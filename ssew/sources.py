"""Parse the public safety statistics and weather that calibrate the site model.

    WorkSafeBC Statistics 2024        BC construction rates, claims mix, deaths by year, death narratives
    AWCBC NWISP 2020-2022             lost-time claims by event (construction, Canada) and BC construction claims
    Alberta OHS PSI report 2020       potentially serious incidents in construction: types, share without injury
    ECCC hourly climate, YVR          real shift-hour weather for every work day
"""
import re
import urllib.request

import numpy as np
import pandas as pd
import pymupdf

from . import config as C

NUM = re.compile(r"^(X|\d[\d,]*)\b")


def download():
    C.RAW.mkdir(parents=True, exist_ok=True)
    (C.RAW / "weather").mkdir(exist_ok=True)
    get = lambda url, path: path.write_bytes(urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=180).read())
    for name, url in C.SOURCES.items():
        if not (C.RAW / name).exists():
            get(url, C.RAW / name)
            print("downloaded", name)
    if not (C.RAW / C.STATCAN_LFS[0]).exists():
        get(C.STATCAN_LFS[1], C.RAW / C.STATCAN_LFS[0])
    for pv in C.PROVINCES.values():
        for y in C.WEATHER_YEARS:
            for m in range(1, 13):
                p = C.RAW / "weather" / f"{pv['code']}_{y}_{m:02d}.csv"
                if not p.exists():
                    get(C.WEATHER_URL.format(st=pv["station"], y=y, m=m), p)
    print("weather ready")


def statcan_employment():
    """Construction employment by province (thousands), Labour Force Survey annual table 14-10-0023."""
    import zipfile
    z = zipfile.ZipFile(C.RAW / C.STATCAN_LFS[0])
    df = pd.read_csv(z.open("14100023.csv"), low_memory=False,
                     usecols=["REF_DATE", "GEO", "Labour force characteristics", "North American Industry Classification System (NAICS)",
                              "Gender", "Age group", "VALUE"])
    c = df[df["North American Industry Classification System (NAICS)"].str.startswith("Construction", na=False)
           & (df["Labour force characteristics"] == "Employment") & (df.Gender == "Total - Gender")
           & (df["Age group"] == "15 years and over")]
    return c.pivot_table(index="REF_DATE", columns="GEO", values="VALUE")


def provincial_rates(aw, emp):
    """Accepted lost-time claims per 100 construction workers, 2020-2022: AWCBC claims / LFS employment.
    Boards differ in coverage and what counts as lost time, so rates compare each province with itself."""
    out = {}
    for k, pv in C.PROVINCES.items():
        col = {"BC": "bc", "ON": "on", "AB": "ab"}[k]
        rates = {y: aw["construction_by_year"][y][col] / (emp.loc[y, pv["geo"]] * 1000) * 100 for y in (2020, 2021, 2022)}
        out[k] = {"rate": float(np.mean(list(rates.values()))), "by_year": rates,
                  "claims": {y: aw["construction_by_year"][y][col] for y in (2020, 2021, 2022)},
                  "employment_k": {int(y): float(emp.loc[y, pv["geo"]]) for y in emp.index if y >= 2020},
                  "fatalities": {y: aw["construction_fatalities"][y].get(col) for y in (2020, 2021, 2022)}}
    return out


def _n(tok):
    return np.nan if tok == "X" else float(tok.replace(",", ""))


# ---------------------------------------------------------------------------------------------- WorkSafeBC
def worksafebc():
    d = pymupdf.open(C.RAW / "worksafebc_statistics_2024.pdf")
    pages = [p.get_text() for p in d]
    out = {}
    # Figure 1.9 serious-injury time-loss claims rate by sector, 2020-2024
    t = next(p for p in pages if "Figure 1.9" in p and "72 — Construction" in p)
    L = [l.strip() for l in t[t.find("72 — Construction"):].splitlines() if l.strip()]
    out["serious_rate"] = dict(zip(range(2020, 2025), [float(x) for x in L[1:6]]))
    # Figure 2.10 time-loss claims rate and duration, general construction
    t = next(p for p in pages if "Figure 2.10" in p and "7210" in p)
    L = [l.strip() for l in t.splitlines() if l.strip()]
    i = L.index("General Construction")
    out["time_loss_rate"], out["avg_duration_days"] = float(L[i + 1]), float(L[i + 2])
    # Figure 2.7 claims first paid in 2024, general construction (7210)
    t = next(p for p in pages if "Sector 72 — Construction" in p and "Figure 2.7" in p)
    L = [l.strip() for l in t[t.find("Sector 72"):].splitlines() if l.strip()]
    i = L.index("7210")
    vals = [float(x.replace(",", "")) for x in L[i + 2:i + 8]]
    out["claims_2024"] = dict(zip(["health_care_only", "short_term_disability", "long_term_disability",
                                   "deaths", "total", "days_lost"], vals))
    # Figure 1.4 work-related death claims, general construction, 2015-2024
    t = next(p for p in pages if "Figure 1.4" in p and "7210" in p)
    L = [l.strip() for l in t.splitlines() if l.strip()]
    i = L.index("7210")
    out["deaths_by_year"] = dict(zip(range(2015, 2025), [int(x) for x in L[i + 3:i + 13]]))
    out["narratives"] = narratives(pages)
    return out


def narratives(pages):
    """Work-related deaths accepted in 2024, construction subsectors: occupation, age and what happened."""
    txt = "\n".join(p for p in pages if "Incident description" in p)
    rows = []
    for part in re.split(r"\n(?=7[0-6]\d0\s*\n)", txt):
        if not part.strip().startswith("72"):
            continue
        s = " ".join(part.split())
        m = re.match(r"(72\d0) (.+?(?:Construction|Maintenance)) (\d{4}) (.+?) (\d{2,3}) (.+)", s)
        if m:
            desc = re.split(r" Work-related deaths and serious injury \|", m.group(6))[0]
            rows.append({"subsector": m.group(1), "year_of_death": int(m.group(3)), "occupation": m.group(4),
                         "age": int(m.group(5)), "description": desc.strip()})
    df = pd.DataFrame(rows)
    df["hazard"] = df.description.map(classify)
    return df


HAZARD_RULES = [  # first match wins; mirrors the site's hazard families
    ("Exposure (asbestos, fumes)", r"asbestos|mesothelioma|fumes|lung cancer"),
    ("Electrical contact", r"power line|electric"),
    ("Struck by crane load / falling object", r"crane|flytable|fell .*floors|wall form"),
    ("Fall from height", r"fell \d+ ft|scaffold|roof"),
    ("Slip, trip or fall on same level", r"slipped|slippery"),
    ("Struck by or caught in", r"lathe|chute|pinning|pinned|rock flew"),
    ("Vehicles and mobile equipment", r"\bvehicle|\btruck\b|snowplow|scissor lift|\broad"),
    ("Struck by or caught in", r"struck|crush"),
    ("Infection and other", r"."),
]


def classify(text):
    t = text.lower()
    return next(name for name, pat in HAZARD_RULES if re.search(pat, t))


# ---------------------------------------------------------------------------------------------- AWCBC
def awcbc():
    d = pymupdf.open(C.RAW / "awcbc_nwisp_2020_2022.pdf")
    out = {}
    # Table 15: BC construction accepted lost-time claims 2020-2022
    t = next(p.get_text() for p in d if "Table 15" in p.get_text() and "23\nConstruction\n2020" in p.get_text())
    L = [l.strip() for l in t[t.find("23\nConstruction\n2020"):].splitlines() if l.strip()]
    bc = {}
    for y in ("2020", "2021", "2022"):
        i = L.index(y)
        row = [_n(x) for x in L[i + 1:i + 15]]      # Total, NL, PE, NS, NB, QC, ON, MB, SK, AB, BC, NT/NU, YT, Total
        bc[int(y)] = {"canada": row[0], "bc": row[10], "ab": row[9], "on": row[6]}
    out["construction_by_year"] = bc
    # Fatalities by industry and jurisdiction: construction, 2020-2022 (X = suppressed)
    t = next(p.get_text() for p in d if "Fatalities" in p.get_text() and "Industry and Jurisdiction" in p.get_text()
             and "23\nConstruction\n2020" in p.get_text())
    L = [l.strip() for l in t[t.find("23\nConstruction\n2020"):].splitlines() if l.strip()]
    fat = {}
    for y in ("2020", "2021", "2022"):
        i = L.index(y)
        row = [_n(x) for x in L[i + 1:i + 15]]
        fat[int(y)] = {"canada": row[0], "on": row[6], "ab": row[9], "bc": row[10]}
    out["construction_fatalities"] = fat
    # Table 21: lost-time claims by event, construction column (Canada), 2021 and 2022
    rows = []
    for p in d:
        t = p.get_text()
        if "Table 21" not in t or "Utilities" not in t or "Agriculture" not in t:
            continue
        L = [l.strip() for l in t.splitlines() if l.strip()]
        i = 0
        while i < len(L):
            if re.fullmatch(r"\d{2}", L[i]) and i + 1 < len(L) and not NUM.match(L[i + 1]):
                code, name, j = L[i], [], i + 1
                while j < len(L) and not NUM.match(L[j]):
                    name.append(L[j])
                    j += 1
                nums = [NUM.match(x).group(1) for x in L[j:j + 10]] if all(NUM.match(x) for x in L[j:j + 10]) else None
                if nums and len(nums) == 10:
                    rows.append({"code": code, "event": " ".join(name), "canada_2021": _n(nums[0]),
                                 "canada_2022": _n(nums[1]), "construction_2021": _n(nums[8]),
                                 "construction_2022": _n(nums[9])})
                    i = j + 10
                    continue
            i += 1
    ev = pd.DataFrame(rows).drop_duplicates("code")
    out["events"] = ev
    return out


EVENT_FAMILY = {  # AWCBC event codes (two-digit) -> site hazard family
    "Struck by or caught in": ["00", "01", "02", "03", "05", "06", "09"],
    "Excavation / collapse": ["04"],
    "Fall from height": ["11", "12"],                      # fall / jump to lower level
    "Slip, trip or fall on same level": ["10", "13", "19"],
    "Overexertion and bodily reaction": ["20", "21", "22", "23", "24", "25", "26", "27", "29"],
    "Exposure (electrical, heat, substances)": ["30", "31", "32", "33", "34", "35", "36", "37", "38", "39"],
    "Vehicles and mobile equipment": ["40", "41", "42", "43", "44", "45", "46", "49"],
    "Fire and explosion": ["50", "51", "52", "59"],
}


def event_mix(ev):
    """Share of construction lost-time claims in each site hazard family (2021-2022 combined)."""
    ev = ev.assign(n=ev.construction_2021.fillna(0) + ev.construction_2022.fillna(0))
    fam = {code: f for f, codes in EVENT_FAMILY.items() for code in codes}
    ev["family"] = ev.code.map(fam)
    s = ev.dropna(subset=["family"]).groupby("family").n.sum()
    return (s / s.sum()).sort_values(ascending=False)


# ---------------------------------------------------------------------------------------------- Alberta PSI
def alberta_psi():
    d = pymupdf.open(C.RAW / "alberta_psi_construction_2020.pdf")
    t = "\n".join(p.get_text() for p in d)
    total = int(re.search(r"Total PSIs reported\s*\n(\d+)", t).group(1))
    share = int(re.search(r"PSIs with\s*\ninjuries\s*\n(\d+)%", t).group(1)) / 100
    page3 = d[2].get_text()
    L = [l.strip() for l in page3.splitlines() if l.strip()]
    nums = [int(x) for x in L if x.isdigit()][:5]
    names = [l for l in L if not l.isdigit() and l[0].isupper() and "PSI" not in l and "Current" not in l and "Page" not in l][:5]
    return {"total": total, "share_with_injury": share, "types": dict(zip(names, nums))}


# ---------------------------------------------------------------------------------------------- weather
def weather(code="yvr"):
    frames = []
    for p in sorted((C.RAW / "weather").glob(f"{code}_*.csv")):
        w = pd.read_csv(p, encoding="utf-8-sig")
        frames.append(w)
    w = pd.concat(frames, ignore_index=True)
    w["dt"] = pd.to_datetime(w["Date/Time (LST)"])
    w = w.rename(columns={"Temp (°C)": "temp", "Precip. Amount (mm)": "rain", "Wind Spd (km/h)": "wind",
                          "Hmdx": "humidex", "Rel Hum (%)": "rh", "Weather": "wx"})
    w = w[(w.dt.dt.hour >= C.SHIFT[0]) & (w.dt.dt.hour <= C.SHIFT[1])]
    g = w.groupby(w.dt.dt.normalize())
    wet = w.wx.astype(str).str.contains("Rain|Drizzle|Shower", case=False)
    day = pd.DataFrame({
        "temp_max": g.temp.max(), "temp_min": g.temp.min(),
        "rain_hours": wet.groupby(w.dt.dt.normalize()).sum(),   # hourly files report weather type, not mm
        "wind_max": g.wind.max(), "humidex_max": g.humidex.max(),
        "snow_or_ice": g.wx.apply(lambda s: s.astype(str).str.contains("Snow|Ice|Freezing", case=False).any()),
    })
    # ECCC reports mean wind; gusts on a 30 m crane jib run well above it, so screen on 1.5 x the hourly mean
    day["gust_est"] = day.wind_max * 1.5
    # direction (tens of degrees, where the wind comes from) at the windiest shift hour
    wd = w.dropna(subset=["wind"]).sort_values("wind").groupby(w.dt.dt.normalize())["Wind Dir (10s deg)"].last()
    day["wind_dir"] = wd * 10
    day["humidex_max"] = day.humidex_max.fillna(day.temp_max)
    return day
