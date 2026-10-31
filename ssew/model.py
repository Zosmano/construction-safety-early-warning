"""Early-warning model: the probability of an injury or high-potential near miss in a zone over the next
HORIZON work days, from what the site knows at the end of today (indicators logged so far, the crew plan and the
weather forecast). Trained before TRAIN_END, judged on the months after."""
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from . import config as C
from .site import ZONE_IDS

GROUPS = {  # driver name shown to the site -> feature columns
    "Near-miss reports": ["nm_5", "nm_20"],
    "Hazard observations": ["obs_5", "obs_20"],
    "PPE non-compliance": ["ppe_10"],
    "Housekeeping": ["house_10"],
    "New workers on crew": ["new_10"],
    "Overtime and fatigue": ["ot_10"],
    "Trade congestion": ["trades_5"],
    "Permit issues": ["permit_10"],
    "Wind forecast": ["gust_fc"],
    "Heat forecast": ["humidex_fc"],
    "Rain and ice forecast": ["wet_fc", "freeze_fc"],
    "Crew exposure": ["hours_plan", "crew_now"],
}
# Recent incidents (events in the last 20 days, days since the last one) were tested and made test-period
# predictions worse (shuffling them raised AUC), so they are kept for display only. Trend features (last 5 vs 20
# days for near misses, observations, PPE and housekeeping; crew ramp-up) were also tested: +0.002 AUC at best and
# not chosen on the validation window, so they are left out.
ZONE_COLS = [f"z_{z}" for z in ZONE_IDS]
FEATURES = [f for g in GROUPS.values() for f in g] + ["base_rate"] + ZONE_COLS
WEATHER_ZONES = {  # zones where each weather driver acts (mirrors site.simulate); elsewhere it is not cited
    "Wind forecast": ["CRN", "SCF", "ROF"],
    "Heat forecast": ["ROF", "DCK", "FRM", "LAY"],
    "Rain and ice forecast": ["DCK", "SCF", "ROF", "GTE", "LAY", "EXC"],
}


def frame(df, events, rates):
    """One row per site, zone and work day with features (past and planned only) and the forward target.
    `rates`: each province's construction claims rate, given to the model so it can scale across provinces."""
    days = pd.Index(sorted(df.date.unique()))
    sites = df.site.unique()
    grid = pd.MultiIndex.from_product([sites, ZONE_IDS, days], names=["site", "zone", "date"])
    X = df.set_index(["site", "zone", "date"]).reindex(grid)
    X[["crew", "hours", "hazard_obs", "reported_near_misses", "permit_issues", "trades"]] = \
        X[["crew", "hours", "hazard_obs", "reported_near_misses", "permit_issues", "trades"]].fillna(0)
    wxs = {s: g.drop_duplicates("date").set_index("date")[["gust_est", "humidex_max", "rain_hours", "temp_min", "snow_or_ice"]]
           for s, g in df.groupby("site")}
    prov = df.drop_duplicates("site").set_index("site").province
    ev = events.groupby(["site", "zone", "date"]).size().rename("ev")
    X = X.join(ev).fillna({"ev": 0}).reset_index()
    out = []
    for (s, z), g in X.groupby(["site", "zone"], sort=False):
        wx = wxs[s]
        g = g.sort_values("date").reset_index(drop=True)
        r = lambda col, w: g[col].rolling(w, min_periods=1).sum()
        m = lambda col, w: g[col].rolling(w, min_periods=1).mean()
        f = pd.DataFrame({"site": s, "province": prov[s], "zone": z, "date": g.date, "crew_now": g.crew})
        f["base_rate"] = rates[prov[s]]
        f["nm_5"], f["nm_20"] = r("reported_near_misses", 5), r("reported_near_misses", 20)
        f["obs_5"], f["obs_20"] = r("hazard_obs", 5), r("hazard_obs", 20)
        f["ppe_10"], f["house_10"] = m("ppe_noncompliance", 10), m("housekeeping", 10)
        f["new_10"], f["ot_10"] = m("new_worker_share", 10), m("overtime_share", 10)
        f["trades_5"], f["permit_10"] = m("trades", 5), r("permit_issues", 10)
        f["events_20"] = r("ev", 20)
        last = g.date.where(g.ev > 0).ffill()
        f["days_since_event"] = ((g.date - last).dt.days).fillna(999).clip(upper=999)
        # planned and forecast: the next HORIZON work days (the crew plan and the weather forecast are known)
        fwd = lambda col: g[col][::-1].rolling(C.HORIZON_DAYS, min_periods=1).agg("max" if col != "hours" else "sum")[::-1].shift(-1)
        f["hours_plan"] = fwd("hours")
        w = wx.reindex(g.date).reset_index(drop=True)
        fw = lambda s, how: s[::-1].rolling(C.HORIZON_DAYS, min_periods=1).agg(how)[::-1].shift(-1)
        f["gust_fc"] = fw(w.gust_est, "max")
        f["humidex_fc"] = fw(w.humidex_max, "max")
        f["wet_fc"] = fw((w.rain_hours >= C.WET_HOURS).astype(float), "sum")
        f["freeze_fc"] = fw(((w.temp_min <= C.FREEZE_C) | w.snow_or_ice.astype(bool)).astype(float), "sum")
        f["y"] = (g.ev[::-1].rolling(C.HORIZON_DAYS, min_periods=1).sum()[::-1].shift(-1) > 0).astype(float)
        f["y"] = f.y.where(g.index < len(g) - 1)
        f["true_hazard"] = g.true_hazard.fillna(0)
        f["events_today"] = g.ev
        out.append(f)
    F = pd.concat(out, ignore_index=True)
    for z in ZONE_IDS:
        F[f"z_{z}"] = (F.zone == z).astype(float)
    # a zone with nobody planned can't have an event: score only zone-days with work now or planned
    F = F[(F.crew_now > 0) | (F.hours_plan > 0)].dropna(subset=["y", "hours_plan"])
    return F.reset_index(drop=True)


def fit(F):
    tr = F[F.date <= C.TRAIN_END]
    te = F[F.date > C.TRAIN_END]
    # settings chosen on a validation window inside the training period (May-Oct 2024), never on the test months
    gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.03, max_leaf_nodes=15, min_samples_leaf=150,
                                        l2_regularization=1.0, random_state=0)
    gb.fit(tr[FEATURES], tr.y)
    base = LogisticRegression(max_iter=1000)      # exposure-only baseline: who is on site, and where
    Xb = lambda d: np.c_[np.log1p(d.hours_plan), pd.get_dummies(d.zone).reindex(columns=ZONE_IDS, fill_value=0)]
    base.fit(Xb(tr), tr.y)
    F = F.copy()
    F["p"] = gb.predict_proba(F[FEATURES])[:, 1]
    F["p_base"] = base.predict_proba(Xb(F))[:, 1]
    # alert bands per province. Pooled cut-offs under-flag low-rate Ontario, whose zones rarely reach BC-level risk
    # even when they are its riskiest. Each province's cut-off is the lower of the pooled one and its own top 5% /
    # next 15% of training zone-days, so a province's riskiest zones always alert and no province alerts less.
    tr = F.date <= C.TRAIN_END
    cut = lambda p: {"red": float(np.quantile(p, 1 - C.RED_SHARE)), "amber": float(np.quantile(p, 1 - C.AMBER_SHARE))}
    pooled = cut(F.loc[tr, "p"])
    th = {"pooled": pooled, "by_province": {p: {k: min(v, pooled[k]) for k, v in cut(F.loc[tr & (F.province == p), "p"]).items()}
                                            for p in F.province.unique()}}
    F["band_pooled"] = bands(F.p, th["pooled"]["red"], th["pooled"]["amber"])
    F["band"] = bands(F.p, F.province.map(lambda p: th["by_province"][p]["red"]), F.province.map(lambda p: th["by_province"][p]["amber"]))
    F = rules(F)
    return gb, F, th


def bands(p, red, amber):
    return np.where(p >= red, "red", np.where(p >= amber, "amber", "green"))


def rules(F):
    """Hard safety rules on top of the model. Wind incidents are too rare for the model to learn their weight
    (events nearly double in windy forecast windows while its risk barely moves), so a forecast gust at the
    crane stand-down screen sets crane, scaffold and roof zones to at least amber."""
    F = F.copy()
    windy = (F.gust_fc >= C.CRANE_GUST_KMH) & F.zone.isin(WEATHER_ZONES["Wind forecast"])
    wind = windy & (F.band == "green")
    F["rule"] = np.where(wind, "Wind stand-down rule", "")
    F.loc[wind, "band"] = "amber"
    if "band_pooled" in F:
        F.loc[windy & (F.band_pooled == "green"), "band_pooled"] = "amber"
    return F


def evaluate(F, events, band="band"):
    F = F.assign(band=F[band])
    te = F[F.date > C.TRAIN_END]
    out = {"test_rows": int(len(te)), "test_base_rate": float(te.y.mean()),
           "auc": float(roc_auc_score(te.y, te.p)), "auc_base": float(roc_auc_score(te.y, te.p_base)),
           "ap": float(average_precision_score(te.y, te.p)), "ap_base": float(average_precision_score(te.y, te.p_base)),
           "auc_oracle": float(roc_auc_score(te.y, te.true_hazard * (te.hours_plan + 1)))}
    by = te.groupby("band").agg(rows=("y", "size"), event_rate=("y", "mean"))
    by["share_rows"] = by.rows / by.rows.sum()
    by["lift"] = by.event_rate / te.y.mean()
    by["share_of_positive_rows"] = te.groupby("band").y.sum() / te.y.sum()
    out["bands"] = by.reindex(["red", "amber", "green"]).reset_index().to_dict("records")
    # were the actual test-period events preceded by a warning? first alert within the HORIZON days before
    ev = events[events.date > C.TRAIN_END]
    key = F.set_index(["site", "zone", "date"]).band
    dates = pd.Index(sorted(F.date.unique()))
    caught, leads = [], []
    for r in ev.itertuples():
        i = dates.searchsorted(r.date)
        prior = dates[max(0, i - C.HORIZON_DAYS):i]
        bands = [key.get((r.site, r.zone, d), "green") for d in prior]
        warned = [k for k, b in enumerate(bands) if b != "green"]
        caught.append(bool(warned))
        if warned:
            leads.append(len(prior) - warned[0])
    ev = ev.assign(warned=caught)
    out["events_test"] = int(len(ev))
    out["warned_share"] = float(np.mean(caught))
    out["warned_injuries_share"] = float(ev[ev.kind != "High-potential near miss"].warned.mean())
    out["median_lead_days"] = float(np.median(leads)) if leads else None
    out["warned_by_kind"] = ev.groupby("kind").warned.mean().to_dict()
    weeks = te.date.dt.to_period("W").nunique() * te.site.nunique()
    out["alerts_per_site_week"] = {"red": float((te.band == "red").sum() / weeks), "amber": float((te.band == "amber").sum() / weeks)}
    # calibration (deciles)
    te = te.assign(dec=pd.qcut(te.p.rank(method="first"), 10, labels=False))
    out["calibration"] = te.groupby("dec").agg(pred=("p", "mean"), obs=("y", "mean")).reset_index().to_dict("records")
    return out, ev


def drivers(gb, F, rows):
    """Why a zone is flagged: the change in log-odds when each driver group is set to its normal (training median)
    level for that zone. Positive = pushing risk up."""
    tr = F[F.date <= C.TRAIN_END]
    med = tr.groupby("zone")[FEATURES].median()
    X = rows[FEATURES].copy()
    lo = lambda p: np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
    base = lo(gb.predict_proba(X)[:, 1])
    out = {}
    for name, cols in GROUPS.items():
        Xa = X.copy()
        for c in cols:
            Xa[c] = rows.zone.map(med[c]).values
        out[name] = base - lo(gb.predict_proba(Xa)[:, 1])
    return pd.DataFrame(out, index=rows.index)


def export(gb, F):
    """The fitted trees as plain JSON so the live page can score new data exactly as Python does:
    each tree is [feature, threshold, left, right, missing_left, leaf_value] rows; score = baseline + sum of leaves."""
    trees = []
    for it in gb._predictors:
        nodes = it[0].nodes
        trees.append([[int(n["feature_idx"]), float(n["num_threshold"]), int(n["left"]), int(n["right"]),
                       int(n["missing_go_to_left"]), round(float(n["value"]), 6) if n["is_leaf"] else None] for n in nodes])
    tr = F[F.date <= C.TRAIN_END]
    med = tr.groupby("zone")[FEATURES].median()
    return {"features": FEATURES, "baseline": float(np.ravel(gb._baseline_prediction)[0]), "trees": trees,
            "medians": {z: [round(float(v), 5) for v in med.loc[z, FEATURES]] for z in med.index},
            "groups": GROUPS}


def importance(gb, F):
    """Test-period AUC lost when each driver group is shuffled (permutation importance by group)."""
    te = F[F.date > C.TRAIN_END]
    rng = np.random.default_rng(0)
    auc0 = roc_auc_score(te.y, gb.predict_proba(te[FEATURES])[:, 1])
    out = {}
    for name, cols in GROUPS.items():
        d = []
        for _ in range(5):
            X = te[FEATURES].copy()
            idx = rng.permutation(len(X))
            X[cols] = X[cols].values[idx]
            d.append(auc0 - roc_auc_score(te.y, gb.predict_proba(X)[:, 1]))
        out[name] = float(np.mean(d))
    return pd.Series(out).sort_values(ascending=False)
