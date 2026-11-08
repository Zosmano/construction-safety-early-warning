"""How much real site data is needed to measure the model's accuracy? A planning study.

Resamples whole sites from the simulated test period (Nov 2024 to Aug 2025, 71 sites) to see how
precisely each accuracy figure is pinned down with a given number of sites and months, and how
often the model would be shown to beat the crew-size baseline. Sites are resampled whole because
days on one site are not independent. The simulated sites stand in for real ones here: the study
says how much data a test needs, not what the result of that test would be.

    python analysis/sample_size.py            -> outputs/sample_size.csv, outputs/sample_size.png
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ssew import config as C  # noqa: E402

REPS = 300
SITES = [3, 5, 10, 20, 40, 71]
MONTHS = [3, 6, 10]
rng = np.random.default_rng(2026)

rows = pd.read_csv(ROOT / "outputs/risk_scores.csv", usecols=["site", "date", "y", "p", "p_base", "band"], parse_dates=["date"])
rows = rows[rows.date > C.TRAIN_END]
ev = pd.read_csv(ROOT / "outputs/test_events_warned.csv", parse_dates=["date"])
start = rows.date.min()
rows["m"] = (rows.date.dt.year - start.year) * 12 + rows.date.dt.month - start.month
ev["m"] = (ev.date.dt.year - start.year) * 12 + ev.date.dt.month - start.month
by_site = {s: g for s, g in rows.groupby("site")}
ev_site = {s: g for s, g in ev.groupby("site")}
sites = sorted(by_site)

out = []
for months in MONTHS:
    for n in SITES:
        res = []
        for _ in range(REPS):
            pick = rng.choice(sites, size=n, replace=True)
            r = pd.concat([by_site[s][by_site[s].m < months] for s in pick])
            e = pd.concat([ev_site[s][ev_site[s].m < months] for s in pick if s in ev_site]) if any(s in ev_site for s in pick) else ev.iloc[0:0]
            if r.y.nunique() < 2 or len(e) == 0:
                continue
            auc, base = roc_auc_score(r.y, r.p), roc_auc_score(r.y, r.p_base)
            red = r[r.band == "red"]
            res.append({"events": len(e), "auc": auc, "gain": auc - base, "capture": e.warned.mean(),
                        "red_lift": red.y.mean() / r.y.mean() if len(red) and r.y.mean() else np.nan})
        R = pd.DataFrame(res)
        q = lambda c, a: float(np.nanpercentile(R[c], a))
        out.append({"sites": n, "months": months, "site_months": n * months, "reps": len(R),
                    "events_median": int(R.events.median()),
                    "auc_low": q("auc", 2.5), "auc_high": q("auc", 97.5),
                    "gain_low": q("gain", 2.5), "gain_high": q("gain", 97.5),
                    "share_beats_baseline": float((R.gain > 0).mean()),
                    "capture_low": q("capture", 2.5), "capture_high": q("capture", 97.5),
                    "red_lift_low": q("red_lift", 2.5), "red_lift_high": q("red_lift", 97.5)})
        print(f"{n:>3} sites x {months:>2} months: {out[-1]['events_median']:>4} incidents  "
              f"AUC {out[-1]['auc_low']:.2f}-{out[-1]['auc_high']:.2f}  capture {out[-1]['capture_low']:.0%}-{out[-1]['capture_high']:.0%}  "
              f"beats crew-size baseline in {out[-1]['share_beats_baseline']:.0%}")
T = pd.DataFrame(out)
for c in ("auc", "gain", "capture", "red_lift"):
    T[f"{c}_width"] = T[f"{c}_high"] - T[f"{c}_low"]
T.round(4).to_csv(ROOT / "outputs/sample_size.csv", index=False)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
for ax, (lo, hi, lab) in zip(axes, [("capture_low", "capture_high", "Share of incidents warned in advance"),
                                     ("auc_low", "auc_high", "Ranking quality (AUC)")]):
    for months, col in zip(MONTHS, ["#9ec5f4", "#3987e5", "#184f95"]):
        t = T[T.months == months].sort_values("events_median")
        ax.fill_between(t.events_median, t[lo], t[hi], color=col, alpha=0.35, label=f"{months} months of logs")
    ax.set_xscale("log")
    ax.set_xlabel("Incidents in the real data (near misses and injuries)")
    ax.set_title(f"{lab}: 95% range", loc="left", fontsize=10)
    ax.spines[["top", "right"]].set_visible(False)
axes[0].legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(ROOT / "outputs/sample_size.png", dpi=150)
