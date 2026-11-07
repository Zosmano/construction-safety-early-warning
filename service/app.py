"""HTTP API. Run locally:  uvicorn service.app:app --port 8770   (settings from the environment)

POST /v1/daily-logs                          signed webhook: one project-day of zone readings
POST /v1/projects/{project_id}/worker-reports anonymous report from the gate-poster QR code
GET  /v1/projects/{project_id}/confidence    scan confidence for the dashboard
GET  /v1/projects/{project_id}/feed          logged days in the dashboard's feed format (for retraining)
GET  /healthz
"""
import hmac
import json
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from . import confidence, db, security, settings as settings_mod


class RosterEntry(BaseModel):
    worker_ref: str = Field(min_length=1, max_length=200)     # badge or card number: used, then discarded
    trade: str | None = Field(default=None, max_length=120)
    hours: float = Field(default=8, ge=0, le=24)
    new_hire: bool = False


class ZoneIn(BaseModel):
    roster: list[RosterEntry] | None = None                   # either a roster or counts
    crew: int | None = Field(default=None, ge=0, le=5000)
    near_misses: int = Field(default=0, ge=0, le=500)
    hazard_obs: int = Field(default=0, ge=0, le=500)
    ppe_gaps_pct: float = Field(default=0, ge=0, le=100)
    housekeeping: float = Field(default=85, ge=0, le=100)
    new_workers_pct: float = Field(default=0, ge=0, le=100)
    overtime_pct: float = Field(default=0, ge=0, le=100)
    trades: int = Field(default=1, ge=0, le=200)
    permit_issues: int = Field(default=0, ge=0, le=200)


class Weather(BaseModel):
    gust: float | None = Field(default=None, ge=0, le=250)
    humidex: float | None = Field(default=None, ge=-60, le=60)
    wet: bool = False
    freeze: bool = False


class SiteEvent(BaseModel):
    zone: str
    kind: Literal["High-potential near miss", "Health-care injury", "Time-loss injury"]   # the dashboard's terms


class DailyLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    log_date: date
    source: str = Field(default="api", max_length=40)
    weather: Weather = Weather()
    zones: dict[str, ZoneIn]
    events: list[SiteEvent] = []


class WorkerReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    zone_code: str | None = None
    category: Literal["hazard", "near_miss", "idea", "other"]
    text: str = Field(min_length=1, max_length=2000)
    language_code: str = Field(min_length=2, max_length=12)

    @field_validator("language_code")
    @classmethod
    def lang(cls, v):
        v = v.strip()
        if not all(p.isalpha() and len(p) <= 8 for p in v.replace("_", "-").split("-")):
            raise ValueError("language_code must look like en, fr, pa or zh-Hant")
        return v.lower()


def create_app(cfg=None):
    cfg = cfg or settings_mod.load()
    con = db.connect(cfg["db"])
    app = FastAPI(title="Site Safety Early Warning ingestion", version="1.0")
    report_log = defaultdict(deque)          # project_id -> recent report times, for a simple rate limit

    def project_of(tenant_id, project_id):
        row = con.execute("SELECT * FROM projects WHERE project_id = ? AND tenant_id = ? AND active = 1",
                          (project_id, tenant_id)).fetchone()
        if not row:
            raise HTTPException(404, "unknown project for this tenant")
        return row

    def check_key(tenant_id, authorization):
        key = cfg["api_keys"].get(tenant_id or "")
        given = (authorization or "").removeprefix("Bearer ").strip()
        if not key or not hmac.compare_digest(key, given):
            raise HTTPException(401, "invalid tenant or API key")

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.post("/v1/daily-logs", status_code=202)
    async def daily_log(request: Request, x_ssew_tenant: str = Header(...), x_ssew_signature: str | None = Header(None)):
        secret = cfg["webhook_secrets"].get(x_ssew_tenant)
        if not secret:
            raise HTTPException(401, "unknown tenant")
        body = await request.body()
        try:
            security.verify(secret, body, x_ssew_signature, cfg["max_skew"])
        except security.SignatureError as e:
            raise HTTPException(401, str(e))
        try:
            log = DailyLog.model_validate_json(body)
        except ValidationError as e:
            raise HTTPException(422, json.loads(e.json(include_url=False)))
        proj = project_of(x_ssew_tenant, log.project_id)
        if log.log_date > date.today() + timedelta(days=1):
            raise HTTPException(422, "log_date is in the future")
        allowed = db.zones_for(con, proj["sector"])
        bad = sorted(set(log.zones) - allowed) + sorted({e.zone for e in log.events} - allowed)
        if bad:
            raise HTTPException(422, f"zones not in the {proj['sector']} layout: {', '.join(bad)}")
        if con.execute("SELECT 1 FROM ingestion_events WHERE tenant_id = ? AND event_id = ?",
                       (x_ssew_tenant, log.event_id)).fetchone():
            return {"status": "duplicate", "event_id": log.event_id}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        d = log.log_date.isoformat()
        rows = []
        for z, v in log.zones.items():
            counts = security.roster_counts([r.model_dump() for r in v.roster], cfg["pepper"]) if v.roster is not None else {
                "crew": v.crew or 0, "crew_hours": 8.0 * (v.crew or 0), "trades": v.trades,
                "new_workers_pct": v.new_workers_pct, "overtime_pct": v.overtime_pct}
            rows.append((x_ssew_tenant, log.project_id, d, z, counts["crew"], counts["crew_hours"], v.near_misses, v.hazard_obs,
                         v.ppe_gaps_pct, v.housekeeping, counts["new_workers_pct"], counts["overtime_pct"], counts["trades"],
                         v.permit_issues, log.source, log.event_id, now))
        with con:
            con.execute("INSERT INTO ingestion_events VALUES (?,?,?,?,?,?)",
                        (log.event_id, x_ssew_tenant, log.project_id, log.source, d, now))
            con.executemany("INSERT OR REPLACE INTO zone_days VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            w = log.weather
            con.execute("INSERT OR REPLACE INTO day_weather VALUES (?,?,?,?,?,?)",
                        (log.project_id, d, w.gust, w.humidex, int(w.wet), int(w.freeze)))
            con.execute("DELETE FROM site_events WHERE project_id = ? AND log_date = ?", (log.project_id, d))
            con.executemany("INSERT INTO site_events VALUES (?,?,?,?,?,?)",
                            [(x_ssew_tenant, log.project_id, d, e.zone, e.kind, log.event_id) for e in log.events])
        return {"status": "accepted", "event_id": log.event_id, "zones": len(rows)}

    @app.post("/v1/projects/{project_id}/worker-reports", status_code=201)
    def worker_report(project_id: str, report: WorkerReport, x_report_token: str = Header(...)):
        token = cfg["report_tokens"].get(project_id)
        if not token or not hmac.compare_digest(token, x_report_token):
            raise HTTPException(401, "invalid report link")
        proj = con.execute("SELECT * FROM projects WHERE project_id = ? AND active = 1", (project_id,)).fetchone()
        if not proj:
            raise HTTPException(404, "unknown project")
        if report.zone_code and report.zone_code not in db.zones_for(con, proj["sector"]):
            raise HTTPException(422, "unknown zone")
        q, t = report_log[project_id], time.time()
        while q and t - q[0] > 3600:
            q.popleft()
        if len(q) >= 60:
            raise HTTPException(429, "too many reports from this site in the last hour; try again later")
        q.append(t)
        status = "not_needed" if report.language_code.split("-")[0] == "en" else "pending"
        with con:
            con.execute("INSERT INTO worker_reports (tenant_id, project_id, zone_code, category, text, language_code, "
                        "translation_status, text_en, received_date) VALUES (?,?,?,?,?,?,?,?,?)",
                        (proj["tenant_id"], project_id, report.zone_code, report.category, report.text,
                         report.language_code, status, report.text if status == "not_needed" else None, date.today().isoformat()))
        return {"status": "received", "translation": status}

    @app.get("/v1/projects/{project_id}/confidence")
    def get_confidence(project_id: str, x_ssew_tenant: str = Header(...), authorization: str | None = Header(None)):
        check_key(x_ssew_tenant, authorization)
        project_of(x_ssew_tenant, project_id)
        return confidence.level(con, x_ssew_tenant, project_id)

    @app.get("/v1/projects/{project_id}/feed")
    def get_feed(project_id: str, x_ssew_tenant: str = Header(...), authorization: str | None = Header(None)):
        check_key(x_ssew_tenant, authorization)
        project_of(x_ssew_tenant, project_id)
        return {"docs": feed_docs(con, x_ssew_tenant, project_id)}

    return app


def feed_docs(con, tenant_id, project_id):
    """Logged days in the format the dashboard's live feed and `run_all.py --feed` read."""
    docs = {}
    for r in con.execute("SELECT * FROM zone_days WHERE tenant_id = ? AND project_id = ? ORDER BY log_date, zone_code",
                         (tenant_id, project_id)):
        d = docs.setdefault(r["log_date"], {"date": r["log_date"], "zones": {}, "events": [], "weather": {},
                                            "source": r["source"], "received_at": r["received_at"]})
        d["zones"][r["zone_code"]] = {"crew": r["crew"], "nm": r["near_misses"], "obs": r["hazard_obs"], "ppe": r["ppe_gaps_pct"],
                                      "house": r["housekeeping"], "new": r["new_workers_pct"], "ot": r["overtime_pct"],
                                      "trades": r["trades"], "permits": r["permit_issues"]}
    for r in con.execute("SELECT w.* FROM day_weather w JOIN projects p ON p.project_id = w.project_id "
                         "WHERE p.tenant_id = ? AND w.project_id = ?", (tenant_id, project_id)):
        if r["log_date"] in docs:
            docs[r["log_date"]]["weather"] = {k: r[k] for k in ("gust", "humidex") if r[k] is not None} | {
                "wet": bool(r["wet"]), "freeze": bool(r["freeze"])}
    for r in con.execute("SELECT * FROM site_events WHERE tenant_id = ? AND project_id = ?", (tenant_id, project_id)):
        if r["log_date"] in docs:
            docs[r["log_date"]]["events"].append({"zone": r["zone_code"], "kind": r["kind"]})
    return list(docs.values())


try:
    app = create_app()
except settings_mod.SettingsError:
    app = None      # imported without settings (tests, tooling); `uvicorn service.app:app` needs them set
