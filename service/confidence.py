"""Scan confidence, the same rule the dashboard uses: how much of the recent site record is real and
how current it is. It stops at "Good", because fresh data can't vouch for a model trained on simulated logs."""
from datetime import date, datetime, timedelta, timezone


def work_days_back(as_of: date, n: int):
    days, d = [], as_of
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days


def work_days_between(a: date, b: date):
    return sum(1 for i in range(1, (b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)


def level(con, tenant_id, project_id, as_of: date | None = None, now: datetime | None = None):
    as_of = as_of or date.today()
    now = now or datetime.now(timezone.utc)
    window = work_days_back(as_of, 20)
    rows = con.execute("SELECT DISTINCT log_date FROM zone_days WHERE tenant_id = ? AND project_id = ? AND crew > 0 "
                       "AND log_date BETWEEN ? AND ?", (tenant_id, project_id, window[-1].isoformat(), as_of.isoformat())).fetchall()
    real = sorted(date.fromisoformat(r["log_date"]) for r in rows)   # a logged weekend day counts too
    sync = con.execute("SELECT MAX(received_at) AS t FROM ingestion_events WHERE tenant_id = ? AND project_id = ? "
                       "AND source <> 'manual'", (tenant_id, project_id)).fetchone()["t"]
    sync_hours = None
    if sync:
        sync_hours = round((now - datetime.fromisoformat(sync)).total_seconds() / 3600, 1)
    if not real:
        return {"level": "Very low", "real_days": 0, "of_days": 20, "latest": None, "work_days_since_latest": None,
                "hours_since_sync": sync_hours, "note": "no real site records yet: log a day or connect a feed"}
    ago = work_days_between(real[-1], as_of)
    n = len(real)
    lvl = "Good" if n >= 15 and ago <= 1 else "Partial" if n >= 5 and ago <= 2 else "Low"
    return {"level": lvl, "real_days": n, "of_days": 20, "latest": real[-1].isoformat(), "work_days_since_latest": ago,
            "hours_since_sync": sync_hours, "note": "capped at Good while the model is trained on simulated logs"}
