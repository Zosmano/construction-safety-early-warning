"""A real-outcome check on public New York City records (NYC Open Data, Department of Buildings).

Real site logs from contractors are not public, so the zone model cannot be tested on real data directly. This
module tests the same idea on real sites instead: do the warning signs a regulator already records at a site
(construction and site-safety violations, crane violations, construction complaints, earlier incidents) flag the
sites that go on to have a construction accident or incident in the next four weeks, better than job size alone?

    Unit      one active construction site (building ID, BIN) in one week
    Sites     buildings with an active DOB NOW permit for structural, foundation, earthwork, excavation support,
              demolition, scaffold or larger general construction work (estimated cost of $500,000 or more)
    Signals   trailing 4 and 13 weeks of ECB violations (construction, site safety, cranes and derricks), DOB
              complaints in construction categories, and incidents in the past year
    Outcome   a DOB-recorded construction accident or incident at the site in the next 4 weeks
    Test      trained on weeks before 2025-07-01, tested on later weeks
"""
import gzip
import io
import json
import time
import urllib.parse
import urllib.request

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score

from . import config as C

RAW = C.ROOT / "data" / "raw" / "nyc"
API = "https://data.cityofnewyork.us/resource/{}.csv?"
SOURCES = {
    "incidents": ("bf97-mjsy", "Construction-Related Incidents"),
    "permits": ("rbx6-tga4", "DOB NOW: Build – Approved Permits"),
    "ecb": ("6bgk-3dad", "DOB ECB Violations"),
    "complaints": ("eabe-havv", "DOB Complaints Received"),
}
START, SPLIT, END = "2024-01-01", "2025-07-01", "2026-09-28"     # weeks scored; train/test split; last week with a full 4-week outcome
HORIZON_W = 4
HEAVY = ["Foundation", "Earth Work", "Support of Excavation", "Full Demolition", "Structural", "Supported Scaffold",
         "Suspended Scaffold", "Protection and Mechanical Methods"]
# DOB complaint categories about site safety or unauthorised construction work
CMP_UNSAFE = {"03": "Adjacent building not protected", "09": "Excessive debris", "10": "Debris or building falling",
              "23": "Sidewalk shed or scaffold defective", "30": "Building shaking or structural stability",
              "91": "Site conditions endangering workers"}
CMP_ILLEGAL = {"04": "After-hours work", "05": "Work without a permit", "83": "Work contrary to plans or permits",
               "86": "Work contrary to a stop work order"}


def _fetch(ds, params, path, page=50000):
    """Page through a Socrata dataset into a gzipped CSV."""
    out, off = [], 0
    while True:
        p = dict(params, **{"$limit": page, "$offset": off, "$order": ":id"})
        for k in range(4):
            try:
                txt = urllib.request.urlopen(urllib.request.Request(API.format(ds) + urllib.parse.urlencode(p),
                                                                    headers={"User-Agent": "ssew-research"}), timeout=300).read().decode("utf-8")
                break
            except Exception:
                if k == 3:
                    raise
                time.sleep(5 * (k + 1))
        df = pd.read_csv(io.StringIO(txt), dtype=str)
        out.append(df)
        print(f"  {path.name}: {off + len(df):,} rows")
        if len(df) < page:
            break
        off += page
    df = pd.concat(out, ignore_index=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        df.to_csv(f, index=False)
    return df


def download():
    RAW.mkdir(parents=True, exist_ok=True)
    _fetch(SOURCES["incidents"][0], {"$select": "bin,accident_report_id,incident_date_mm_dd_yyyy,record_type_description,check2_description,fatality,injury,boro"},
           RAW / "incidents.csv.gz")
    _fetch(SOURCES["permits"][0], {"$select": "bin,work_type,issued_date,expired_date,estimated_job_costs,borough,filing_reason",
                                   "$where": "issued_date >= '2022-07-01' AND issued_date < '2026-10-01'"}, RAW / "permits.csv.gz")
    _fetch(SOURCES["ecb"][0], {"$select": "bin,issue_date,violation_type,severity",
                               "$where": "issue_date >= '20230101' AND violation_type in ('Construction','Site Safety','Cranes and Derricks')"},
           RAW / "ecb.csv.gz")
    cats = ",".join(f"'{c}'" for c in list(CMP_UNSAFE) + list(CMP_ILLEGAL))
    frames = []
    for y in range(2023, 2027):      # date_entered is text (MM/DD/YYYY), so filter year by year
        frames.append(_fetch(SOURCES["complaints"][0], {"$select": "bin,date_entered,complaint_category",
                                                        "$where": f"date_entered like '%/{y}' AND complaint_category in ({cats})"},
                             RAW / f"complaints_{y}.csv.gz"))


def load():
    rd = lambda n: pd.read_csv(RAW / n, dtype=str)
    inc = rd("incidents.csv.gz")
    inc["date"] = pd.to_datetime(inc.incident_date_mm_dd_yyyy.str[:10], errors="coerce")
    inc = inc[inc.record_type_description.isin(["Accident", "Incident"]) & inc.date.notna()]
    per = rd("permits.csv.gz")
    per["start"] = pd.to_datetime(per.issued_date.str[:10], errors="coerce")
    per["end"] = pd.to_datetime(per.expired_date.str[:10], errors="coerce")
    per["cost"] = pd.to_numeric(per.estimated_job_costs, errors="coerce").fillna(0)
    ecb = rd("ecb.csv.gz")
    ecb["date"] = pd.to_datetime(ecb.issue_date, format="%Y%m%d", errors="coerce")
    cmp = pd.concat([rd(f"complaints_{y}.csv.gz") for y in range(2023, 2027)], ignore_index=True)
    cmp["date"] = pd.to_datetime(cmp.date_entered, format="%m/%d/%Y", errors="coerce")
    for d in (inc, per, ecb, cmp):
        d["bin"] = pd.to_numeric(d.bin, errors="coerce")
    bad_bin = lambda s: s.isna() | (s % 1000000 == 0)      # placeholder BINs (e.g. 1000000) are not real buildings
    return (inc[~bad_bin(inc.bin)], per[~bad_bin(per.bin) & per.start.notna()], ecb[~bad_bin(ecb.bin) & ecb.date.notna()],
            cmp[~bad_bin(cmp.bin) & cmp.date.notna()])


def panel(inc, per, ecb, cmp):
    """One row per active site-week with exposure, trailing warning signals and the 4-week outcome."""
    weeks = pd.date_range(pd.Timestamp(START) - pd.Timedelta(weeks=60), END, freq="W-MON")
    wk = lambda s: s.dt.to_period("W-SUN").dt.start_time
    per = per[(per.work_type.isin(HEAVY)) | ((per.work_type == "General Construction") & (per.cost >= 500000))].copy()
    per["end"] = per.end.fillna(per.start + pd.Timedelta(days=365)).clip(upper=per.start + pd.Timedelta(days=730))
    per["w0"], per["w1"] = wk(per.start), wk(per.end)
    # active weeks per site, with exposure: active permits, heavy work types, largest job cost
    n = (((per.w1 - per.w0).dt.days // 7) + 1).clip(lower=1).to_numpy()
    off = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    act = pd.DataFrame({"bin": np.repeat(per.bin.to_numpy(), n), "week": np.repeat(per.w0.to_numpy(), n) + pd.to_timedelta(off * 7, unit="D"),
                        "work_type": np.repeat(per.work_type.to_numpy(), n), "cost": np.repeat(per.cost.to_numpy(), n)})
    act = act[(act.week >= START) & (act.week <= END)]
    X = act.groupby(["bin", "week"]).agg(permits=("work_type", "size"), work_types=("work_type", "nunique"),
                                         cost=("cost", "max")).reset_index()
    for t in ["Foundation", "Earth Work", "Support of Excavation", "Full Demolition", "Structural", "Supported Scaffold", "Suspended Scaffold"]:
        k = act[act.work_type == t].groupby(["bin", "week"]).size().rename("wt_" + t.lower().replace(" ", "_"))
        X = X.join(k, on=["bin", "week"])
    X = X.fillna(0)
    X["log_cost"] = np.log1p(X.cost)
    X["boro"] = X.bin // 1000000
    # weekly counts per site for each signal, then trailing sums
    sig = {"ecb_construction": ecb[ecb.violation_type == "Construction"], "ecb_site_safety": ecb[ecb.violation_type == "Site Safety"],
           "ecb_cranes": ecb[ecb.violation_type == "Cranes and Derricks"],
           "ecb_hazardous": ecb[ecb.severity.fillna("").str.contains("Hazard|CLASS - 1", case=False)],
           "cmp_unsafe": cmp[cmp.complaint_category.isin(CMP_UNSAFE)], "cmp_illegal": cmp[cmp.complaint_category.isin(CMP_ILLEGAL)],
           "incidents": inc}
    sites = X.bin.unique()
    for name, d in sig.items():
        d = d[d.bin.isin(sites)]
        c = d.assign(week=wk(d.date)).groupby(["bin", "week"]).size()
        full = c.unstack(fill_value=0).reindex(columns=weeks, fill_value=0)
        for n in ([4, 13] if name != "incidents" else [52]):
            roll = full.T.rolling(n, min_periods=1).sum().T.stack().rename(f"{name}_{n}w")
            roll.index.names = ["bin", "week"]
            X = X.join(roll, on=["bin", "week"])
        if name == "incidents":                 # outcome: an incident in weeks t+1 .. t+4
            fwd = full.T[::-1].rolling(HORIZON_W, min_periods=1).sum()[::-1].shift(-1).T.stack().rename("y_count")
            fwd.index.names = ["bin", "week"]
            X = X.join(fwd, on=["bin", "week"])
    X = X.fillna(0)
    X["y"] = (X.y_count > 0).astype(int)
    X["new_permit_4w"] = X.groupby("bin").permits.diff().fillna(0).clip(lower=0)
    return X, inc[inc.bin.isin(sites)], inc


EXPOSURE = ["permits", "work_types", "log_cost", "boro", "wt_foundation", "wt_earth_work", "wt_support_of_excavation",
            "wt_full_demolition", "wt_structural", "wt_supported_scaffold", "wt_suspended_scaffold", "new_permit_4w"]
SIGNALS = ["ecb_construction_4w", "ecb_construction_13w", "ecb_site_safety_4w", "ecb_site_safety_13w", "ecb_cranes_4w", "ecb_cranes_13w",
           "ecb_hazardous_4w", "ecb_hazardous_13w", "cmp_unsafe_4w", "cmp_unsafe_13w", "cmp_illegal_4w", "cmp_illegal_13w", "incidents_52w"]
GROUP = {"Construction violations": ["ecb_construction_4w", "ecb_construction_13w", "ecb_hazardous_4w", "ecb_hazardous_13w"],
         "Site-safety violations": ["ecb_site_safety_4w", "ecb_site_safety_13w"], "Crane violations": ["ecb_cranes_4w", "ecb_cranes_13w"],
         "Unsafe-site complaints": ["cmp_unsafe_4w", "cmp_unsafe_13w"], "Unauthorised-work complaints": ["cmp_illegal_4w", "cmp_illegal_13w"],
         "Incident in the past year": ["incidents_52w"], "Job size and type": EXPOSURE}


def evaluate(X):
    tr, te = X[X.week < SPLIT], X[X.week >= SPLIT]
    F = EXPOSURE + SIGNALS
    gb = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=200,
                                        l2_regularization=1.0, random_state=0).fit(tr[F], tr.y)
    base = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=200,
                                          l2_regularization=1.0, random_state=0).fit(tr[EXPOSURE], tr.y)
    X = X.assign(p=gb.predict_proba(X[F])[:, 1], p_base=base.predict_proba(X[EXPOSURE])[:, 1])
    p_tr = X.loc[X.week < SPLIT, "p"]
    red, amber = np.quantile(p_tr, 0.95), np.quantile(p_tr, 0.80)
    X["band"] = np.where(X.p >= red, "red", np.where(X.p >= amber, "amber", "green"))
    te = X[X.week >= SPLIT]
    out = {"sites": int(X.bin.nunique()), "site_weeks": int(len(X)), "test_site_weeks": int(len(te)),
           "test_base_rate": float(te.y.mean()), "auc": float(roc_auc_score(te.y, te.p)), "auc_base": float(roc_auc_score(te.y, te.p_base)),
           "ap": float(average_precision_score(te.y, te.p)), "ap_base": float(average_precision_score(te.y, te.p_base)),
           "thresholds": {"red": float(red), "amber": float(amber)}}
    by = te.groupby("band").agg(rows=("y", "size"), rate=("y", "mean"))
    by["share"] = by.rows / by.rows.sum()
    by["lift"] = by.rate / te.y.mean()
    out["bands"] = by.reindex(["red", "amber", "green"]).reset_index().to_dict("records")
    # the same rule for the base-only model, for a like-for-like comparison of flagged incidents
    pb_tr = X.loc[X.week < SPLIT, "p_base"]
    rb, ab = np.quantile(pb_tr, 0.95), np.quantile(pb_tr, 0.80)
    X["band_base"] = np.where(X.p_base >= rb, "red", np.where(X.p_base >= ab, "amber", "green"))
    smp = te.sample(min(60000, len(te)), random_state=0)
    imp = permutation_importance(gb, smp[F], smp.y, scoring="roc_auc", n_repeats=3, random_state=0)
    gi = {g: 0.0 for g in GROUP}
    for f, v in zip(F, imp.importances_mean):
        for g, fs in GROUP.items():
            if f in fs:
                gi[g] += float(v)
    out["importance"] = dict(sorted(gi.items(), key=lambda kv: -kv[1]))
    return X, out


def warned(X, inc, split=SPLIT):
    """Each test-period incident at a scored site: was the site amber or red in any of the 4 weeks before?"""
    key = X.set_index(["bin", "week"])[["band", "band_base", "p"]]
    ev = inc[(inc.date >= split) & (inc.date < pd.Timestamp(END) + pd.Timedelta(weeks=HORIZON_W))].copy()
    ev["week"] = ev.date.dt.to_period("W-SUN").dt.start_time
    res = []
    for r in ev.itertuples():
        prior = [r.week - pd.Timedelta(weeks=k) for k in range(1, HORIZON_W + 1)]
        b = [key.loc[(r.bin, w)] for w in prior if (r.bin, w) in key.index]
        res.append({"date": r.date.strftime("%Y-%m-%d"), "bin": int(r.bin), "type": r.record_type_description, "what": r.check2_description,
                    "injury": int(float(r.injury or 0)) > 0, "fatal": int(float(r.fatality or 0)) > 0, "scored": bool(b),
                    "warned": any(x.band != "green" for x in b), "warned_base": any(x.band_base != "green" for x in b),
                    "red": any(x.band == "red" for x in b)})
    return pd.DataFrame(res)


def run():
    inc, per, ecb, cmp = load()
    X, inc_s, inc_all = panel(inc, per, ecb, cmp)
    X, out = evaluate(X)
    w = warned(X, inc_s)
    tested = w[w.scored]
    test_inc = inc_all[(inc_all.date >= SPLIT) & (inc_all.date < pd.Timestamp(END) + pd.Timedelta(weeks=HORIZON_W))]
    out.update({"incidents_all_test": int(len(test_inc)), "incidents_scored_test": int(len(tested)),
                "coverage": float(len(tested) / max(1, len(test_inc))),
                "warned_share": float(tested.warned.mean()), "warned_share_base": float(tested.warned_base.mean()),
                "red_share": float(tested.red.mean()),
                "warned_injury_share": float(tested[tested.injury].warned.mean()) if tested.injury.any() else None,
                "warned_by_type": tested.groupby("what").warned.agg(["mean", "size"]).sort_values("size", ascending=False).reset_index().to_dict("records"),
                "split": SPLIT, "start": START, "end": END, "horizon_weeks": HORIZON_W,
                "alerts_per_100_site_weeks": {"red": float((X[X.week >= SPLIT].band == "red").mean() * 100),
                                              "amber": float((X[X.week >= SPLIT].band == "amber").mean() * 100)},
                "sources": {k: {"id": v[0], "name": v[1], "url": f"https://data.cityofnewyork.us/d/{v[0]}"} for k, v in SOURCES.items()}})
    # the sharper test: among the jobs that size and type alone already flag (amber or red on the base model), do the
    # warning signals still separate the sites that go on to have an incident?
    te = X[X.week >= SPLIT]
    big = te[te.band_base != "green"]
    out["within_large_jobs"] = {"site_weeks": int(len(big)), "base_rate": float(big.y.mean()),
                                "auc": float(roc_auc_score(big.y, big.p)), "auc_base": float(roc_auc_score(big.y, big.p_base))}
    rates = []
    for g, fs in GROUP.items():
        if g == "Job size and type":
            continue
        on = big[fs].sum(axis=1) > 0
        if on.sum() >= 200:
            rates.append({"signal": g, "share_with": float(on.mean()), "rate_with": float(big[on].y.mean()), "rate_without": float(big[~on].y.mean()),
                          "ratio": float(big[on].y.mean() / big[~on].y.mean()) if big[~on].y.mean() else None})
    out["signal_rates_large_jobs"] = sorted(rates, key=lambda r: -(r["ratio"] or 0))
    # monthly incidents vs alerts, for a chart
    m = te.assign(m=te.week.dt.strftime("%Y-%m")).groupby("m").agg(red=("band", lambda s: int((s == "red").sum())), site_weeks=("y", "size"))
    mi = tested.assign(m=tested.date.str[:7]).groupby("m").agg(incidents=("warned", "size"), warned=("warned", "sum"))
    out["monthly"] = m.join(mi).fillna(0).reset_index().to_dict("records")
    C.OUT.mkdir(parents=True, exist_ok=True)
    (C.OUT / "nyc_check.json").write_text(json.dumps(out, indent=1, default=float))
    w.to_csv(C.OUT / "nyc_test_incidents_warned.csv", index=False)
    print(json.dumps({k: v for k, v in out.items() if k not in ("monthly", "warned_by_type", "sources", "bands")}, indent=1, default=float))
    return out


if __name__ == "__main__":
    import sys
    if "--download" in sys.argv:
        download()
    run()
