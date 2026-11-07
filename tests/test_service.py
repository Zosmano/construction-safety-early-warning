"""Tests for the ingestion service, on a temporary database with made-up secrets."""
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from service import confidence, db, schedule_sync, security  # noqa: E402
from service.app import create_app, feed_docs  # noqa: E402

SECRET, KEY, TOKEN = "s" * 40, "k" * 40, "t" * 40


@pytest.fixture
def env(tmp_path):
    cfg = {"db": str(tmp_path / "svc.db"), "webhook_secrets": {"T1": SECRET, "T2": "x" * 40},
           "api_keys": {"T1": KEY, "T2": "y" * 40}, "report_tokens": {"P1": TOKEN}, "pepper": b"p" * 40, "max_skew": 300}
    con = db.connect(cfg["db"])
    with con:
        con.execute("INSERT INTO tenants (tenant_id, name, account_type) VALUES ('T1','GC One','general_contractor')")
        con.execute("INSERT INTO tenants (tenant_id, name, account_type) VALUES ('T2','GC Two','general_contractor')")
        con.execute("INSERT INTO projects (project_id, tenant_id, name, jurisdiction, city) VALUES ('P1','T1','Site','BC','Burnaby')")
        con.execute("INSERT INTO projects (project_id, tenant_id, name, jurisdiction, city) VALUES ('P2','T2','Other','ON','Toronto')")
    return cfg, TestClient(create_app(cfg)), con


def post_log(client, payload, tenant="T1", secret=SECRET, t=None):
    body = json.dumps(payload).encode()
    return client.post("/v1/daily-logs", content=body, headers={
        "X-SSEW-Tenant": tenant, "X-SSEW-Signature": security.sign(secret, body, t), "Content-Type": "application/json"})


def log(event="e1", day=None, **zones):
    return {"event_id": event, "project_id": "P1", "log_date": (day or date.today()).isoformat(),
            "zones": zones or {"FRM": {"crew": 12, "near_misses": 1}}}


def test_signed_log_is_accepted_and_retry_is_idempotent(env):
    _, c, con = env
    assert post_log(c, log()).status_code == 202
    r = post_log(c, log())
    assert r.json()["status"] == "duplicate"
    assert con.execute("SELECT COUNT(*) FROM zone_days").fetchone()[0] == 1


@pytest.mark.parametrize("change", ["tampered", "wrong_secret", "old", "missing", "garbage"])
def test_bad_signatures_are_rejected_without_crashing(env, change):
    _, c, _ = env
    body = json.dumps(log()).encode()
    sig = {"tampered": security.sign(SECRET, body + b" "), "wrong_secret": security.sign("z" * 40, body),
           "old": security.sign(SECRET, body, int(time.time()) - 3600), "missing": None, "garbage": "t=1,v1=ab"}[change]
    headers = {"X-SSEW-Tenant": "T1", "Content-Type": "application/json"} | ({"X-SSEW-Signature": sig} if sig else {})
    assert c.post("/v1/daily-logs", content=body, headers=headers).status_code == 401


def test_a_tenant_cannot_write_or_read_another_tenants_project(env):
    _, c, _ = env
    assert post_log(c, log(), tenant="T2", secret="x" * 40).status_code == 404
    r = c.get("/v1/projects/P1/confidence", headers={"X-SSEW-Tenant": "T2", "Authorization": "Bearer " + "y" * 40})
    assert r.status_code == 404


def test_roster_becomes_counts_and_no_identifier_is_stored(env):
    _, c, con = env
    roster = [{"worker_ref": "BADGE-1001", "trade": "Formwork", "hours": 10, "new_hire": True},
              {"worker_ref": "BADGE-1002", "trade": "Electrical", "hours": 8},
              {"worker_ref": "BADGE-1001", "trade": "Formwork", "hours": 10, "new_hire": True}]   # scanned twice
    assert post_log(c, log(FRM={"roster": roster, "hazard_obs": 3})).status_code == 202
    row = dict(con.execute("SELECT * FROM zone_days").fetchone())
    assert (row["crew"], row["crew_hours"], row["trades"], row["new_workers_pct"], row["overtime_pct"]) == (2, 18.0, 2, 50.0, 50.0)
    dump = "\n".join(con.iterdump())
    assert "BADGE-1001" not in dump and security.hmac.new(b"p" * 40, b"BADGE-1001", "sha256").hexdigest() not in dump


def test_unknown_zones_and_fields_are_rejected(env):
    _, c, _ = env
    assert post_log(c, log(XYZ={"crew": 3})).status_code == 422
    p = log()
    p["worker_names"] = ["someone"]
    assert post_log(c, p).status_code == 422


def test_confidence_rises_with_real_recent_days(env):
    _, c, con = env
    today = date(2026, 11, 6)                                     # a Friday
    days = confidence.work_days_back(today, 20)
    for i, d in enumerate(days[:16]):
        assert post_log(c, log(f"e{i}", d)).status_code == 202
    assert confidence.level(con, "T1", "P1", today)["level"] == "Good"
    assert confidence.level(con, "T1", "P1", today + timedelta(days=7))["level"] == "Low"     # a week with no logs
    lvl = confidence.level(con, "T2", "P2", today)
    assert lvl["level"] == "Very low" and lvl["real_days"] == 0


def test_a_logged_weekend_day_counts(env):
    _, c, con = env
    saturday = date(2026, 11, 7)
    assert post_log(c, log("sat", saturday)).status_code == 202
    lvl = confidence.level(con, "T1", "P1", saturday)
    assert lvl["level"] == "Low" and lvl["real_days"] == 1 and lvl["work_days_since_latest"] == 0


def test_confidence_endpoint_needs_the_tenants_key(env):
    _, c, _ = env
    assert c.get("/v1/projects/P1/confidence", headers={"X-SSEW-Tenant": "T1"}).status_code == 401
    r = c.get("/v1/projects/P1/confidence", headers={"X-SSEW-Tenant": "T1", "Authorization": "Bearer " + KEY})
    assert r.status_code == 200 and r.json()["level"] == "Very low"


def test_worker_reports_are_anonymous_and_flag_translation(env):
    _, c, con = env
    bad = c.post("/v1/projects/P1/worker-reports", json={"category": "hazard", "text": "x", "language_code": "en"},
                 headers={"X-Report-Token": "wrong" * 8})
    assert bad.status_code == 401
    r = c.post("/v1/projects/P1/worker-reports", json={"zone_code": "SCF", "category": "hazard",
               "text": "ਸਕੈਫੋਲਡ ਦੀ ਰੇਲਿੰਗ ਢਿੱਲੀ ਹੈ", "language_code": "pa"}, headers={"X-Report-Token": TOKEN})
    assert r.status_code == 201 and r.json()["translation"] == "pending"
    row = dict(con.execute("SELECT * FROM worker_reports").fetchone())
    assert row["language_code"] == "pa" and row["text_en"] is None and set(row) >= {"received_date"}
    assert not any(k in row for k in ("ip", "received_at", "device"))


def test_feed_export_matches_the_dashboard_format(env):
    _, c, con = env
    p = log(FRM={"crew": 10, "near_misses": 2})
    p["events"] = [{"zone": "FRM", "kind": "High-potential near miss"}]
    p["weather"] = {"gust": 55, "wet": True}
    post_log(c, p)
    doc = feed_docs(con, "T1", "P1")[0]
    assert doc["zones"]["FRM"]["crew"] == 10 and doc["zones"]["FRM"]["nm"] == 2
    assert doc["events"] == [{"zone": "FRM", "kind": "High-potential near miss"}] and doc["weather"]["wet"] is True


def test_schedule_sync_reads_the_programme_csv(env, tmp_path):
    _, _, con = env
    sample = Path(__file__).resolve().parent.parent / "samples" / "SAMPLE_programme_fictional_project.csv"
    proj = con.execute("SELECT * FROM projects WHERE project_id = 'P1'").fetchone()
    res = schedule_sync.sync_project(con, proj, {"type": "file", "path": str(sample)})
    assert res["status"] == "synced" and res["activities"] > 10 and not res["skipped_lines"]
    bad = tmp_path / "bad.csv"
    bad.write_text("activity,zone,start,finish,crew\nX,ZZZ,2026-01-01,2026-01-02,3\n", encoding="utf-8")
    assert schedule_sync.sync_project(con, proj, {"type": "file", "path": str(bad)})["status"] == "failed"
    assert con.execute("SELECT COUNT(*) FROM programme_activities").fetchone()[0] == res["activities"]   # old kept
    with pytest.raises(schedule_sync.NotConfigured):
        schedule_sync.fetch({"type": "procore"}, set())


def test_settings_refuse_weak_or_missing_secrets(monkeypatch):
    from service import settings
    monkeypatch.setenv("SSEW_ID_PEPPER", "p" * 40)
    monkeypatch.setenv("SSEW_API_KEYS", json.dumps({"T1": KEY}))
    monkeypatch.setenv("SSEW_WEBHOOK_SECRETS", json.dumps({"T1": "short"}))
    with pytest.raises(settings.SettingsError):
        settings.load()
    monkeypatch.delenv("SSEW_WEBHOOK_SECRETS")
    with pytest.raises(settings.SettingsError):
        settings.load()
