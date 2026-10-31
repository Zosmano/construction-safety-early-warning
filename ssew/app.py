"""Build the self-contained live dashboard (outputs/site_safety_live.html): the flagship's history and scores, the
exported model that re-scores new data in the browser, and everything the tabs show."""
import datetime as dt
import json

import numpy as np
import pandas as pd

from . import alerts, config as C
from .model import GROUPS, WEATHER_ZONES
from .site import FLAGSHIP, SITES, ZONES

TEMPLATE = C.ROOT / "ssew" / "app_template.html"
BANDS = ["green", "amber", "red"]
LOG_FIELDS = {"crew": "crew", "nm": "reported_near_misses", "obs": "hazard_obs", "ppe": "ppe_noncompliance",
              "house": "housekeeping", "new": "new_worker_share", "ot": "overtime_share", "trades": "trades",
              "permits": "permit_issues"}


def payload(fl, events, wx, crew, summary, narratives, th, test_events, model, logs):
    drivers = list(GROUPS)
    days = sorted(set(fl.date.unique()) | set(logs.date.unique()))      # include the last day (no forward target)
    dkey = {d: i for i, d in enumerate(days)}
    risk = {z[0]: [None] * len(days) for z in ZONES}
    for r in fl.itertuples():
        risk[r.zone][dkey[r.date]] = [round(float(r.p), 4), BANDS.index(r.band), [drivers.index(x) for x in r.drivers]]
    w = wx.reindex(pd.DatetimeIndex(days))
    ev = events[events.site == FLAGSHIP]
    # raw daily logs per zone (null when the zone had no crew): the live engine rebuilds features from these
    L = logs.set_index(["zone", "date"])
    raw = {}
    for z in [z[0] for z in ZONES]:
        sub = L.loc[z] if z in L.index.get_level_values(0) else pd.DataFrame()
        sub = sub.reindex(pd.DatetimeIndex(days))
        raw[z] = {k: [None if pd.isna(v) else round(float(v) * (100 if k in ("ppe", "new", "ot") else 1), 5) for v in sub[col]]
                  for k, col in LOG_FIELDS.items()}
    return {
        "generated": dt.date.today().isoformat(), "site": C.SITE_NAME, "flagship": FLAGSHIP,
        "sites": [{"site": s, "province": p} for s, p, _ in SITES], "train_end": C.TRAIN_END, "horizon": C.HORIZON_DAYS,
        "zones": [{"id": z[0], "name": z[1], "poly": z[2], "hazards": list(z[3])} for z in ZONES],
        "days": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in days],
        "risk": risk, "drivers": drivers, "weather_zones": WEATHER_ZONES,
        "actions": {k: {"action": v[0], "ref": v[1]} for k, v in alerts.ACTIONS.items()},
        "zone_rule": {k: {"action": v[0], "ref": v[1]} for k, v in alerts.ZONE_RULE.items()},
        "law": alerts.LAW,
        "crew": {z: crew[z].reindex(pd.DatetimeIndex(days)).fillna(0).astype(int).tolist() for z in crew.columns},
        "logs": raw,
        "weather": {"gust": w.gust_est.round(2).tolist(), "humidex": w.humidex_max.round(2).tolist(),
                    "dir": w.wind_dir.fillna(-1).astype(int).tolist(),
                    "rain": w.rain_hours.fillna(0).astype(int).tolist(), "tmin": w.temp_min.round(1).tolist(),
                    "snow": w.snow_or_ice.fillna(False).astype(bool).tolist()},
        "triggers": {"gust": C.CRANE_GUST_KMH, "humidex": C.HUMIDEX_HEAT, "wet": C.WET_HOURS, "freeze": C.FREEZE_C},
        # every calendar day of real Vancouver shift weather, 2023-2025: the seasonal outlook for any future date
        "climate": {"dates": [d.strftime("%Y-%m-%d") for d in wx.index], "gust": wx.gust_est.round(1).tolist(),
                    "humidex": wx.humidex_max.round(1).tolist(), "rain": wx.rain_hours.fillna(0).astype(int).tolist(),
                    "tmin": wx.temp_min.round(1).tolist(), "snow": wx.snow_or_ice.fillna(False).astype(bool).tolist()},
        "events": [{"d": r.date.strftime("%Y-%m-%d"), "z": r.zone, "k": r.kind, "f": r.family, "s": bool(r.serious)}
                   for r in ev.itertuples()],
        "crane": ["2023-08-01", "2025-01-31"],
        "thresholds": th, "model": model, "base_rate_bc": summary["sources"]["time_loss_rate"],
        "summary": summary,
        "narratives": narratives[["occupation", "age", "hazard", "description"]].to_dict("records"),
        "test_events": test_events.sort_values("date").assign(date=lambda d: d.date.dt.strftime("%Y-%m-%d"))
                       [["date", "site", "province", "zone", "kind", "family", "warned"]].to_dict("records"),
    }


def build(data):
    blob = json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=float).replace("</", "<\\/")
    body = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    C.OUT.mkdir(parents=True, exist_ok=True)
    head, rest = body.split("<style>", 1)
    full = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            + head + "<style>" + rest.replace("</style>", "</style></head><body>", 1) + "\n</body></html>")
    (C.OUT / "site_safety_live.html").write_text(full, encoding="utf-8")
    (C.OUT / "site_safety_live_artifact.html").write_text(body, encoding="utf-8")
    print(f"-> {C.OUT / 'site_safety_live.html'} ({len(full) / 1e6:.2f} MB)")
