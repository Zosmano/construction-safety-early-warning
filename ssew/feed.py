"""The live feed: days a supervisor logs on the dashboard (stored in the page's shared database) folded back into the
flagship's history, so the next run retrains on them.

Export the feed with Claude (ArtifactData `list` of the `feed` collection) or the dashboard, save it as JSON, then
`python run_all.py --feed feed.json`. Each document: {date, weather: {gust, humidex, wet, freeze}, zones: {ZONE:
{crew, nm, obs, ppe, house, new, ot, trades, permits}}, events: [{zone, kind}]}."""
import pandas as pd

from .site import FLAGSHIP


def merge(df, ev, docs):
    docs = docs.get("docs", docs) if isinstance(docs, dict) else docs
    rows, evs = [], []
    for d in docs:
        d = d.get("data", d)
        date = pd.Timestamp(d["date"])
        w = d.get("weather", {})
        for z, v in d.get("zones", {}).items():
            if not v.get("crew"):
                continue
            rows.append({"date": date, "zone": z, "site": FLAGSHIP, "province": "BC", "crew": v["crew"], "hours": v["crew"] * 8,
                         "new_worker_share": v.get("new", 0) / 100, "overtime_share": v.get("ot", 0) / 100, "trades": v.get("trades", 1),
                         "hazard_obs": v.get("obs", 0), "ppe_noncompliance": v.get("ppe", 0) / 100, "housekeeping": v.get("house", 85),
                         "permit_issues": v.get("permits", 0), "reported_near_misses": v.get("nm", 0), "near_misses": 0,
                         "health_care_injuries": 0, "time_loss_injuries": 0, "true_hazard": float("nan"), "latent_climate": float("nan"),
                         "gust_est": w.get("gust", 30), "humidex_max": w.get("humidex", 15), "rain_hours": 4 if w.get("wet") else 0,
                         "temp_min": 0 if w.get("freeze") else 8, "snow_or_ice": bool(w.get("freeze")), "wind_dir": -1})
        for e in d.get("events", []):
            evs.append({"date": date, "zone": e["zone"], "kind": e["kind"], "family": e.get("family", "Reported on site"),
                        "serious": False, "site": FLAGSHIP, "province": "BC"})
    if rows:
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    if evs:
        ev = pd.concat([ev, pd.DataFrame(evs)], ignore_index=True)
    print(f"live feed: {len(docs)} days, {len(rows)} zone-days, {len(evs)} events merged")
    return df, ev
