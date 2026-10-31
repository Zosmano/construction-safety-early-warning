"""Eight report dashboards (KPI cards, side panel, titled chart cards) as 16:9 PNGs and one PDF, drawn from outputs/.

    python run_all.py --report     # redraw from the cached outputs in seconds
"""
import json
import shutil
import textwrap

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch, Polygon

from ssew import alerts, config as C
from ssew.site import FLAGSHIP, ZONES

# independent safety-analytics identity: slate navy band, signal orange, risk green / amber / red
BG, SHEET, EDGE, INK, MUTED, CHIP = "#E8ECF1", "#FFFFFF", "#D2D9E2", "#101826", "#667085", "#EDF0F4"
BAND, BAND2, HI, GREEN, AMBER, RED, BLUE, VIOLET, GREY = ("#13233A", "#1F3A5C", "#FF5F15", "#1F9D55", "#E8A90C",
                                                          "#D62839", "#2F6FDE", "#6C55D8", "#98A2B3")
ICON, DISPLAY = "Segoe MDL2 Assets", "Bahnschrift"
plt.rcParams.update({"font.family": "Segoe UI", "font.size": 9, "text.color": INK, "text.parse_math": False})
I = {"warn": "", "shield": "", "chart": "", "people": "", "clock": "", "cloud": "",
     "check": "", "map": "", "book": "", "build": "", "list": "", "chevron": "",
     "calc": "", "flag": ""}
PAGES = [("Overview", "warn", "Burnaby tower, 10 zones"), ("BC evidence", "book", "WorkSafeBC, AWCBC, Alberta"),
         ("Site & calibration", "build", "30-month programme"), ("Does it work?", "chart", "Test period, 30 sites"),
         ("Warning record", "clock", "Zone by zone, week by week"), ("Weather triggers", "cloud", "Real YVR shift weather"),
         ("Provinces", "map", "BC, Ontario, Alberta"), ("Controls & sources", "list", "OHS Regulation, data"),
         ("Real-world check", "flag", "NYC public records")]
FILES = ["P1_overview", "P2_bc_evidence", "P3_site_and_calibration", "P4_does_it_work", "P5_warning_record",
         "P6_weather_triggers", "P7_provinces", "P8_controls_and_sources", "P9_real_world_check"]
R1 = [(0.135, 0.455, 0.274, 0.335), (0.4205, 0.455, 0.274, 0.335), (0.706, 0.455, 0.284, 0.335)]
W1 = (0.135, 0.455, 0.5595, 0.335)
R2 = [(0.135, 0.045, 0.415, 0.335), (0.561, 0.045, 0.429, 0.335)]
NOTE = "Independent work. Hypothetical sites with simulated daily logs, calibrated to WorkSafeBC, AWCBC, Statistics Canada and Alberta OHS data; real ECCC weather."
BANDC = {"green": GREEN, "amber": AMBER, "red": RED}
ZN = {z[0]: z[1] for z in ZONES}


# ---------------------------------------------------------------------------------------- furniture
def rbox(fig, x, y, w, h, fc=SHEET, ec=EDGE, r=0.012, shadow=True):
    ax = fig.add_axes([x, y, w, h], zorder=-2)
    ax.axis("off")
    asp = (w * fig.get_figwidth()) / (h * fig.get_figheight())
    if shadow:
        ax.add_patch(FancyBboxPatch((0.004, -0.012), 1, 1, boxstyle=f"round,pad=0,rounding_size={r*3}", mutation_aspect=asp,
                                    transform=ax.transAxes, fc="#C2CAD5", ec="none", alpha=0.55, clip_on=False))
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle=f"round,pad=0,rounding_size={r*3}", mutation_aspect=asp,
                                transform=ax.transAxes, fc=fc, ec=ec, lw=0.9, clip_on=False))
    return ax


def hazard(fig, x, y, w, h, n=18):
    ax = fig.add_axes([x, y, w, h], zorder=-1)
    ax.axis("off")
    ax.set_xlim(0, n)
    ax.set_ylim(0, 1)
    for i in range(n):
        ax.add_patch(Polygon([(i, 0), (i + 0.5, 0), (i + 1.1, 1), (i + 0.6, 1)], closed=True, fc=HI, ec="none"))


def frame(page_no, kpis, source, boxes=None, note=NOTE):
    fig = plt.figure(figsize=(16, 9), facecolor=BG)
    title, _, scope = PAGES[page_no - 1]
    rbox(fig, 0.008, 0.02, 0.118, 0.96, fc=BAND, ec=BAND, shadow=False)
    hazard(fig, 0.012, 0.952, 0.110, 0.020)
    fig.text(0.067, 0.898, I["warn"], family=ICON, fontsize=28, color=HI, ha="center")
    fig.text(0.067, 0.862, "SITE SAFETY", fontsize=15, family=DISPLAY, color="#F1F4F9", ha="center")
    fig.text(0.067, 0.843, "Early warning, Canada", fontsize=7.2, color="#A9B6C8", ha="center")
    fig.text(0.067, 0.810, f"Page {page_no} of {len(PAGES)}", fontsize=7.5, color="#A9B6C8", ha="center")
    fig.text(0.067, 0.790, title.upper(), fontsize=9.6, family=DISPLAY, color=HI, ha="center")
    boxes = boxes or [("Site", "24-storey tower, Burnaby"), ("Zones", "10 work zones"), ("Horizon", "Next 5 work days"), ("Scope", scope)]
    for i, (lab, val) in enumerate(boxes):
        y = 0.70 - i * 0.085
        rbox(fig, 0.016, y, 0.102, 0.072, fc=BAND2, ec="#2E4A70", shadow=False)
        fig.text(0.024, y + 0.050, lab, fontsize=8, weight="semibold", color="#F1F4F9")
        fig.text(0.024, y + 0.018, val, fontsize=6.9, color="#A9B6C8")
        fig.text(0.108, y + 0.050, I["chevron"], family=ICON, fontsize=7, color="#7F8DA3", ha="center")
    for i, (_, ic, _) in enumerate(PAGES):
        cx, cy = (0.040, 0.093)[i % 2], 0.385 - (i // 2) * 0.064
        on = i == page_no - 1
        rbox(fig, cx - 0.021, cy - 0.027, 0.042, 0.054, fc=HI if on else BAND2, ec=HI if on else "#2E4A70", r=0.03, shadow=False)
        fig.text(cx, cy + 0.003, I[ic], family=ICON, fontsize=13, color=BAND if on else "#A9B6C8", ha="center", va="center")
        fig.text(cx, cy - 0.019, str(i + 1), fontsize=6, color=BAND if on else "#7F8DA3", ha="center")
    fig.text(0.067, 0.070, "Analysis and design by", fontsize=6.6, color="#A9B6C8", ha="center")
    fig.text(0.067, 0.050, "Osman Zakaria, PMP", fontsize=9.2, family=DISPLAY, color=HI, ha="center")
    fig.text(0.067, 0.031, "© 2026", fontsize=6.6, color="#A9B6C8", ha="center")
    x0, w, gap = 0.135, 0.1345, 0.0076
    for i, (ic, val, lab) in enumerate(kpis):
        x = x0 + i * (w + gap)
        rbox(fig, x, 0.875, w, 0.105, r=0.03)
        fig.add_artist(plt.Rectangle((x + 0.004, 0.875), w - 0.008, 0.006, color=HI, transform=fig.transFigure, zorder=3))
        fig.text(x + 0.020, 0.940, I[ic], family=ICON, fontsize=18, color=BAND, ha="center", va="center")
        fig.text(x + 0.039, 0.939, val.replace("−", "–"), fontsize=19 if len(val) < 8 else 15.5, family=DISPLAY, color=BAND, va="center")
        fig.text(x + w / 2, 0.898, lab, fontsize=7.1, weight="semibold", color=MUTED, ha="center", va="center")
    fig.text(0.135, 0.008, f"{source} {note}", fontsize=6.4, color=MUTED)
    return fig


def chart(fig, box, title, pl=0.0, pb=0.0, yticks=False):
    x, y, w, h = box
    rbox(fig, x, y + h + 0.010, w, 0.040, fc=BAND, ec=BAND, r=0.006)
    fig.text(x + w / 2, y + h + 0.030, title, fontsize=8.8, weight="bold", color="#F1F4F9", ha="center", va="center")
    rbox(fig, x, y, w, h, r=0.008)
    ax = fig.add_axes([x + 0.012 + pl, y + 0.045 + pb, w - 0.024 - pl, h - 0.075 - pb], zorder=2)
    ax.patch.set_alpha(0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0, labelsize=7.4, colors=INK)
    if not yticks:
        ax.set_yticks([])
    return ax


def textcard(fig, box, title, lines, fs=7.4):
    ax = chart(fig, box, title)
    ax.set_xticks([])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    y, width = 0.99, int(box[2] * 16 * 18.5 * 7.4 / fs)
    for head, body, col in lines:
        ax.text(0.0, y, "■", color=col, fontsize=fs + 1, va="top")
        ax.text(0.035, y, head, fontsize=fs + 0.4, weight="bold", va="top")
        y -= 0.085
        for ln in textwrap.wrap(body, width):
            ax.text(0.035, y, ln, fontsize=fs, color="#2B3442", va="top")
            y -= 0.072
        y -= 0.035
    return ax


def chip(ax, x, y, text, fs=6.9, horizontal=False):
    off = (5, 0) if horizontal else (0, 5)
    ax.annotate(text, (x, y), xytext=off, textcoords="offset points", ha="left" if horizontal else "center",
                va="center" if horizontal else "bottom", fontsize=fs, bbox=dict(boxstyle="round,pad=0.25,rounding_size=0.5", fc=CHIP, ec="none"))


def legend(ax, names, colors, marker="s", ncol=None):
    h = [plt.Line2D([], [], marker=marker, ls="" if marker else "-", lw=2, ms=6, color=c, label=n) for n, c in zip(names, colors)]
    ax.legend(handles=h, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=ncol or len(names), frameon=False,
              fontsize=7.0, handletextpad=0.3, columnspacing=0.9, borderaxespad=0.2)


def hbar(ax, labels, vals, fmt="{:,.0f}", colors=BLUE, fs=7.2):
    ys = list(range(len(vals)))[::-1]
    ax.barh(ys, vals, color=colors, height=0.62)
    for y, v in zip(ys, vals):
        chip(ax, v, y, fmt.format(v), horizontal=True)
    ax.set_yticks(ys)
    ax.set_yticklabels(labels, fontsize=fs)
    ax.set_xticks([])
    ax.set_xlim(0, max(vals) * 1.25)


def grid(ax, axis="y"):
    ax.grid(axis=axis, color="#E4E8EE", lw=0.7)
    ax.set_axisbelow(True)


def wrap(s, n):
    return "\n".join(textwrap.wrap(str(s), n, break_long_words=False))


# ---------------------------------------------------------------------------------------- data
def load():
    o = C.OUT
    d = {"S": json.loads((o / "summary.json").read_text()),
         "F": pd.read_csv(o / "risk_scores.csv", parse_dates=["date"]),
         "ev": pd.read_csv(o / "events.csv", parse_dates=["date"]),
         "evt": pd.read_csv(o / "test_events_warned.csv", parse_dates=["date"]),
         "zd": pd.read_csv(o / "zone_days.csv", parse_dates=["date"]),
         "wx": pd.read_csv(o / "weather_shift_daily.csv", index_col=0, parse_dates=True),
         "narr": pd.read_csv(o / "worksafebc_construction_deaths_2024.csv"),
         "drv": pd.read_csv(o / "flagship_drivers.csv", parse_dates=["date"])}
    d["M"] = d["S"]["metrics"]
    d["fl"] = d["F"][d["F"].site == FLAGSHIP]
    return d


def site_plan(ax, fl, day):
    """The site plan on one day, zones filled by alert band, risk in each."""
    today = fl[fl.date == day].set_index("zone")
    for zid, name, poly, _, _ in ZONES:
        r = today.loc[zid] if zid in today.index else None
        fc = "#F2F3F1" if r is None else BANDC[r.band]
        ax.add_patch(Polygon(poly, closed=True, fc=fc, ec="#8A938F", lw=1, alpha=1 if r is None else [0.35, 0.65, 0.85][["green", "amber", "red"].index(r.band)]))
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        cx, cy, w = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(xs) - min(xs)
        lab = wrap(name, 16) if w > 14 else zid
        ax.text(cx, cy - 2.5 if w > 14 else cy, lab, ha="center", va="center", fontsize=6.4 if w > 14 else 6, weight="semibold",
                rotation=0 if w > 7 else 90)
        if r is not None and w > 7:
            ax.text(cx, cy + 4, f"{r.p:.0%}", ha="center", va="center", fontsize=11, family=DISPLAY, color=INK)
    ax.add_patch(plt.Circle((56, 38), 30, fill=False, ls="--", ec=HI, lw=1.4))
    ax.plot([50, 84], [38, 50], color=HI, lw=3, solid_capstyle="round")
    ax.plot(56, 38, "o", color=BAND, ms=6)
    ax.set_xlim(-1, 101)
    ax.set_ylim(66, -2)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])


# ---------------------------------------------------------------------------------------- pages
def p1(d):
    M, S, fl, ev = d["M"], d["S"], d["fl"], d["ev"]
    kpis = [("check", f"{M['warned_share']:.0%}", f"Events flagged in advance ({M['events_test']})"),
            ("warn", f"{M['bands'][0]['lift']:.1f}×", "Event rate on red zone-days"),
            ("clock", f"{M['median_lead_days']:.0f} days", "Median warning before an event"),
            ("chart", f"{M['auc']:.2f}", f"AUC (crew-only baseline {M['auc_base']:.2f})"),
            ("people", f"{S['simulated_rate']:.1f}", f"Injuries / 100 person-yrs (BC: {S['sources']['time_loss_rate']:.0f})"),
            ("flag", f"{M['alerts_per_site_week']['red']:.1f}", "Red alerts per site-week")]
    fig = frame(1, kpis, "Sources: WorkSafeBC Statistics 2024; AWCBC NWISP 2020–2022; Alberta OHS PSI 2020; ECCC hourly climate (YVR).")
    te = fl[fl.date > C.TRAIN_END]
    worst = te.groupby("date").p.max().idxmax()
    ax = chart(fig, R1[0], f"Site plan on the riskiest test day: {worst:%a %d %b %Y}")
    site_plan(ax, fl, worst)
    legend(ax, ["Red", "Amber", "Green"], [RED, AMBER, GREEN])
    ax = chart(fig, (0.4205, 0.455, 0.5695, 0.335), "Highest zone risk on site each work day (5-day horizon), with injuries and near misses", yticks=True)
    m = fl.groupby("date").agg(p=("p", "max"))
    b = fl.assign(bi=fl.band.map({"green": 0, "amber": 1, "red": 2})).groupby("date").bi.max()
    ax.bar(m.index, m.p, width=1.6, color=[[GREEN, AMBER, RED][k] for k in b.reindex(m.index)])
    e = ev[ev.site == FLAGSHIP]
    top = m.p.max() * 1.12
    for r in e.itertuples():
        ax.plot(r.date, top * (0.98 if r.kind != "High-potential near miss" else 0.93), "o" if r.kind != "High-potential near miss" else "^",
                ms=4.5, color=RED if r.kind != "High-potential near miss" else "white", mec=INK, mew=0.7)
    ax.axvline(pd.Timestamp(C.TRAIN_END), color=INK, ls="--", lw=0.9)
    ax.text(pd.Timestamp(C.TRAIN_END), top * 0.86, "  test period →", fontsize=7)
    ax.set_ylim(0, top)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    grid(ax)
    legend(ax, ["Injury", "High-potential near miss"], [RED, "white"], marker="o")
    imp = pd.Series(d["S"]["importance"]).sort_values(ascending=False)
    imp = imp[imp > 0.001]
    ax = chart(fig, R2[0], "What carries the warning: test AUC lost when each signal is shuffled", pl=0.07, yticks=True)
    hbar(ax, list(imp.index), list(imp.values), fmt="{:.3f}", colors=[BAND if k == "Crew exposure" else HI for k in imp.index])
    textcard(fig, R2[1], "What the system does, and what it found", [
        ("Answers where, not just how many", "A schedule already says how many people will be on site. The model says which zone is building toward an "
         f"injury in the next {C.HORIZON_DAYS} work days and why, so the morning briefing can target it.", HI),
        ("Warns early enough to act", f"{M['warned_share']:.0%} of test-period events (and {M['warned_injuries_share']:.0%} of injuries) had an amber or red alert "
         f"in the zone during the {C.HORIZON_DAYS} work days before. Red zone-days carry {M['bands'][0]['lift']:.1f} times the average event rate.", RED),
        ("Without crying wolf", f"About {M['alerts_per_site_week']['red']:.1f} red and {M['alerts_per_site_week']['amber']:.0f} amber zone-days per site each week, "
         "each with up to three drivers and controls tied to the BC OHS Regulation.", GREEN),
        ("Grounded in BC numbers", f"The simulated portfolio runs at {d['S']['simulated_rate']:.1f} time-loss injuries per 100 person-years against "
         f"WorkSafeBC's {d['S']['sources']['time_loss_rate']:.0f} for general construction, with AWCBC's construction injury mix.", BLUE)], fs=7.2)
    return fig


def p2(d):
    src, narr = d["S"]["sources"], d["narr"]
    deaths = pd.Series(src["deaths_by_year"]).astype(int)
    claims = src["claims_2024"]
    bc = src["bc_construction_ltc"]
    kpis = [("warn", f"{deaths.sum()}", "Construction deaths accepted, 2015–2024"),
            ("people", f"{claims['total']:,.0f}", "General-construction claims, 2024"),
            ("clock", f"{claims['days_lost']/1e3:,.0f}k", "Days lost to those claims"),
            ("chart", f"{src['time_loss_rate']:.0f}", "Time-loss claims / 100 person-years"),
            ("shield", f"{src['serious_rate']['2024']:.2f}", "Serious-injury rate, 2024"),
            ("map", f"{bc['2022']['bc']:,.0f}", "BC construction lost-time claims, 2022")]
    fig = frame(2, kpis, "WorkSafeBC Statistics 2024 (Figures 1.4, 1.9, 2.7, 2.10; 2024 death descriptions); AWCBC NWISP 2020–2022 (Tables 15, 21); Alberta OHS PSI construction 2020.")
    ax = chart(fig, R1[0], "Work-related death claims, BC general construction", yticks=True)
    ax.bar(deaths.index.astype(str), deaths.values, color=RED, width=0.65)
    for x, v in zip(deaths.index.astype(str), deaths.values):
        chip(ax, x, v, str(v))
    ax.set_ylim(0, deaths.max() * 1.25)
    ax.set_yticks([])
    ax = chart(fig, R1[1], "Lost-time claims in Canadian construction, by event, 2021–22", pl=0.09)
    mix = pd.Series(src["event_mix"]).sort_values(ascending=False)
    hbar(ax, [wrap(k, 26) for k in mix.index], list(mix.values), fmt="{:.1%}", colors=AMBER, fs=6.8)
    ax = chart(fig, R1[2], "Serious-injury claims rate, BC construction (per 100 person-years)", yticks=True)
    sr = pd.Series(src["serious_rate"])
    ax.plot(sr.index, sr.values, "o-", color=BLUE, lw=2)
    for x, v in sr.items():
        chip(ax, x, v, f"{v:.2f}")
    ax.set_ylim(0.4, 0.8)
    grid(ax)
    ax = chart(fig, R2[0], "BC construction deaths accepted in 2024, by hazard (WorkSafeBC descriptions)", pl=0.09)
    hz = narr.hazard.value_counts()
    hbar(ax, [wrap(k, 30) for k in hz.index], list(hz.values), colors=[RED if "Fall" in k or "Struck" in k or "Vehicle" in k or "Electrical" in k else GREY for k in hz.index], fs=6.8)
    psi = src["alberta_psi"]
    ax = chart(fig, R2[1], f"Potentially serious incidents, Alberta construction 2020: {psi['total']} reported, {1 - psi['share_with_injury']:.0%} hurt no one", pl=0.13)
    t = pd.Series(psi["types"])
    hbar(ax, [wrap(k.split(" (")[0], 34) for k in t.index], list(t.values), colors=VIOLET, fs=6.8)
    return fig


def p3(d):
    zd, ev, S = d["zd"], d["ev"], d["S"]
    f = zd[zd.site == FLAGSHIP]
    crew = f.pivot_table(index="date", columns="zone", values="crew", aggfunc="sum").fillna(0)
    mix = pd.Series(S["sources"]["event_mix"])
    inj = ev[ev.kind != "High-potential near miss"].family.value_counts(normalize=True)
    kpis = [("people", f"{int(crew.sum(1).max())}", "Peak workers on the Burnaby site"),
            ("clock", f"{S['person_hours']/1e6:.1f}M", "Person-hours, 30 sites"),
            ("chart", f"{S['simulated_rate']:.2f}", f"Time-loss rate (BC target {S['sources']['time_loss_rate']:.0f})"),
            ("warn", f"{(ev.kind != 'High-potential near miss').sum()}", "Injuries across the portfolio"),
            ("flag", f"{(ev.kind == 'High-potential near miss').sum()}", "High-potential near misses"),
            ("build", "30 months", "Programme, Mar 2023 – Aug 2025")]
    fig = frame(3, kpis, "Crews follow a six-phase programme; injury rates are rescaled so the whole portfolio runs at WorkSafeBC's general-construction rate.")
    ax = chart(fig, W1, "Burnaby crews by zone across the programme (workers per day)", yticks=True)
    cols = [BAND, HI, BLUE, RED, AMBER, VIOLET, GREEN, "#7FB3E6", GREY, "#C98A5A"]
    ax.stackplot(crew.index, [crew[z] for z in crew.columns], colors=cols[:len(crew.columns)], lw=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    grid(ax)
    legend(ax, [ZN[z].split(" &")[0].split(",")[0] for z in crew.columns], cols[:len(crew.columns)], ncol=5)
    ax = chart(fig, R1[2], "Simulated injury mix vs AWCBC construction mix", pl=0.10)
    fams = mix.sort_values(ascending=False).index
    ys = np.arange(len(fams))[::-1]
    ax.barh(ys + 0.18, mix.reindex(fams).values, height=0.34, color=AMBER)
    ax.barh(ys - 0.18, inj.reindex(fams).fillna(0).values, height=0.34, color=BAND)
    ax.set_yticks(ys)
    ax.set_yticklabels([wrap(k, 22) for k in fams], fontsize=6.6)
    ax.set_xticks([])
    legend(ax, ["AWCBC (real)", "Simulated injuries"], [AMBER, BAND])
    textcard(fig, R2[0], "What is real", [
        ("Base injury rate", f"BC general construction runs at {S['sources']['time_loss_rate']:.0f} time-loss claims per 100 person-years (WorkSafeBC). "
         "Every site's hazard is rescaled so the portfolio matches it.", BLUE),
        ("Injury mix and severity", "Each injury takes an event family from AWCBC's construction lost-time claims by event, weighted by the zone's hazards; "
         "the serious share follows WorkSafeBC's serious-injury rate.", AMBER),
        ("Near misses and weather", "Three high-potential near misses per injury, after Alberta's 2020 construction PSIs (75% hurt no one); "
         "every day runs on real Vancouver shift weather from ECCC.", GREEN)])
    textcard(fig, R2[1], "What is simulated, and why the model can't cheat", [
        ("The site and its logs", "Ten zones, a six-phase programme and daily logs: near-miss reports, hazard observations, PPE and housekeeping "
         "audits, permits, new workers, overtime and trade congestion.", HI),
        ("A hidden safety climate", "Each zone's climate drifts and sometimes deteriorates for weeks (a new subcontractor, a schedule crunch). "
         "It drives both the logs and the incidents, but the model never sees it.", RED),
        ("Pooled across a portfolio", "One site has too few injuries to learn from, so the model trains on a contractor's 30 sites in three provinces, as a "
         "real safety department would.", VIOLET)])
    return fig


def p4(d):
    M, S = d["M"], d["S"]
    bands = pd.DataFrame(M["bands"]).set_index("band")
    kpis = [("chart", f"{M['auc']:.2f}", "AUC, test period"),
            ("people", f"{M['auc_base']:.2f}", "Crew-only baseline AUC"),
            ("shield", f"{M['auc_oracle']:.2f}", "Ceiling: true hidden hazard"),
            ("calc", f"{M['ap']:.2f}", f"Average precision (base {M['test_base_rate']:.0%})"),
            ("warn", f"{bands.loc['red', 'lift']:.1f}×", "Red-band lift"),
            ("check", f"{M['warned_injuries_share']:.0%}", "Injuries flagged in advance")]
    fig = frame(4, kpis, f"Trained on all 30 sites (BC, ON, AB) before {C.TRAIN_END}; judged on the ten months after. Bands fixed on the training period.")
    ax = chart(fig, R1[0], "Event rate within 5 work days, by alert band", yticks=True)
    order = ["red", "amber", "green"]
    ax.bar([f"{b.title()}\n{bands.loc[b, 'share_rows']:.0%} of zone-days" for b in order], bands.loc[order, "event_rate"], color=[RED, AMBER, GREEN], width=0.6)
    for k, b in enumerate(order):
        chip(ax, k, bands.loc[b, "event_rate"], f"{bands.loc[b, 'event_rate']:.1%} · {bands.loc[b, 'lift']:.1f}×")
    ax.axhline(M["test_base_rate"], color=INK, ls="--", lw=0.8)
    ax.set_yticks([])
    ax = chart(fig, R1[1], "Ranking quality: model vs baseline vs ceiling (AUC)", pl=0.07)
    hbar(ax, ["Crew plan only", "Early-warning model", "True hidden hazard"], [M["auc_base"], M["auc"], M["auc_oracle"]], fmt="{:.3f}", colors=[GREY, HI, GREEN])
    ax.set_xlim(0.5, 0.85)
    ax = chart(fig, R1[2], "Calibration by decile: predicted vs observed", yticks=True)
    cal = pd.DataFrame(M["calibration"])
    mx = max(cal.pred.max(), cal.obs.max()) * 1.1
    ax.plot([0, mx], [0, mx], ls="--", color=GREY, lw=0.9)
    ax.scatter(cal.pred, cal.obs, s=50, color=HI, ec=INK, zorder=3)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_xlabel("Predicted", fontsize=7, color=MUTED)
    ax.set_ylabel("Observed", fontsize=7, color=MUTED)
    grid(ax, "both")
    ax = chart(fig, R2[0], "Share of test-period events flagged amber or red in the 5 work days before", pl=0.07)
    wk = pd.Series(M["warned_by_kind"]).sort_values()
    hbar(ax, list(wk.index) + ["All events"], list(wk.values) + [M["warned_share"]], fmt="{:.0%}", colors=[RED, AMBER, BLUE, BAND])
    textcard(fig, R2[1], "Reading the scorecard honestly", [
        ("Better than the schedule alone", f"Knowing only the crew plan ranks zone-days at AUC {M['auc_base']:.2f}; the leading indicators lift it to {M['auc']:.2f}, "
         f"closing about {(M['auc'] - M['auc_base']) / (M['auc_oracle'] - M['auc_base']):.0%} of the gap to a model that could see the hidden hazard.", HI),
        ("Rare events stay hard", f"With a {M['test_base_rate']:.0%} base rate most zone-days never see an event, so precision stays modest "
         f"({M['ap']:.2f}). That is why alerts drive cheap, targeted controls, not stop-work orders.", AMBER),
        ("Simulated logs, real method", "The indicators are simulated, so these numbers show what the method can do with data like this. "
         "A pilot on a real site's records is the next step.", RED)], fs=7.2)
    return fig


def p5(d):
    fl, ev, evt = d["fl"], d["ev"], d["evt"]
    fl = fl.assign(week=fl.date.dt.to_period("W").dt.start_time, bi=fl.band.map({"green": 0, "amber": 1, "red": 2}))
    H = fl.pivot_table(index="zone", columns="week", values="bi", aggfunc="max")
    H = H.reindex([z[0] for z in ZONES])
    e = ev[ev.site == FLAGSHIP].assign(week=lambda x: x.date.dt.to_period("W").dt.start_time)
    leads = []
    key = d["F"].set_index(["site", "zone", "date"]).band
    dates = pd.Index(sorted(d["F"].date.unique()))
    for r in evt.itertuples():
        i = dates.searchsorted(r.date)
        prior = dates[max(0, i - C.HORIZON_DAYS):i]
        w = [k for k, dd in enumerate(prior) if key.get((r.site, r.zone, dd), "green") != "green"]
        if w:
            leads.append(len(prior) - w[0])
    kpis = [("clock", f"{np.median(leads):.0f} days", "Median warning lead"),
            ("check", f"{evt.warned.mean():.0%}", "Test events with prior warning"),
            ("warn", f"{(fl.band == 'red').sum()}", "Red zone-days, Burnaby"),
            ("flag", f"{(fl.band == 'amber').sum()}", "Amber zone-days, Burnaby"),
            ("people", f"{len(e)}", "Burnaby events, whole build"),
            ("list", f"{len(evt)}", "Test events, all sites")]
    fig = frame(5, kpis, "Weekly peak alert per zone for the Burnaby build; dots are that week's injuries (filled) and high-potential near misses (open).")
    ax = chart(fig, (0.135, 0.455, 0.855, 0.335), "Weekly peak alert by zone, Burnaby, March 2023 – August 2025", pl=0.08)
    cmap = LinearSegmentedColormap.from_list("b", [GREEN, AMBER, RED], N=3)
    M_ = np.ma.masked_invalid(H.values.astype(float))
    ax.imshow(M_, aspect="auto", cmap=cmap, vmin=0, vmax=2, interpolation="nearest")
    cols = list(H.columns)
    for r in e.itertuples():
        if r.week in cols:
            j, i = cols.index(r.week), list(H.index).index(r.zone)
            ax.plot(j, i, "o", ms=4, color=INK if r.kind != "High-potential near miss" else "white", mec=INK, mew=0.7)
    ti = next(k for k, c in enumerate(cols) if c > pd.Timestamp(C.TRAIN_END))
    ax.axvline(ti - 0.5, color=INK, ls="--", lw=1)
    ax.set_yticks(range(len(H)))
    ax.set_yticklabels([ZN[z] for z in H.index], fontsize=7)
    yt = [k for k, c in enumerate(cols) if c.month in (1, 7) and (k == 0 or cols[k - 1].month != c.month)]
    ax.set_xticks(yt)
    ax.set_xticklabels([f"{cols[k]:%b %Y}" for k in yt], fontsize=7)
    ax = chart(fig, R2[0], "Warning lead time for flagged test events (work days before the event)", yticks=True)
    lc = pd.Series(leads).value_counts().reindex(range(1, C.HORIZON_DAYS + 1), fill_value=0)
    ax.bar(lc.index, lc.values, color=HI, ec=INK, width=0.6)
    for x, v in lc.items():
        chip(ax, x, v, str(v))
    ax.set_xticks(lc.index)
    ax.set_yticks([])
    ax = chart(fig, R2[1], "Test events by hazard: share flagged in advance", pl=0.12)
    by = evt.groupby("family").warned.agg(["mean", "size"]).sort_values("mean", ascending=False)
    hbar(ax, [f"{wrap(k, 30)} ({n})" for k, n in by["size"].items()], list(by["mean"].values), fmt="{:.0%}", colors=AMBER, fs=6.8)
    return fig


def p6(d):
    wx, zd = d["wx"], d["zd"]
    w = wx[(wx.index >= C.START) & (wx.index <= C.END) & (wx.index.dayofweek < 5)]
    trig = pd.DataFrame({"Wind (gust ≥ 50)": w.gust_est >= C.CRANE_GUST_KMH, "Heat (humidex ≥ 30)": w.humidex_max >= C.HUMIDEX_HEAT,
                         "Wet (≥ 3 rain hours)": w.rain_hours >= C.WET_HOURS,
                         "Freeze or snow": (w.temp_min <= C.FREEZE_C) | w.snow_or_ice.astype(bool)})
    monthly = trig.groupby(w.index.month).mean()
    kpis = [("cloud", f"{trig.iloc[:, 0].sum()}", "Crane wind stand-down days"),
            ("warn", f"{trig.iloc[:, 1].sum()}", "Heat-stress screening days"),
            ("cloud", f"{trig.iloc[:, 2].sum()}", "Wet-deck days (3+ rain hours)"),
            ("flag", f"{trig.iloc[:, 3].sum()}", "Freeze or snow days"),
            ("chart", f"{w.gust_est.max():.0f} km/h", "Highest estimated gust"),
            ("clock", f"{len(w)}", "Work days of real YVR weather")]
    fig = frame(6, kpis, "ECCC hourly observations at Vancouver Int'l A, 07:00–15:00, work days only. Gust estimated as 1.5 × the hourly mean wind.")
    ax = chart(fig, W1, "Weather triggers by month (share of work days), Vancouver 2023–2025", yticks=True)
    mcol = [BLUE, RED, "#5DA9E9", VIOLET]
    wd = 0.2
    for k, c in enumerate(monthly.columns):
        ax.bar(monthly.index + (k - 1.5) * wd, monthly[c], width=wd, color=mcol[k])
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    grid(ax)
    legend(ax, list(monthly.columns), mcol)
    ax = chart(fig, R1[2], "Estimated gust through the build (crane stand-down at 50 km/h)", yticks=True)
    ax.plot(w.index, w.gust_est, color=GREY, lw=0.5)
    hi_ = w[w.gust_est >= C.CRANE_GUST_KMH]
    ax.plot(hi_.index, hi_.gust_est, "o", ms=2.5, color=RED)
    ax.axhline(C.CRANE_GUST_KMH, color=RED, ls="--", lw=0.8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    grid(ax)
    F = d["F"]
    te = F[F.date > C.TRAIN_END]
    rows = []
    for name, zones, mask in [("Wind ≥ 50 km/h forecast", ["CRN", "SCF", "ROF"], te.gust_fc >= C.CRANE_GUST_KMH),
                              ("Wet or freezing forecast", ["DCK", "SCF", "ROF", "GTE", "LAY", "EXC"], (te.wet_fc >= 1) | (te.freeze_fc >= 1)),
                              ("Heat forecast", ["ROF", "DCK", "FRM", "LAY"], te.humidex_fc >= C.HUMIDEX_HEAT)]:
        z = te[te.zone.isin(zones)]
        m = mask.reindex(z.index)
        rows.append((name, z[m].y.mean(), z[~m].y.mean(), z[m].p.mean(), z[~m].p.mean(), int(m.sum())))
    ax = chart(fig, R2[0], "Exposed zones, test period: actual event rate and model risk when the 5-day forecast has a trigger", yticks=True)
    x = np.arange(len(rows))
    specs = [(1, RED, "Events, trigger forecast"), (2, "#E8A3AC", "Events, otherwise"), (3, BAND, "Model risk, trigger"), (4, GREY, "Model risk, otherwise")]
    for k, (col, c, _) in enumerate(specs):
        vals = [r[col] for r in rows]
        ax.bar(x + (k - 1.5) * 0.2, vals, width=0.19, color=c)
        for xi, v in zip(x + (k - 1.5) * 0.2, vals):
            chip(ax, xi, v, f"{v:.1%}", fs=6.2)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{r[0]}\n({r[5]:,} zone-days)" for r in rows], fontsize=7)
    ax.set_yticks([])
    legend(ax, [s[2] for s in specs], [s[1] for s in specs], ncol=4)
    wind, wet, heat = rows
    textcard(fig, R2[1], "What the weather check found, and the fix", [
        ("Rain and frost: learned", f"When wet or freezing days are forecast, exposed zones see {wet[1] / wet[2]:.1f}× the event rate and the model "
         f"raises their risk {wet[3] / wet[4]:.1f}×. It has seen enough wet winters to weigh this correctly.", BLUE),
        ("Wind: under-learned, so a hard rule backs it up", f"Events run {wind[1] / wind[2]:.1f}× higher in windy windows, but wind incidents are too rare "
         "for the model to weigh, so its risk barely moves. A rule now sets crane, scaffold and roof zones to at least amber whenever a gust of "
         f"{C.CRANE_GUST_KMH} km/h or more is forecast.", RED),
        ("Heat: too little evidence yet", "The test period's heat fell in summer 2025, after the roof, deck and formwork crews had wound down, "
         "so there are too few exposed zone-days to judge. Thresholds remain screens; manufacturers' limits and site procedures decide.", HI)], fs=7.1)
    return fig


def p7(d):
    S, evt = d["S"], d["evt"]
    bs = pd.DataFrame(S["by_site"]).set_index("site")
    bs["rate"] = bs.injuries / bs.person_hours * 200000
    P, B = S["sources"]["provinces"], S["by_province"]
    NM = {"BC": "British Columbia", "ON": "Ontario", "AB": "Alberta"}
    PC = {"BC": BAND2, "ON": BLUE, "AB": VIOLET}
    kpis = [("map", "3", "Provinces, 30 sites"),
            ("chart", f"{P['BC']['rate']:.1f}", "BC claims / 100 workers"),
            ("chart", f"{P['AB']['rate']:.1f}", "Alberta claims / 100 workers"),
            ("chart", f"{P['ON']['rate']:.1f}", "Ontario claims / 100 workers"),
            ("warn", f"{sum(P[k]['fatalities']['2022'] or 0 for k in P):.0f}", "Construction deaths, 3 provinces, 2022"),
            ("check", f"{evt.warned.mean():.0%}", "Test events flagged in advance")]
    fig = frame(7, kpis, "Rates: AWCBC accepted construction lost-time claims ÷ Statistics Canada LFS construction employment (table 14-10-0023), 2020–2022. "
                         "Boards differ in coverage and lost-time definitions.")
    ax = chart(fig, R1[0], "Construction lost-time claims per 100 workers", yticks=True)
    yrs = [2020, 2021, 2022]
    for j, k in enumerate(["BC", "AB", "ON"]):
        v = [P[k]["by_year"][str(y)] if str(y) in P[k]["by_year"] else P[k]["by_year"][y] for y in yrs]
        ax.bar(np.arange(3) + (j - 1) * 0.26, v, width=0.25, color=PC[k])
        for x, vv in zip(np.arange(3) + (j - 1) * 0.26, v):
            chip(ax, x, vv, f"{vv:.1f}", fs=6.2)
    ax.set_xticks(range(3))
    ax.set_xticklabels(yrs)
    ax.set_yticks([])
    legend(ax, [NM[k] for k in ["BC", "AB", "ON"]], [PC[k] for k in ["BC", "AB", "ON"]])
    ax = chart(fig, R1[1], "Construction fatalities accepted (AWCBC)", yticks=True)
    for j, k in enumerate(["BC", "AB", "ON"]):
        v = [(P[k]["fatalities"].get(str(y)) or P[k]["fatalities"].get(y) or 0) for y in yrs]
        ax.bar(np.arange(3) + (j - 1) * 0.26, v, width=0.25, color=PC[k])
        for x, vv in zip(np.arange(3) + (j - 1) * 0.26, v):
            chip(ax, x, vv, f"{vv:.0f}", fs=6.2)
    ax.set_xticks(range(3))
    ax.set_xticklabels(yrs)
    ax.set_yticks([])
    legend(ax, [NM[k] for k in ["BC", "AB", "ON"]], [PC[k] for k in ["BC", "AB", "ON"]])
    ax = chart(fig, R1[2], "Flagged in advance with each province's own cut-off (| = shared cut-off)", pl=0.06)
    ks = ["BC", "AB", "ON"]
    ys = np.arange(3)[::-1]
    ax.barh(ys + 0.18, [B[k]["warned"] for k in ks], height=0.34, color=HI)
    ax.barh(ys - 0.18, [B[k]["auc"] for k in ks], height=0.34, color=BAND)
    for y, k in zip(ys, ks):
        ax.plot([B[k]["warned_pooled"]] * 2, [y + 0.0, y + 0.36], color=INK, lw=1.4)
        lab = f"{B[k]['warned']:.0%} flagged ({B[k]['events']} events)"
        if round(B[k]["warned"], 2) != round(B[k]["warned_pooled"], 2):
            lab += f", was {B[k]['warned_pooled']:.0%}"
        chip(ax, B[k]["warned"], y + 0.18, lab, horizontal=True, fs=6.4)
        chip(ax, B[k]["auc"], y - 0.18, f"AUC {B[k]['auc']:.2f}", horizontal=True, fs=6.4)
    ax.set_yticks(ys)
    ax.set_yticklabels([NM[k] for k in ks], fontsize=7.2)
    ax.set_xlim(0, 1.35)
    ax.set_xticks([])
    ax = chart(fig, (0.135, 0.045, 0.855, 0.335), "Site scorecard (test period)")
    ax.set_xticks([])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    # two side-by-side tables, so a portfolio of any size up to ~32 sites fits
    cols = [("Site", 0.0, "left"), ("Prov.", 0.17, "left"), ("Events", 0.27, "right"), ("Injuries", 0.335, "right"),
            ("Flagged", 0.41, "right"), ("Red days", 0.475, "right")]
    half = (len(bs) + 1) // 2
    step = min(0.061, 0.88 / max(1, half))
    for off in (0.0, 0.52):
        for c, x, ha in cols:
            ax.text(off + x, 0.985, c, fontsize=7.0, weight="bold", color=MUTED, ha=ha, va="top")
    for i, (s, r) in enumerate(bs.iterrows()):
        off, y = (0.0, 0.91 - i * step) if i < half else (0.52, 0.91 - (i - half) * step)
        if s == FLAGSHIP:
            ax.add_patch(plt.Rectangle((off - 0.005, y - step / 2), 0.49, step, color="#FFE3D3", lw=0))
        vals = [s + (" (featured)" if s == FLAGSHIP else ""), r.province, f"{r.events:.0f}", f"{r.injuries:.0f}",
                f"{r.warned:.0%}" if pd.notna(r.warned) else "–", f"{r.red_days:.0f}"]
        for (c, x, ha), v in zip(cols, vals):
            ax.text(off + x, y, v, fontsize=6.4, ha=ha, va="center", weight="bold" if s == FLAGSHIP and x == 0 else "normal")
    return fig


def p8(d):
    kpis = [("list", f"{len(alerts.ACTIONS)}", "Driver-specific controls"),
            ("build", f"{len(alerts.ZONE_RULE)}", "Zone standing controls"),
            ("book", "5", "Public data sources"),
            ("shield", "BC·ON·AB", "Controls cited per province"),
            ("clock", "Pre-shift", "When alerts are acted on"),
            ("check", "3 max", "Drivers shown per alert")]
    fig = frame(8, kpis, "Controls cite BC's OHS Regulation, Ontario's OHSA and O. Reg. 213/91, and Alberta's OHS Act and Code (BC shown; all three on the live dashboard). "
                         "They support, not replace, the site's program.")
    ax = chart(fig, (0.135, 0.455, 0.855, 0.335), "Control library: what the briefing tells the crew to do, by driver")
    ax.set_xticks([])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    items = list(alerts.ACTIONS.items())
    half = (len(items) + 1) // 2
    for col, chunk in enumerate([items[:half], items[half:]]):
        x0 = col * 0.5
        for i, (drv, (act, ref)) in enumerate(chunk):
            y = 0.97 - i * 0.163
            ax.text(x0, y, drv, fontsize=7.6, weight="bold", va="top")
            ax.text(x0, y - 0.047, act if len(act) <= 118 else act[:115].rsplit(" ", 1)[0] + "…", fontsize=6.5, va="top", color="#2B3442")
            ax.text(x0, y - 0.093, f"BC: {ref['BC']}   ·   ON: {ref['ON']}", fontsize=6.0, va="top", color=BLUE)
    ax = chart(fig, (0.135, 0.045, 0.855, 0.335), "Data sources")
    ax.set_xticks([])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    hdr = [("Source", 0.0), ("Provider", 0.20), ("What it sets", 0.42), ("Access", 0.72)]
    for h, x in hdr:
        ax.text(x, 0.97, h, fontsize=7.4, weight="bold", color=MUTED, va="top")
    src = [("Statistics 2024", "WorkSafeBC", "BC construction time-loss and serious-injury rates, claims mix, deaths 2015–2024, 2024 death descriptions",
            "worksafebc.com: Data & insights, statistical reports"),
           ("National Work Injury, Disease and Fatality Statistics 2020–2022", "AWCBC", "Construction claims by event; claims and fatalities by province (BC, ON, AB)",
            "awcbc.org: NWISP publications"),
           ("Potentially Serious Incidents: construction, 2020", "Government of Alberta, OHS", "Near-miss ratio: 75% of construction PSIs hurt no one; PSI types",
            "open.alberta.ca"),
           ("Labour Force Survey, table 14-10-0023", "Statistics Canada", "Construction employment by province: turns AWCBC claims into rates for ON and AB",
            "www150.statcan.gc.ca"),
           ("Historical hourly climate: Vancouver, Toronto, Calgary", "Environment and Climate Change Canada", "Shift-hour wind, humidex, rain, frost and snow for every work day, 2023–2025",
            "climate.weather.gc.ca bulk data")]
    for i, row in enumerate(src):
        y = 0.84 - i * 0.165
        if i % 2 == 0:
            ax.axhspan(y - 0.075, y + 0.075, color="#F3F5F8", lw=0)
        for (h, x), v in zip(hdr, row):
            ax.text(x, y, wrap(v, 40 if x < 0.4 else 52), fontsize=7.0, va="center", weight="bold" if x == 0 else "normal",
                    color=BLUE if x == 0.72 else INK)
    return fig


def p9(d):
    N = d["S"]["nyc"]
    L, bands = N["within_large_jobs"], pd.DataFrame(N["bands"]).set_index("band")
    kpis = [("check", f"{N['warned_share']:.0%}", f"Real incidents flagged ({N['incidents_scored_test']})"),
            ("warn", f"{bands.loc['red', 'lift']:.0f}×", "Incident rate, red site-weeks"),
            ("chart", f"{N['auc']:.2f}", f"AUC (job size alone {N['auc_base']:.2f})"),
            ("calc", f"{L['auc']:.2f}", f"Large jobs (size alone {L['auc_base']:.2f})"),
            ("build", f"{N['sites']:,}", "NYC construction sites"),
            ("clock", "4 weeks", "Warning horizon")]
    fig = frame(9, kpis, f"NYC Open Data, Department of Buildings: Construction-Related Incidents, DOB NOW approved permits, ECB violations, complaints. "
                         f"Trained on site-weeks {N['start']} to {N['split']}; tested to {N['end']}.",
                boxes=[("Sites", f"{N['sites']:,} in New York City"), ("Unit", "One site, one week"), ("Horizon", "Next 4 weeks"), ("Scope", "Real public records")],
                note="Independent work. Real sites and real outcomes; nothing on this page is simulated.")
    ax = chart(fig, R1[0], "Large jobs: incident rate next 4 weeks, with vs without each sign", pl=0.085)
    rs = N["signal_rates_large_jobs"]
    hbar(ax, [wrap(r["signal"], 22) for r in rs], [r["ratio"] for r in rs], fmt="{:.1f}×", colors=HI, fs=6.8)
    ax = chart(fig, R1[1], "Ranking quality (AUC, test period)", pl=0.085)
    hbar(ax, ["Job size and type", "+ warning signs", "Large jobs: size", "Large jobs: + signs"], [N["auc_base"], N["auc"], L["auc_base"], L["auc"]],
         fmt="{:.3f}", colors=[GREY, HI, GREY, HI], fs=6.8)
    ax.set_xlim(0.6, 0.95)
    ax = chart(fig, R1[2], "Incident rate within 4 weeks, by alert band", yticks=True)
    order = ["red", "amber", "green"]
    ax.bar([f"{b.title()}\n{bands.loc[b, 'share']:.0%} of site-weeks" for b in order], bands.loc[order, "rate"], color=[RED, AMBER, GREEN], width=0.6)
    for k, b in enumerate(order):
        chip(ax, k, bands.loc[b, "rate"], f"{bands.loc[b, 'rate']:.2%} · {bands.loc[b, 'lift']:.1f}×")
    ax.set_yticks([])
    ax = chart(fig, R2[0], "Test-period incidents flagged amber or red in the 4 weeks before, by type", pl=0.11)
    wt = N["warned_by_type"]
    hbar(ax, [f"{r['what']} ({r['size']})" for r in wt] + ["All incidents"], [r["mean"] for r in wt] + [N["warned_share"]], fmt="{:.0%}",
         colors=[BLUE] * len(wt) + [BAND])
    textcard(fig, R2[1], "What the real-world check shows", [
        ("It works on real sites", f"Alerts fixed on 2024 to mid-2025 caught {N['warned_share']:.0%} of {N['incidents_scored_test']} later accidents and incidents "
         f"in the 4 weeks before; red site-weeks ({bands.loc['red', 'share']:.0%} of all) had {bands.loc['red', 'lift']:.0f}× the average rate.", GREEN),
        ("Exposure carries most of it", f"Job size and type alone rank sites at AUC {N['auc_base']:.2f}. Big structural, excavation and demolition jobs are where incidents happen.", AMBER),
        ("Warning signs still add", f"On large jobs they lift AUC from {L['auc_base']:.2f} to {L['auc']:.2f}; a site with an incident in the past year was "
         f"{rs[0]['ratio']:.0f}× as likely to have another within 4 weeks.", HI),
        ("Not the zone model itself", "Regulator records are sparse, site-level and partly reactive. A contractor pilot on daily logs is still the real test.", RED)], fs=6.9)
    return fig


def build():
    d = load()
    out = C.OUT / "dashboards"
    out.mkdir(parents=True, exist_ok=True)
    figs = [p1(d), p2(d), p3(d), p4(d), p5(d), p6(d), p7(d), p8(d)] + ([p9(d)] if "nyc" in d["S"] else [])
    with PdfPages(out / "site_safety_early_warning_dashboards.pdf") as pdf:
        for f, name in zip(figs, FILES):
            f.savefig(out / f"{name}.png", dpi=220, facecolor=BG)
            pdf.savefig(f, facecolor=BG)
            plt.close(f)
    docs = C.ROOT / "docs" / "dashboards"
    docs.mkdir(parents=True, exist_ok=True)
    for p in out.iterdir():
        shutil.copy2(p, docs / p.name)
    print(f"{len(figs)} dashboards written to {out} and {docs}")


if __name__ == "__main__":
    build()
