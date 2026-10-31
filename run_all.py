"""Site Safety Early Warning, end to end: public safety statistics and real weather for BC, Ontario and Alberta ->
calibrated simulation of a contractor's 15-site portfolio -> early-warning model -> alerts with controls cited for
each province -> live dashboard (with an in-browser scoring engine and live feed) and report dashboards.

    python run_all.py --download             # first run: fetch WorkSafeBC, AWCBC, Alberta OHS, StatCan and ECCC data
    python run_all.py                        # rebuild everything
    python run_all.py --feed feed.json       # also fold live-feed days (exported from the dashboard) into the history
    python run_all.py --report               # redraw only the report dashboards from outputs/
"""
import json
import sys

import numpy as np
import pandas as pd

from ssew import alerts, app, config as C, feed, model as M, nyc, report, site, sources as S


def main():
    if "--report" in sys.argv:
        report.build()
        return
    if "--download" in sys.argv:
        S.download()
        nyc.download()
    wsbc, aw, psi = S.worksafebc(), S.awcbc(), S.alberta_psi()
    emp = S.statcan_employment()
    prov = S.provincial_rates(aw, emp)
    mix = S.event_mix(aw["events"])
    wxs = {k: S.weather(v["code"]) for k, v in C.PROVINCES.items()}
    df, ev, crew = site.portfolio(wxs, {"worksafebc": wsbc, "event_mix": mix, "provinces": prov})
    if "--feed" in sys.argv:            # live-feed days logged on the dashboard join the flagship's history
        df, ev = feed.merge(df, ev, json.loads(open(sys.argv[sys.argv.index("--feed") + 1]).read()))
    rates = {"BC": wsbc["time_loss_rate"], "ON": prov["ON"]["rate"], "AB": prov["AB"]["rate"]}
    sim_rate = {p: float(g.time_loss_injuries.sum() / g.hours.sum() * 200000) for p, g in df.groupby("province")}
    print(f"{df.site.nunique()} sites, {len(df):,} active zone-days, {len(ev)} events; injury rate by province "
          + ", ".join(f"{p} {r:.2f} (target {rates[p]:.2f})" for p, r in sim_rate.items()))
    F = M.frame(df, ev, rates)
    gb, F, th = M.fit(F)
    res, evt = M.evaluate(F, ev)
    res_pooled, evt_pooled = M.evaluate(F, ev, "band_pooled")      # the earlier shared cut-offs, for comparison
    imp = M.importance(gb, F)
    print(json.dumps({k: v for k, v in res.items() if k not in ("calibration", "bands")}, indent=1, default=float))

    # flagship: drivers and controls for every scored zone-day
    fl = F[F.site == site.FLAGSHIP].copy()
    drv = M.drivers(gb, F, fl)
    relevant = lambda zone, d: zone in M.WEATHER_ZONES.get(d, [zone])     # weather only where it acts
    top = [[k for k, v in r.sort_values(ascending=False).items() if v > 0.02 and relevant(z, k)][:3]
           for z, (_, r) in zip(fl.zone, drv.iterrows())]
    top = [(["Wind forecast"] + [k for k in t if k != "Wind forecast"])[:3] if rule else t for t, rule in zip(top, fl["rule"])]
    fl["drivers"] = top
    fl["actions"] = [alerts.recommend(z, d, "BC") for z, d in zip(fl.zone, fl.drivers)]

    C.OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(C.OUT / "zone_days.csv", index=False)
    ev.to_csv(C.OUT / "events.csv", index=False)
    evt.to_csv(C.OUT / "test_events_warned.csv", index=False)
    F.drop(columns=["true_hazard"]).to_csv(C.OUT / "risk_scores.csv", index=False)
    drv.assign(site=fl.site, zone=fl.zone, date=fl.date).to_csv(C.OUT / "flagship_drivers.csv", index=False)
    imp.rename("auc_drop").to_csv(C.OUT / "driver_importance.csv")
    wsbc["narratives"].to_csv(C.OUT / "worksafebc_construction_deaths_2024.csv", index=False)
    aw["events"].to_csv(C.OUT / "awcbc_construction_events.csv", index=False)
    mix.rename("share").to_csv(C.OUT / "construction_event_mix.csv")
    for k, w in wxs.items():
        w.to_csv(C.OUT / f"weather_shift_daily_{k}.csv")
    wxs["BC"].to_csv(C.OUT / "weather_shift_daily.csv")
    model_json = M.export(gb, F)
    (C.OUT / "model.json").write_text(json.dumps(model_json))

    te = F[F.date > C.TRAIN_END]
    from sklearn.metrics import roc_auc_score
    by_prov = {}
    lift = lambda g, col: float(g[g[col] == "red"].y.mean() / g.y.mean()) if (g[col] == "red").any() else None
    for p, g in te.groupby("province"):
        e, ep = evt[evt.province == p], evt_pooled[evt_pooled.province == p]
        weeks = g.date.dt.to_period("W").nunique() * g.site.nunique()
        by_prov[p] = {"auc": float(roc_auc_score(g.y, g.p)), "base_rate": float(g.y.mean()), "events": int(len(e)),
                      "warned": float(e.warned.mean()) if len(e) else None, "sim_rate": sim_rate[p], "target_rate": rates[p],
                      "red_lift": lift(g, "band"), "thresholds": th["by_province"][p],
                      "warned_pooled": float(ep.warned.mean()) if len(ep) else None, "red_lift_pooled": lift(g, "band_pooled"),
                      "alerts_per_site_week": float((g.band != "green").sum() / weeks),
                      "alerts_per_site_week_pooled": float((g.band_pooled != "green").sum() / weeks)}
    print("by province (own vs pooled cut-offs):", {p: (round(b["warned"], 2), round(b["warned_pooled"], 2)) for p, b in by_prov.items()})
    by_site = []
    for s, p, _ in site.SITES:
        t = F[(F.site == s) & (F.date > C.TRAIN_END)]
        e = evt[evt.site == s]
        by_site.append({"site": s, "province": p, "events": int(len(e)), "injuries": int((e.kind != "High-potential near miss").sum()),
                        "warned": float(e.warned.mean()) if len(e) else None,
                        "red_days": int((t.band == "red").sum()), "amber_days": int((t.band == "amber").sum()),
                        "person_hours": float(df[(df.site == s) & (df.date > C.TRAIN_END)].hours.sum())})
    summary = {"metrics": res, "metrics_pooled": {k: res_pooled[k] for k in ("warned_share", "warned_injuries_share", "alerts_per_site_week")},
               "thresholds": th, "importance": imp.to_dict(), "by_site": by_site, "by_province": by_prov,
               "sources": {"time_loss_rate": wsbc["time_loss_rate"], "serious_rate": wsbc["serious_rate"],
                           "claims_2024": wsbc["claims_2024"], "deaths_by_year": wsbc["deaths_by_year"],
                           "avg_duration_days": wsbc["avg_duration_days"], "bc_construction_ltc": aw["construction_by_year"],
                           "event_mix": mix.to_dict(), "alberta_psi": psi, "provinces": prov,
                           "narrative_hazards": wsbc["narratives"].hazard.value_counts().to_dict()},
               "simulated_rate": sim_rate["BC"], "simulated_rates": sim_rate, "person_hours": float(df.hours.sum())}
    # real-outcome check on New York City's public records (rerun with --nyc; otherwise reuse the last result)
    nyc_json = C.OUT / "nyc_check.json"
    if "--nyc" in sys.argv or (not nyc_json.exists() and (nyc.RAW / "incidents.csv.gz").exists()):
        nyc.run()
    if nyc_json.exists():
        summary["nyc"] = json.loads(nyc_json.read_text())
    (C.OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    # the featured site scores live in the browser against its own province's cut-offs
    th_app = {**th["by_province"][dict((s, p) for s, p, _ in site.SITES)[site.FLAGSHIP]], **th}
    app.build(app.payload(fl, ev, wxs["BC"], crew, summary, wsbc["narratives"], th_app, evt, model_json,
                          df[df.site == site.FLAGSHIP]))
    report.build()


if __name__ == "__main__":
    main()
