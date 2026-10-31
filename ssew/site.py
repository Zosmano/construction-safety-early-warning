"""The site: a hypothetical 24-storey concrete residential tower in Burnaby, BC, simulated zone by zone over a
30-month programme on real Vancouver shift weather.

What is real and what is simulated
- Real: shift-hour weather (ECCC, YVR), the base injury rate (WorkSafeBC general construction time-loss claims
  per 100 person-years), the serious-injury share (WorkSafeBC), the mix of injury events (AWCBC construction
  lost-time claims by event) and the near-miss ratio (Alberta construction potentially serious incidents).
- Simulated: the site, its schedule and crews, the leading indicators a site would log (near misses, hazard
  observations, PPE and housekeeping audits, permits, new workers, overtime, trade congestion) and a latent
  zone "safety climate" that drifts over weeks and drives both the indicators and the incidents.
The model never sees the latent climate; it has to infer rising risk from the indicators, as a site would.
"""
import numpy as np
import pandas as pd

from . import config as C

# Zones: id, name, plan polygon (100 x 64 site plan units), hazard families with weights, phases it is busy in
ZONES = [
    ("EXC", "Excavation & shoring", [(8, 30), (46, 30), (46, 58), (8, 58)],
     {"Excavation / collapse": 3, "Struck by or caught in": 2, "Vehicles and mobile equipment": 2, "Fall from height": 1}, ["excavation", "foundations"]),
    ("CRN", "Tower crane & lift zone", [(48, 30), (64, 30), (64, 46), (48, 46)],
     {"Struck by or caught in": 3, "Fall from height": 1}, ["foundations", "structure", "envelope"]),
    ("FRM", "Formwork & concrete pours", [(8, 6), (46, 6), (46, 28), (8, 28)],
     {"Struck by or caught in": 2, "Overexertion and bodily reaction": 2, "Slip, trip or fall on same level": 1}, ["foundations", "structure"]),
    ("DCK", "Open decks & slab edges", [(48, 6), (72, 6), (72, 28), (48, 28)],
     {"Fall from height": 3, "Slip, trip or fall on same level": 2, "Struck by or caught in": 1}, ["structure"]),
    ("SCF", "Scaffold & façade", [(74, 6), (94, 6), (94, 28), (74, 28)],
     {"Fall from height": 3, "Struck by or caught in": 1, "Overexertion and bodily reaction": 1}, ["envelope"]),
    ("ROF", "Roof & mechanical penthouse", [(74, 30), (94, 30), (94, 46), (74, 46)],
     {"Fall from height": 3, "Exposure (electrical, heat, substances)": 1, "Overexertion and bodily reaction": 1}, ["envelope", "interiors"]),
    ("MEP", "Electrical & mechanical rough-in", [(66, 30), (72, 30), (72, 46), (66, 46)],
     {"Exposure (electrical, heat, substances)": 2, "Overexertion and bodily reaction": 2, "Struck by or caught in": 1, "Fire and explosion": 1}, ["structure", "interiors"]),
    ("INT", "Interior finishing", [(48, 48), (94, 48), (94, 58), (48, 58)],
     {"Overexertion and bodily reaction": 3, "Slip, trip or fall on same level": 2, "Exposure (electrical, heat, substances)": 1}, ["interiors"]),
    ("GTE", "Gate, loading dock & site traffic", [(0, 0), (6, 0), (6, 64), (0, 64)],
     {"Vehicles and mobile equipment": 3, "Struck by or caught in": 1, "Slip, trip or fall on same level": 1}, ["excavation", "foundations", "structure", "envelope", "interiors", "sitework"]),
    ("LAY", "Laydown, hoist & material handling", [(8, 60), (94, 60), (94, 64), (8, 64)],
     {"Overexertion and bodily reaction": 3, "Struck by or caught in": 2, "Slip, trip or fall on same level": 1}, ["foundations", "structure", "envelope", "interiors", "sitework"]),
]
ZONE_IDS = [z[0] for z in ZONES]

PHASES = {  # programme (start, end, peak crew per busy zone)
    "excavation": ("2023-03-01", "2023-08-15", 22),
    "foundations": ("2023-06-15", "2024-01-31", 30),
    "structure": ("2023-12-01", "2024-12-20", 34),
    "envelope": ("2024-06-01", "2025-04-30", 26),
    "interiors": ("2024-10-01", "2025-08-29", 38),
    "sitework": ("2025-04-01", "2025-08-29", 14),
}
CRANE = ("2023-08-01", "2025-01-31")       # tower crane on site


def schedule(days):
    """Planned crew per zone per day: each phase ramps up and down; zones share their phases' crews."""
    crew = pd.DataFrame(0.0, index=days, columns=ZONE_IDS)
    for zid, _, _, _, phases in ZONES:
        for ph in phases:
            s, e, peak = PHASES[ph]
            s, e = pd.Timestamp(s), pd.Timestamp(e)
            t = ((days - s) / (e - s)).values
            ramp = np.clip(np.sin(np.pi * np.clip(t, 0, 1)) * 1.4, 0, 1)
            crew[zid] += np.where((t >= 0) & (t <= 1), peak * ramp, 0)
    crew = crew / crew.max().replace(0, 1) * pd.Series(CAP)          # each zone peaks at a realistic crew
    on = (days >= CRANE[0]) & (days <= CRANE[1])
    crew["CRN"] = np.where(on, np.maximum(crew["CRN"], 4), 0)
    crew["GTE"] = crew["GTE"].clip(lower=3)
    return crew.round()


CAP = {"EXC": 28, "CRN": 10, "FRM": 40, "DCK": 34, "SCF": 26, "ROF": 22, "MEP": 38, "INT": 46, "GTE": 12, "LAY": 18}


SITES = [  # a national contractor's portfolio (hypothetical): site, province, crew scale relative to the flagship
    ("Burnaby", "BC", 1.0), ("Surrey", "BC", 0.8), ("Richmond", "BC", 0.9), ("Coquitlam", "BC", 0.7),
    ("Vancouver", "BC", 1.2), ("North Vancouver", "BC", 0.75), ("New Westminster", "BC", 0.85), ("Langley", "BC", 0.65),
    ("Toronto", "ON", 1.3), ("Mississauga", "ON", 1.0), ("Vaughan", "ON", 0.9), ("Markham", "ON", 0.8),
    ("Calgary", "AB", 1.1), ("Airdrie", "AB", 0.7), ("Cochrane", "AB", 0.6),
    # 15 more sites: doubling the training data lifted test AUC on the original 15 sites from 0.73 to 0.75
    ("Kelowna", "BC", 0.7), ("Victoria", "BC", 0.8), ("Abbotsford", "BC", 0.6), ("Port Moody", "BC", 0.55),
    ("Delta", "BC", 0.7), ("Maple Ridge", "BC", 0.6), ("Ottawa", "ON", 1.0), ("Hamilton", "ON", 0.85),
    ("Brampton", "ON", 1.1), ("Oakville", "ON", 0.7), ("Kitchener", "ON", 0.75), ("Edmonton", "AB", 1.2),
    ("Red Deer", "AB", 0.6), ("Lethbridge", "AB", 0.55), ("St. Albert", "AB", 0.65),
]
FLAGSHIP = "Burnaby"


def portfolio(weathers, sources):
    """Each site runs on its province's real weather and is calibrated to its province's construction claims
    rate; crews, climate and incidents are its own."""
    out = []
    for k, (name, prov, s) in enumerate(SITES):
        rate = sources["worksafebc"]["time_loss_rate"] if prov == "BC" else sources["provinces"][prov]["rate"]
        out.append(simulate(weathers[prov], sources, seed=C.SEED + k, scale=s, rate=rate))
    df = pd.concat([o[0].assign(site=n, province=p) for o, (n, p, _) in zip(out, SITES)], ignore_index=True)
    ev = pd.concat([o[1].assign(site=n, province=p) for o, (n, p, _) in zip(out, SITES)], ignore_index=True)
    return df, ev, out[0][2]


def simulate(weather, sources, seed=C.SEED, scale=1.0, rate=None):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(C.START, C.END)
    days = days[days.isin(weather.index)]
    W = weather.reindex(days)
    crew = (schedule(days) * scale).round()
    n, Z = len(days), len(ZONE_IDS)

    # base hazard per worker-hour: BC general construction time-loss rate per 100 person-years
    tl_rate = (rate or sources["worksafebc"]["time_loss_rate"]) / (100 * C.PERSON_YEAR_HOURS)
    claims = sources["worksafebc"]["claims_2024"]
    hco_ratio = claims["health_care_only"] / (claims["short_term_disability"] + claims["long_term_disability"] + claims["deaths"])
    serious_share = sources["worksafebc"]["serious_rate"][2024] / sources["worksafebc"]["time_loss_rate"]
    mix = sources["event_mix"]

    # latent safety climate per zone: slow AR(1) drift with occasional deteriorating episodes (new subcontractor,
    # schedule crunch); unobserved by the model
    climate = np.zeros((n, Z))
    for j in range(Z):
        x = 0.0
        for i in range(n):
            if rng.random() < 0.015:                      # an episode starts (new subcontractor, schedule crunch)
                x += rng.uniform(0.8, 1.6)
            x = 0.95 * x + rng.normal(0, 0.05)            # episodes fade over two to four weeks
            climate[i, j] = x

    # observable drivers
    gust, hum = W.gust_est.values, W.humidex_max.values
    wet = (W.rain_hours.values >= C.WET_HOURS).astype(float)
    freeze = ((W.temp_min.values <= C.FREEZE_C) | W.snow_or_ice.values.astype(bool)).astype(float)
    high_wind = (gust >= C.CRANE_GUST_KMH).astype(float)
    heat = (hum >= C.HUMIDEX_HEAT).astype(float)

    # pass 1: hazard multipliers; pass 2 rescales them so the whole site runs at BC's construction rate
    zone_data = {}
    for j, (zid, name, _, fam, _) in enumerate(ZONES):
        c = crew[zid].values
        busy = c > 0
        ramp = np.r_[0, np.diff(c)].clip(min=0)
        new_share = np.clip(0.06 + 0.5 * ramp / np.maximum(c, 1) + 0.04 * climate[:, j] + rng.normal(0, 0.03, n), 0, 0.6)
        overtime = np.clip(0.05 + 0.06 * climate[:, j] + 0.03 * (c > np.percentile(c[busy], 75) if busy.any() else 0)
                           + rng.normal(0, 0.03, n), 0, 0.5)
        trades = np.clip(np.round(1 + c / 9 + rng.normal(0, 0.7, n)), 0, None) * busy
        weather_mult = np.ones(n)
        if zid in ("CRN", "SCF", "ROF"):
            weather_mult *= np.exp(0.9 * high_wind)
        if zid in ("DCK", "SCF", "ROF", "GTE", "LAY", "EXC"):
            weather_mult *= np.exp(0.45 * wet + 0.8 * freeze)
        if zid in ("ROF", "DCK", "FRM", "LAY"):
            weather_mult *= np.exp(0.5 * heat)
        if zid == "EXC":
            weather_mult *= np.exp(0.5 * wet)              # saturated soil and shoring loads
        logh = (1.3 * climate[:, j] + 1.6 * (new_share - 0.06) + 1.8 * (overtime - 0.05)
                + 0.06 * np.maximum(trades - 3, 0) + np.log(weather_mult))
        zone_data[zid] = (c, busy, new_share, overtime, trades, np.exp(logh))
    hrs = sum((v[0] * 8).sum() for v in zone_data.values())
    scale = hrs / sum((v[0] * 8 * v[5]).sum() for v in zone_data.values())

    rows = []
    for j, (zid, name, _, fam, _) in enumerate(ZONES):
        c, busy, new_share, overtime, trades, hz = zone_data[zid]
        hz = hz * scale
        hours = c * 8
        lam_tl = tl_rate * hours * hz
        tl = rng.poisson(lam_tl)
        hco = rng.poisson(lam_tl * hco_ratio)
        near = rng.poisson(lam_tl * (1 + hco_ratio) * C.NEAR_MISS_RATIO)
        # all reported near misses and close calls (most low-potential): what a site actually logs every day
        reported = near + rng.poisson(lam_tl * (1 + hco_ratio) * C.NEAR_MISS_RATIO * 5)
        # leading indicators logged daily (noisy views of the same latent hazard)
        obs_rate = np.where(busy, 0.02 * np.sqrt(np.maximum(c, 1)) * hz ** 0.9, 0)
        hazard_obs = rng.poisson(obs_rate * 10)
        ppe = np.clip(0.04 + 0.05 * climate[:, j] + rng.normal(0, 0.015, n), 0, 0.5) * busy
        house = np.clip(88 - 9 * climate[:, j] - 4 * (trades > 4) + rng.normal(0, 3, n), 30, 100) * busy
        permits = rng.poisson(np.where(busy, 0.05 * hz, 0))
        for i in range(n):
            if not busy[i] and tl[i] + hco[i] + near[i] == 0:
                continue
            rows.append((days[i], zid, c[i], hours[i], new_share[i], overtime[i], trades[i], hazard_obs[i], ppe[i],
                         house[i], permits[i], reported[i], near[i], hco[i], tl[i], hz[i], climate[i, j]))
    df = pd.DataFrame(rows, columns=["date", "zone", "crew", "hours", "new_worker_share", "overtime_share", "trades",
                                     "hazard_obs", "ppe_noncompliance", "housekeeping", "permit_issues",
                                     "reported_near_misses", "near_misses", "health_care_injuries",
                                     "time_loss_injuries", "true_hazard", "latent_climate"])
    df = df.merge(W.rename_axis("date").reset_index(), on="date", how="left")
    # each injury gets an event family from the zone's hazards weighted by AWCBC's construction mix
    fams = {z[0]: z[3] for z in ZONES}
    ev = []
    for r in df.itertuples():
        for kind, k in (("Time-loss injury", r.time_loss_injuries), ("Health-care injury", r.health_care_injuries),
                        ("High-potential near miss", r.near_misses)):
            for _ in range(int(k)):
                f = fams[r.zone]
                p = np.array([f[x] * mix.get(x, 0.01) for x in f]) * _weather_tilt(r, list(f))
                fam = rng.choice(list(f), p=p / p.sum())
                serious = kind == "Time-loss injury" and rng.random() < serious_share * 1.0
                ev.append({"date": r.date, "zone": r.zone, "kind": kind, "family": fam, "serious": bool(serious)})
    events = pd.DataFrame(ev)
    return df, events, crew


def _weather_tilt(r, fams):
    t = np.ones(len(fams))
    for k, f in enumerate(fams):
        if f == "Slip, trip or fall on same level" and (r.rain_hours >= C.WET_HOURS or r.temp_min <= C.FREEZE_C):
            t[k] = 2.0
        if f == "Fall from height" and r.gust_est >= C.CRANE_GUST_KMH:
            t[k] = 1.6
        if f == "Exposure (electrical, heat, substances)" and r.humidex_max >= C.HUMIDEX_HEAT:
            t[k] = 2.0
    return t
