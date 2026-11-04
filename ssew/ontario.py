"""A model trained on real Canadian records: Ontario's Ministry of Labour field visits and orders, construction, 2012-2024.

The ministry publishes every closed field visit: date, workplace, case type, and each order with the regulation section it cites.
Contractors' daily logs aren't public, but an inspection is a real outside look at a real site on a known date.

The question: at the end of an inspection, what is the chance the same workplace has a ministry *investigation* in the next 90 days? Investigations follow complaints, work refusals, critical injuries and other events. They are a proxy for
trouble on site, not a count of injuries, and inspectors choose where they go, so results describe inspected workplaces only.
Trained on 2012-2020, judged on 2021-2024, against yardsticks of project type, region and season, then those plus size.
Names in the source are never used: only the ministry's ID numbers.
"""
import json
import re
import urllib.request

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from . import config as C

RAW = C.RAW / "ontario"
HORIZON = 90
TRAIN_END = "2020-12-31"
# O. Reg. 213/91 sections -> hazard category (Part II general, Part II.1 fall protection, Part III excavations and so on)
CATS = [("Falls and guardrails", [(26, 27.99)]), ("Ladders and access", [(70, 86.99)]), ("Scaffolds and platforms", [(125, 149.99)]),
        ("PPE", [(21, 25.99)]), ("Housekeeping and storage", [(35, 46.99)]), ("Traffic and vehicles", [(67, 69.99), (93, 110.99)]),
        ("Cranes and hoisting", [(150, 180.99)]), ("Electrical", [(181, 195.99)]), ("Excavation", [(222, 242.99)]),
        ("Formwork and structure", [(87, 92.99), (56, 62.99)]), ("Other sections", [(0, 9999)])]
CAT_NAMES = [c[0] for c in CATS]
SLUG = lambda s: "o_" + re.sub(r"[^a-z]+", "_", s.lower()).strip("_")
FEATS_LOG = [SLUG(c) for c in CAT_NAMES] + ["stop_orders", "forthwith_orders", "orders_total", "training_orders", "prior_inspections_wp", "prior_inv_wp",
                                            "prior_orders_con", "prior_stops_con", "prior_inv_con", "con_known"]
FEATS_CTX = ["naics_236", "naics_237", "naics_238", "month", "gta", "north"]
FEATS_SIZE = ["prior_visits_con", "prior_inspections_wp"]         # how much the ministry already sees of this constructor and site: a size proxy
FEATURES = FEATS_LOG + FEATS_CTX + ["prior_visits_con"]


def _dates(s, name):
    """Files use mm/dd/yyyy, yyyy-mm-dd or timestamps; a few years could be read two ways, so test which reading is valid."""
    s = s.astype(str).str.strip()
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    out[iso] = pd.to_datetime(s[iso].str[:10], errors="coerce")
    rest = s[~iso]
    if len(rest):
        a = pd.to_datetime(rest, format="%m/%d/%Y", errors="coerce")
        b = pd.to_datetime(rest, format="%d/%m/%Y", errors="coerce")
        out[~iso] = a if a.notna().sum() >= b.notna().sum() else b
    return out


def load():
    fr = []
    for p in sorted(RAW.glob("con_*.csv.gz")):
        d = pd.read_csv(p, dtype=str, low_memory=False)
        d.columns = [c.strip() for c in d.columns]
        ren = {}
        for c in d.columns:
            if c.startswith("CONTRAVENER") and "ID" in c:
                ren[c] = "CON"
            if c.startswith("WORKPLACE ADDRESS") or c == "WORKPLACE LOCATION" or c.startswith("WORKPLACE ADDRESSS"):
                ren[c] = "ADDR"
            if c in ("ACT-REGULATION NAME", "REG NAME"):
                ren[c] = "REG"
        d = d.rename(columns=ren)
        keep = ["FIELD VISIT DATE", "FIELD VISIT TYPE", "CASE TYPE", "WORKPLACE ID", "POSTAL CODE", "PRIMARY NAICS", "CON", "CONTRAVENER ROLE", "ORDER TYPE", "ORDER STATUS", "REG", "SEC"]
        d = d.reindex(columns=keep)
        d["date"] = _dates(d["FIELD VISIT DATE"], p.name)
        d["file"] = int(p.name[4:8])
        fr.append(d.drop(columns="FIELD VISIT DATE"))
    D = pd.concat(fr, ignore_index=True)
    D = D[D.date.dt.year == D.file]                    # a date outside its file's year means it was misread
    for c in ("ORDER TYPE", "CASE TYPE", "FIELD VISIT TYPE", "CONTRAVENER ROLE", "REG"):
        D[c] = D[c].str.strip()
    return D


def _cat(reg, sec):
    if not isinstance(reg, str) or "CONSTRUCTION PROJECT" not in reg.upper():
        return None
    m = re.match(r"\s*(\d+(?:\.\d+)?)", str(sec))
    if not m:
        return "Other sections"
    v = float(m.group(1))
    return next(n for n, rng in CATS if any(a <= v <= b for a, b in rng))


def visits(D):
    """One row per workplace-day-case visit, with its orders counted by hazard category."""
    D = D.copy()
    D["cat"] = [_cat(r, s) for r, s in zip(D.REG, D.SEC)]
    has = D["ORDER TYPE"].notna()
    t = D["ORDER TYPE"].fillna("").str.lower()
    D["stop"] = has & t.str.contains("stop")
    D["forth"] = has & t.str.contains("forthwith")
    D["train"] = has & D.REG.fillna("").str.contains("TRAINING", case=False)
    key = ["WORKPLACE ID", "date", "CASE TYPE", "FIELD VISIT TYPE"]
    g = D.groupby(key, sort=False)
    v = g.agg(orders_total=("ORDER TYPE", "count"), stop_orders=("stop", "sum"), forthwith_orders=("forth", "sum"), training_orders=("train", "sum"),
              naics=("PRIMARY NAICS", "first"), postal=("POSTAL CODE", "first")).reset_index()
    cats = D[D.cat.notna()].groupby(key + ["cat"]).size().unstack(fill_value=0).reindex(columns=CAT_NAMES, fill_value=0)
    cats.columns = [SLUG(c) for c in CAT_NAMES]
    v = v.merge(cats.reset_index(), on=key, how="left")
    v[[SLUG(c) for c in CAT_NAMES]] = v[[SLUG(c) for c in CAT_NAMES]].fillna(0)
    # the constructor named on the visit's orders, if any
    con = D[D["CONTRAVENER ROLE"].eq("Constructor") & D.CON.notna()].groupby(key).CON.first().rename("con").reset_index()
    return v.merge(con, on=key, how="left").sort_values("date").reset_index(drop=True)


def _rolling_prior(ev, key, val, days, query):
    """For each query row: the sum of val for the same key in the `days` before its date (the same day excluded)."""
    out = np.zeros(len(query))
    by = {k: (g.date.values, np.cumsum(g[val].values)) for k, g in ev.groupby(key)}
    w = np.timedelta64(days, "D")
    for i, (k, d) in enumerate(zip(query[key].values, query.date.values)):
        h = by.get(k)
        if h is None:
            continue
        ds, cs = h
        hi = np.searchsorted(ds, d, "left") - 1
        lo = np.searchsorted(ds, d - w, "left") - 1
        if hi >= 0:
            out[i] = cs[hi] - (cs[lo] if lo >= 0 else 0)
    return out


def frame(v):
    """Rows: first-time and repeat *inspections*; features known by the end of that day; target: a later investigation."""
    v = v.copy()
    v["is_inv"] = (v["CASE TYPE"] == "Investigation").astype(int)
    v["is_insp"] = (v["CASE TYPE"] == "Inspection").astype(int)
    q = v[(v["CASE TYPE"] == "Inspection") & (v["FIELD VISIT TYPE"] == "Initial")].copy().reset_index(drop=True)
    wid = v[["WORKPLACE ID", "date", "is_inv", "is_insp"]].groupby(["WORKPLACE ID", "date"], as_index=False).sum().sort_values("date")
    q["prior_inspections_wp"] = _rolling_prior(wid, "WORKPLACE ID", "is_insp", 365, q)
    q["prior_inv_wp"] = _rolling_prior(wid, "WORKPLACE ID", "is_inv", 365, q)
    # constructor history and future, across all of its workplaces
    c = v[v.con.notna()]
    links = v[v.con.notna()].groupby("WORKPLACE ID").con.first()
    v["con2"] = v.con.fillna(v["WORKPLACE ID"].map(links))
    cev = v[v.con2.notna()].assign(n=1).groupby(["con2", "date"], as_index=False).agg(orders=("orders_total", "sum"), stops=("stop_orders", "sum"), inv=("is_inv", "sum"), visits=("n", "sum")).sort_values("date")
    # only what is known by the visit: its own constructor; otherwise unknown
    q["con2"] = q.con
    q["con_known"] = q.con2.notna().astype(float)
    qc = q[q.con2.notna()].copy()
    for name, col in (("prior_orders_con", "orders"), ("prior_stops_con", "stops"), ("prior_inv_con", "inv"), ("prior_visits_con", "visits")):
        q[name] = 0.0
        q.loc[qc.index, name] = _rolling_prior(cev, "con2", col, 365, qc)
    # target: an investigation at the workplace, or anywhere for that constructor, in the next HORIZON days
    def future(ev, key, val, qq):
        out = np.zeros(len(qq), dtype=bool)
        by = {k: g.date.values[g[val].values > 0] for k, g in ev.groupby(key)}
        w = np.timedelta64(HORIZON, "D")
        for i, (k, d) in enumerate(zip(qq[key].values, qq.date.values)):
            ds = by.get(k)
            if ds is None or not len(ds):
                continue
            j = np.searchsorted(ds, d, "right")
            out[i] = j < len(ds) and ds[j] <= d + w
        return out
    q["y_wp"] = future(wid, "WORKPLACE ID", "is_inv", q)
    q["y_con"] = False
    q.loc[qc.index, "y_con"] = future(cev, "con2", "inv", qc)
    q["y"] = (q.y_wp | q.y_con).astype(int)
    q["y_site"] = q.y_wp.astype(int)
    q["naics_236"] = q.naics.astype(str).str.startswith("236").astype(float)
    q["naics_237"] = q.naics.astype(str).str.startswith("237").astype(float)
    q["naics_238"] = q.naics.astype(str).str.startswith("238").astype(float)
    q["month"] = q.date.dt.month.astype(float)
    fsa = q.postal.astype(str).str.upper().str.replace(" ", "")
    q["gta"] = fsa.str[0].isin(list("ML")).astype(float)
    q["north"] = fsa.str[0].eq("P").astype(float)
    # the last HORIZON days of the record can't be judged yet
    return q[q.date <= q.date.max() - pd.Timedelta(days=HORIZON)].reset_index(drop=True)


def fit(q, target="y_site"):
    """The main model: an investigation at this same workplace within HORIZON days. Yardsticks: project type, region and season
    alone, and those plus size (how often the ministry has already visited this constructor and workplace)."""
    tr, te = q[q.date <= TRAIN_END], q[q.date > TRAIN_END]
    y_tr, y = tr[target], te[target].values
    gb = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200, l2_regularization=1.0, random_state=0)
    gb.fit(tr[FEATURES], y_tr)
    tree = lambda: HistGradientBoostingClassifier(max_iter=150, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=200, random_state=0)
    base = tree().fit(tr[FEATS_CTX], y_tr)
    size = tree().fit(tr[FEATS_CTX + FEATS_SIZE], y_tr)
    p = gb.predict_proba(te[FEATURES])[:, 1]
    pb, ps = base.predict_proba(te[FEATS_CTX])[:, 1], size.predict_proba(te[FEATS_CTX + FEATS_SIZE])[:, 1]
    ptr = gb.predict_proba(tr[FEATURES])[:, 1]                    # alert bands set on training inspections only
    red, amber = float(np.quantile(ptr, .9)), float(np.quantile(ptr, .7))
    b = np.where(p >= red, "red", np.where(p >= amber, "amber", "green"))
    bands = [{"band": k, "share": float((b == k).mean()), "rate": float(y[b == k].mean()), "lift": float(y[b == k].mean() / y.mean()), "caught": float(y[b == k].sum() / y.sum())}
             for k in ("red", "amber", "green")]
    yrs = te.date.dt.year.values
    by_year = [{"year": int(k), "n": int((yrs == k).sum()), "auc": float(roc_auc_score(y[yrs == k], p[yrs == k])), "rate": float(y[yrs == k].mean())} for k in sorted(set(yrs))]
    new = (te.prior_inspections_wp.values + te.prior_inv_wp.values + te.prior_visits_con.values) == 0
    res = {"target": target, "train_rows": int(len(tr)), "test_rows": int(len(te)), "test_rate": float(y.mean()), "train_rate": float(y_tr.mean()),
           "auc": float(roc_auc_score(y, p)), "auc_base": float(roc_auc_score(y, pb)), "auc_size": float(roc_auc_score(y, ps)),
           "ap": float(average_precision_score(y, p)), "ap_base": float(average_precision_score(y, pb)), "ap_size": float(average_precision_score(y, ps)),
           "auc_first_look": float(roc_auc_score(y[new], p[new])) if new.sum() > 100 and y[new].sum() > 10 else None, "first_look_rows": int(new.sum()),
           "red": red, "amber": amber, "bands": bands, "by_year": by_year}
    d = pd.DataFrame({"p": p, "y": y})
    d["dec"] = pd.qcut(d.p.rank(method="first"), 10, labels=False)
    res["calibration"] = d.groupby("dec").agg(pred=("p", "mean"), obs=("y", "mean")).reset_index().to_dict("records")
    return gb, res, te.assign(p=p, pb=pb, y=y)

def group_effects(gb, te):
    """Test-period AUC lost when each feature group is shuffled."""
    rng = np.random.default_rng(0)
    y, base = te.y, roc_auc_score(te.y, gb.predict_proba(te[FEATURES])[:, 1])
    groups = {"Constructor's record (12 months)": ["prior_orders_con", "prior_stops_con", "prior_inv_con", "prior_visits_con", "con_known"],
              "This workplace's record (12 months)": ["prior_inspections_wp", "prior_inv_wp"],
              "Orders on this visit": [SLUG(c) for c in CAT_NAMES] + ["stop_orders", "forthwith_orders", "orders_total", "training_orders"],
              "Project type, region, season": FEATS_CTX}
    out = {}
    for n, cols in groups.items():
        X = te[FEATURES].copy()
        X[cols] = X[cols].values[rng.permutation(len(X))]
        out[n] = float(base - roc_auc_score(y, gb.predict_proba(X)[:, 1]))
    return out


def signs(q):
    """On unseen years: how much more often an investigation followed when an order category was present. Unadjusted."""
    te = q[q.date > TRAIN_END].assign(y=lambda d: d.y_site)
    out = []
    for c in CAT_NAMES + ["stop_orders"]:
        col = SLUG(c) if c in CAT_NAMES else c
        a, b = te[te[col] > 0], te[te[col] == 0]
        if len(a) >= 100:
            out.append({"sign": "Stop-work order" if c == "stop_orders" else c, "n": int(len(a)), "with": float(a.y.mean()), "without": float(b.y.mean()), "ratio": float(a.y.mean() / b.y.mean())})
    return sorted(out, key=lambda r: -r["ratio"])


def order_mix(D):
    """Which hazards inspectors cite on construction projects, all years, and how orders vary by month."""
    d = D[D["ORDER TYPE"].notna()].copy()
    d["cat"] = [_cat(r, s) for r, s in zip(d.REG, d.SEC)]
    m = d.cat.value_counts(normalize=True)
    month = D.drop_duplicates(["WORKPLACE ID", "date", "CASE TYPE"]).groupby(D.date.dt.month)["CASE TYPE"].value_counts().unstack(fill_value=0)
    return {"mix": m.to_dict(), "orders": int(len(d)), "by_month": {"inspection": month["Inspection"].to_dict(), "investigation": month["Investigation"].to_dict()}}


def weather_effect(v):
    """Do investigations opened at Toronto-area sites rise with the weather? Daily counts, 2012-2024 work days, against Toronto Pearson
    daily weather from the Open-Meteo archive, with year, month and weekday controls. Unit: rate ratio on the day and the next work day."""
    p = RAW / "toronto_daily_2012_2024.json"
    if not p.exists():
        u = ("https://archive-api.open-meteo.com/v1/archive?latitude=43.68&longitude=-79.63&start_date=2012-01-01&end_date=2024-12-31"
             "&daily=temperature_2m_min,apparent_temperature_max,wind_gusts_10m_max,precipitation_sum,snowfall_sum&timezone=America/Toronto")
        p.write_bytes(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "site-safety-early-warning/1.0"}), timeout=180).read())
    j = json.loads(p.read_text())["daily"]
    w = pd.DataFrame(j)
    w["date"] = pd.to_datetime(w.time)
    fsa = v.postal.astype(str).str.upper().str[0]
    inv = v[(v["CASE TYPE"] == "Investigation") & (v["FIELD VISIT TYPE"] == "Initial") & fsa.isin(list("ML"))].groupby("date").size().rename("n")
    d = w.merge(inv, on="date", how="left").fillna({"n": 0})
    d = d[d.date.dt.year != 2019]                      # the 2019 file is only a fragment of the year
    d = d[d.date.dt.dayofweek < 5]
    d["wet"] = (d.precipitation_sum >= 5).astype(float)
    d["freeze"] = ((d.temperature_2m_min <= C.FREEZE_C) | (d.snowfall_sum > 0)).astype(float)
    d["heat"] = (d.apparent_temperature_max >= C.HUMIDEX_HEAT).astype(float)
    d["wind"] = (d.wind_gusts_10m_max >= C.CRANE_GUST_KMH).astype(float)
    d["cold"] = (d.apparent_temperature_max <= -15).astype(float)
    import statsmodels.api as sm
    X = pd.concat([d[["wet", "freeze", "heat", "wind", "cold"]], pd.get_dummies(d.date.dt.year, prefix="y", drop_first=True).astype(float),
                   pd.get_dummies(d.date.dt.month, prefix="m", drop_first=True).astype(float), pd.get_dummies(d.date.dt.dayofweek, prefix="d", drop_first=True).astype(float)], axis=1)
    m = sm.GLM(d.n, sm.add_constant(X), family=sm.families.Poisson()).fit(cov_type="HC1")
    ci = m.conf_int()
    return {k: {"ratio": float(np.exp(m.params[k])), "low": float(np.exp(ci.loc[k, 0])), "high": float(np.exp(ci.loc[k, 1])), "days": int(d[k].sum())} for k in ("wet", "freeze", "heat", "wind", "cold")} | {"days": int(len(d)), "events": int(d.n.sum())}


def export(gb):
    trees = []
    for it in gb._predictors:
        nodes = it[0].nodes
        trees.append([[int(n["feature_idx"]), round(float(n["num_threshold"]), 4), int(n["left"]), int(n["right"]), int(n["missing_go_to_left"]),
                       round(float(n["value"]), 5) if n["is_leaf"] else None] for n in nodes])
    return {"features": FEATURES, "baseline": float(np.ravel(gb._baseline_prediction)[0]), "trees": trees}


def run():
    D = load()
    print(f"Ontario: {len(D):,} rows, {D['WORKPLACE ID'].nunique():,} workplaces, {D.date.min().date()} to {D.date.max().date()}", D.groupby("file").size().to_dict(), flush=True)
    v = visits(D)
    q = frame(v)
    gb, res, te = fit(q)
    res["constructor_wide"] = {k: v for k, v in fit(q, "y")[1].items() if k in ("auc", "auc_base", "auc_size", "test_rate", "bands")}
    res["rows_source"] = int(len(D))
    res["workplaces"] = int(D["WORKPLACE ID"].nunique())
    res["orders"] = int(D["ORDER TYPE"].notna().sum())
    res["investigations"] = int(((v["CASE TYPE"] == "Investigation") & (v["FIELD VISIT TYPE"] == "Initial")).sum())
    res["inspections"] = int(len(q))
    res["from"], res["to"] = D.date.min().strftime("%Y-%m-%d"), D.date.max().strftime("%Y-%m-%d")
    res["groups"] = group_effects(gb, te)
    res["signs"] = signs(q)
    res["mix"] = order_mix(D)
    try:
        res["weather"] = weather_effect(v)
    except Exception as e:
        print("weather effect skipped:", repr(e)[:200])
    res["by_file"] = {int(k): int(n) for k, n in D.groupby("file").size().items()}
    res["model"] = export(gb)
    res["medians"] = {f: float(q[f].median()) for f in FEATURES}
    (C.OUT / "ontario_check.json").write_text(json.dumps(res, default=float))
    print(json.dumps({k: v for k, v in res.items() if k not in ("model", "calibration", "medians", "by_file")}, indent=0, default=float)[:5000])
    return res


if __name__ == "__main__":
    run()
