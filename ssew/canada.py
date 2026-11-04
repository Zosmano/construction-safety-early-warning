"""All 10 provinces and 3 territories: published construction statistics, and the portfolio's cities and weather stations.

    AWCBC NWISP 2022-2024            construction lost-time claims and fatalities by jurisdiction; claims by event
    Statistics Canada LFS            construction employment, 10 provinces (table 14-10-0023)
    Statistics Canada SEPH           construction employees, territories (table 14-10-0201), a check on the estimate below
    CNESST lesions 2022, 2023        every accepted Quebec injury record, construction sector: event, cause, injury, age
    Ontario MLITSD 2015-2024         construction fatalities and critical injuries
    ECCC hourly climate              real shift-hour weather at the hourly station nearest each city

The federal-jurisdiction files (Employer's Annual Hazardous Occurrence Report) cover air, rail, water, ports and the federal
public service, not construction, so they are not used. Nor is the fatal-claim investigation count, which covers all WSIB industries.
"""
import concurrent.futures as cf
import csv
import json
import math
import re
import urllib.request

import numpy as np
import pandas as pd
import pymupdf

from . import config as C

DIR = C.RAW / "canada"
AWCBC = DIR / "National-Work-Injury-Disease-and-Fatality-Statistics-2022-2024.pdf"
ORDER = ["NL", "PE", "NS", "NB", "QC", "ON", "MB", "SK", "AB", "BC", "NTNU", "YT"]   # AWCBC columns after Total
NAMES = {"BC": "British Columbia", "AB": "Alberta", "SK": "Saskatchewan", "MB": "Manitoba", "ON": "Ontario", "QC": "Quebec",
         "NB": "New Brunswick", "NS": "Nova Scotia", "PE": "Prince Edward Island", "NL": "Newfoundland and Labrador",
         "YT": "Yukon", "NT": "Northwest Territories", "NU": "Nunavut"}
JURS = list(NAMES)
NORTH = ("YT", "NT", "NU")
BOARD = {"BC": "WorkSafeBC", "AB": "WCB-Alberta; Alberta OHS", "SK": "WCB Saskatchewan; WorkSafe Saskatchewan", "MB": "WCB Manitoba; SAFE Work Manitoba",
         "ON": "WSIB; Ontario Ministry of Labour", "QC": "CNESST", "NB": "WorkSafeNB", "NS": "WCB Nova Scotia; NS Labour",
         "PE": "WCB PEI", "NL": "WorkplaceNL; NL OHS Branch", "YT": "Yukon WCHSB", "NT": "WSCC (NT and NU)", "NU": "WSCC (NT and NU)"}
# territories' workers come from SEPH (employees only), because the LFS table doesn't cover them: see seph_check.
TERR = {"YT": ["Yukon"], "NTNU": ["Northwest Territories", "Nunavut"]}

# city, jurisdiction, latitude, longitude, crew scale, project type
CITIES = [
    ("Burnaby", "BC", 49.25, -122.95, 1.0, "tower"), ("Surrey", "BC", 49.19, -122.85, .8, "midrise"), ("Vancouver", "BC", 49.28, -123.12, 1.2, "tower"),
    ("Richmond", "BC", 49.17, -123.14, .9, "tower"), ("Kelowna", "BC", 49.89, -119.50, .7, "midrise"), ("Victoria", "BC", 48.43, -123.37, .8, "midrise"),
    ("Kamloops", "BC", 50.67, -120.33, .6, "civil"), ("Prince George", "BC", 53.92, -122.75, .6, "industrial"), ("Fort St. John", "BC", 56.25, -120.85, .6, "industrial"),
    ("Toronto", "ON", 43.65, -79.38, 1.3, "tower"), ("Mississauga", "ON", 43.59, -79.64, 1.0, "tower"), ("Brampton", "ON", 43.73, -79.76, 1.1, "midrise"),
    ("Ottawa", "ON", 45.42, -75.70, 1.0, "tower"), ("Hamilton", "ON", 43.26, -79.87, .85, "industrial"), ("Kitchener", "ON", 43.45, -80.49, .75, "midrise"),
    ("London", "ON", 42.98, -81.25, .75, "midrise"), ("Windsor", "ON", 42.31, -83.04, .7, "industrial"), ("Kingston", "ON", 44.23, -76.49, .6, "civil"),
    ("Sudbury", "ON", 46.49, -81.00, .6, "civil"), ("Thunder Bay", "ON", 48.38, -89.25, .6, "civil"), ("Barrie", "ON", 44.39, -79.69, .7, "midrise"),
    ("Montreal", "QC", 45.50, -73.57, 1.3, "tower"), ("Laval", "QC", 45.57, -73.69, .9, "midrise"), ("Quebec City", "QC", 46.81, -71.21, 1.0, "tower"),
    ("Gatineau", "QC", 45.48, -75.70, .8, "midrise"), ("Sherbrooke", "QC", 45.40, -71.89, .7, "midrise"), ("Trois-Rivieres", "QC", 46.34, -72.54, .65, "industrial"),
    ("Saguenay", "QC", 48.43, -71.07, .6, "civil"), ("Rimouski", "QC", 48.45, -68.52, .55, "civil"),
    ("Calgary", "AB", 51.05, -114.07, 1.1, "tower"), ("Edmonton", "AB", 53.55, -113.49, 1.2, "tower"), ("Red Deer", "AB", 52.27, -113.81, .6, "midrise"),
    ("Lethbridge", "AB", 49.69, -112.84, .55, "midrise"), ("Medicine Hat", "AB", 50.04, -110.68, .55, "civil"), ("Grande Prairie", "AB", 55.17, -118.80, .6, "industrial"),
    ("Fort McMurray", "AB", 56.73, -111.38, .9, "industrial"),
    ("Winnipeg", "MB", 49.90, -97.14, 1.0, "tower"), ("Brandon", "MB", 49.85, -99.95, .6, "midrise"), ("Thompson", "MB", 55.74, -97.86, .55, "industrial"), ("Gimli", "MB", 50.63, -96.99, .5, "civil"),
    ("Saskatoon", "SK", 52.13, -106.67, .9, "midrise"), ("Regina", "SK", 50.45, -104.62, .9, "midrise"), ("Prince Albert", "SK", 53.20, -105.75, .55, "civil"), ("Estevan", "SK", 49.14, -102.99, .55, "industrial"),
    ("Halifax", "NS", 44.65, -63.57, 1.0, "tower"), ("Sydney", "NS", 46.14, -60.19, .6, "civil"), ("Truro", "NS", 45.37, -63.28, .55, "midrise"), ("Yarmouth", "NS", 43.84, -66.12, .5, "civil"),
    ("Moncton", "NB", 46.09, -64.78, .9, "midrise"), ("Saint John", "NB", 45.27, -66.06, .9, "industrial"), ("Fredericton", "NB", 45.96, -66.64, .85, "midrise"),
    ("Miramichi", "NB", 47.00, -65.50, .6, "civil"), ("Bathurst", "NB", 47.62, -65.65, .6, "civil"), ("Edmundston", "NB", 47.37, -68.33, .6, "midrise"),
    ("St. John's", "NL", 47.56, -52.71, .9, "midrise"), ("Gander", "NL", 48.95, -54.61, .55, "civil"), ("Corner Brook", "NL", 48.95, -57.95, .55, "midrise"),
    ("Happy Valley-Goose Bay", "NL", 53.30, -60.42, .6, "industrial"), ("Labrador City", "NL", 52.94, -66.91, .6, "industrial"),
    ("Charlottetown", "PE", 46.24, -63.13, .8, "midrise"), ("Summerside", "PE", 46.40, -63.79, .6, "midrise"), ("Montague", "PE", 46.17, -62.65, .5, "civil"),
    ("Whitehorse", "YT", 60.72, -135.05, .55, "midrise"), ("Dawson City", "YT", 64.06, -139.43, .4, "civil"), ("Watson Lake", "YT", 60.06, -128.71, .4, "civil"),
    ("Yellowknife", "NT", 62.45, -114.37, .55, "midrise"), ("Inuvik", "NT", 68.36, -133.72, .4, "civil"), ("Hay River", "NT", 60.82, -115.79, .45, "civil"),
    ("Iqaluit", "NU", 63.75, -68.52, .5, "midrise"), ("Rankin Inlet", "NU", 62.81, -92.09, .4, "civil"), ("Cambridge Bay", "NU", 69.12, -105.06, .4, "civil"),
]
LEGACY = {51442: "yvr", 51459: "yyz", 50430: "yyc"}                 # hourly files already held under these names


def _n(tok):
    return np.nan if tok == "X" else float(tok.replace(",", ""))


def _table_row(doc, title, code="23\nConstruction\n"):
    """Rows of a Table 15 / Table 36 style page for one industry: year -> Total + 12 jurisdiction columns."""
    t = next(p.get_text() for p in doc if title in p.get_text() and code in p.get_text())
    L = [x.strip() for x in t[t.find(code):].splitlines() if x.strip()]
    out = {}
    for y in ("2022", "2023", "2024"):
        i = L.index(y)
        v = [_n(x) for x in L[i + 1:i + 14]]
        out[int(y)] = dict(zip(["canada"] + ORDER, v))
    return out


def awcbc_tables():
    d = pymupdf.open(AWCBC)
    claims = _table_row(d, "Table 15\nNumber of Accepted Lost Time Claims, by Industry")
    deaths = _table_row(d, "Table 36\nNumber of Fatalities, by Industry")
    # Table 21: claims by event, construction column, 2023 and 2024 (same layout as the 2020-2022 edition)
    NUM = re.compile(r"^(X|\d[\d,]*)\b")
    rows = []
    for p in d:
        t = p.get_text()
        if "Table 21" not in t or "Utilities" not in t or "Agriculture" not in t:
            continue
        L = [x.strip() for x in t.splitlines() if x.strip()]
        i = 0
        while i < len(L):
            if re.fullmatch(r"\d{2}", L[i]) and i + 1 < len(L) and not NUM.match(L[i + 1]):
                code, name, j = L[i], [], i + 1
                while j < len(L) and not NUM.match(L[j]):
                    name.append(L[j])
                    j += 1
                vals = L[j:j + 10]
                if len(vals) == 10 and all(NUM.match(x) for x in vals):
                    nums = [NUM.match(x).group(1) for x in vals]
                    rows.append({"code": code, "event": " ".join(name), "canada_2023": _n(nums[0]), "canada_2024": _n(nums[1]),
                                 "construction_2023": _n(nums[8]), "construction_2024": _n(nums[9])})
                    i = j + 10
                    continue
            i += 1
    events = pd.DataFrame(rows).drop_duplicates("code")
    return claims, deaths, events


def rates(claims, deaths, emp, seph):
    """Claims per 100 construction workers by jurisdiction, on the median of 2022-2024 claims, so that one year's reporting
    change doesn't set the rate (Ontario's 2024 count is 81% above 2023). NT and NU report together: both get the combined rate."""
    out = {}
    for k in ORDER:
        cl = {y: claims[y][k] for y in claims}
        fat = {y: None if np.isnan(deaths[y][k]) else deaths[y][k] for y in deaths}
        if k in ("YT", "NTNU"):
            workers = sum(seph[g] for g in TERR[k]) / 1000
        else:
            col = NAMES[k]
            workers = float(emp.loc[[y for y in emp.index if y >= 2022], col].mean())
        rate = float(np.median(list(cl.values()))) / (workers * 1000) * 100
        for code in (("NT", "NU") if k == "NTNU" else (k,)):
            out[code] = {"name": NAMES[code], "rate": rate, "claims": cl, "fatalities": fat, "workers_k": workers,
                         "combined": k == "NTNU", "quality": "employees only" if k in ("YT", "NTNU") else "published"}
    out["BC"]["computed_rate"] = out["BC"]["rate"]
    return out


GENRE_FAMILY = [  # CNESST accident type -> site hazard family
    ("Fall from height", r"CHUTE A UN NIVEAU INF"), ("Slip, trip or fall on same level", r"CHUTE AU MEME|TREBUCH|GLISS"),
    ("Struck by or caught in", r"FRAPPE|HEURTER|COINCE|FROTTEM|CONTACT"), ("Overexertion and bodily reaction", r"EFFORT|REACTION DU CORPS|MOUVEMENT REPET|POSTURE"),
    ("Vehicles and mobile equipment", r"ROUTE|VEHIC|TRANSPORT"), ("Fire and explosion", r"FEU|INCENDIE|EXPLOS(?!\.)|EXPLOSION"),
    ("Exposure (electrical, heat, substances)", r"EXPOS|ELECTR|TEMPERATURE|BRUIT"),
]


def quebec():
    """Every accepted construction-sector injury record in Quebec, 2022-2023. COVID-19 records are removed, and noise-induced
    hearing loss is counted apart because its coding moved between the two years."""
    fr = []
    for y in (2022, 2023):
        d = pd.read_csv(DIR / f"lesions-{y}_Quebec.csv", encoding="utf-8-sig", dtype=str)
        fr.append(d[d.SECTEUR_SCIAN.str.contains("CONSTRUCTION", na=False)].assign(year=y))
    d = pd.concat(fr, ignore_index=True)
    total, covid = len(d), int((d.IND_LESION_COVID_19 == "OUI").sum())
    d = d[d.IND_LESION_COVID_19 != "OUI"]
    deaf = int((d.IND_LESION_SURDITE == "OUI").sum())
    inj = d[d.IND_LESION_SURDITE != "OUI"]

    def fam(g):
        g = str(g)
        return next((n for n, pat in GENRE_FAMILY if re.search(pat, g)), "Other")
    mix = inj.GENRE.map(fam).value_counts(normalize=True)
    top = lambda col, n=8: {k: int(v) for k, v in inj[col].value_counts().head(n).items()}
    return {"records": total, "covid_removed": covid, "hearing_loss": deaf, "by_year": d.year.value_counts().sort_index().to_dict(),
            "family_mix": mix.to_dict(), "top_event": top("GENRE"), "top_cause": top("AGENT_CAUSAL_LESION"), "top_injury": top("NATURE_LESION"),
            "top_body": top("SIEGE_LESION"), "age": {k: int(v) for k, v in inj.GROUPE_AGE.value_counts().sort_index().items()},
            "machine_share": float((inj.IND_LESION_MACHINE == "OUI").mean()), "msd_share": float((inj.IND_LESION_TMS == "OUI").mean())}


def ontario_outcomes():
    f = pd.read_csv(DIR / "fatalities_Ontario_2015_2024.csv")
    c = pd.read_csv(DIR / "critical_injuries_Ontario_2015_2024.csv")
    col = "Construction Health and Safety Program"
    return {"fatalities": dict(zip(f["Calendar Year"].astype(int), f[col].astype(int))),
            "critical_injuries": dict(zip(c["Calendar Year"].astype(int), c[col].astype(int)))}


def national_2024():
    """Canada 2024 all-industry and construction totals from the AWCBC workbooks."""
    from openpyxl import load_workbook
    out = {}
    for key, name in (("lost_time", "Lost-time-claims-2024.xlsx"), ("fatal", "Fatalities-data-2024.xlsx")):
        ws = load_workbook(DIR / name, data_only=True, read_only=True)["Industry"]
        for r in ws.iter_rows(values_only=True):
            v = [x for x in r if x is not None]
            if len(v) >= 2 and isinstance(v[1], (int, float)):
                if str(v[0]).strip() == "Construction":
                    out[key + "_construction"] = int(v[1])
                if str(v[0]).startswith(("Lost Time Claims", "Fatalities")):
                    out.setdefault(key + "_all", int(v[1]))
    return out


def seph_check(path=None):
    """Average construction employees, territories (SEPH, employees only: leaves out the self-employed and may miss crews from the south)."""
    p = C.RAW / "canada" / "seph_territories.csv"
    if not p.exists():
        return {}
    d = pd.read_csv(p)
    naics = [c for c in d.columns if "North American" in c][0]
    d = d[d["Type of employee"].eq("All employees") & d[naics].eq("Construction [23]")]
    d = d[d.REF_DATE.str[:4].astype(int).between(2022, 2024)]
    return d.groupby("GEO").VALUE.mean().round(0).to_dict()


# ---------------------------------------------------------------------------------------------- stations and weather
def _dist(a, b, c, e):
    r = math.pi / 180
    x = (e - b) * r * math.cos((a + c) * r / 2)
    return math.hypot(x, (c - a) * r) * 6371


def station_candidates():
    """Stations from ECCC's station list with hourly data across 2023-2025."""
    rows = list(csv.DictReader(open(DIR / "Station_search_results_Environment.csv", encoding="utf-8-sig")))
    out = []
    for r in rows:
        f, l = r["Hourly data first year"], r["Hourly data last year"]
        if f and l and f[:4] <= "2023" and l[:4] >= "2025":
            out.append((r["Station name"], float(r["Latitude (decimal degrees)"]), float(r["Longitude (decimal degrees)"]), r["Climate Identifier"]))
    return out


def _get(url, tries=3):
    for k in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "site-safety-early-warning/1.0"}), timeout=120).read()
        except Exception as e:
            err = e
    raise err


def station_id(climate_id):
    j = json.loads(_get(f"https://api.weather.gc.ca/collections/climate-stations/items?f=json&CLIMATE_IDENTIFIER={climate_id}"))
    return int(j["features"][0]["properties"]["STN_ID"]) if j["features"] else None


def choose_stations():
    """Each city -> the nearest station that really reports hourly wind and weather in a test month. Saved so the choice is stable."""
    p = DIR / "stations.json"
    if p.exists():
        return json.loads(p.read_text())
    cand, ids, good, out = station_candidates(), {}, {}, {}

    def test(cid):
        if cid in good:
            return good[cid]
        ids[cid] = station_id(cid)
        ok = False
        if ids[cid]:
            t = _get(C.WEATHER_URL.format(st=ids[cid], y=2024, m=7)).decode("utf-8-sig", "replace").splitlines()
            rec = list(csv.DictReader(t))
            ok = len(rec) > 500 and sum(1 for r in rec if r.get("Wind Spd (km/h)")) > 0.7 * len(rec) and sum(1 for r in rec if r.get("Temp (°C)")) > 0.7 * len(rec)
        good[cid] = ok
        return ok
    for name, prov, lat, lon, *_ in CITIES:
        ranked = sorted(cand, key=lambda s: _dist(lat, lon, s[1], s[2]))[:12]
        for s in ranked:
            if test(s[3]):
                out[name] = {"station": ids[s[3]], "name": s[0], "km": round(_dist(lat, lon, s[1], s[2])), "climate_id": s[3]}
                break
        print(name, prov, out.get(name), flush=True)
    p.write_text(json.dumps(out, indent=0))
    return out


def code_of(station):
    return LEGACY.get(station, f"s{station}")


def download_weather():
    st = choose_stations()
    (C.RAW / "weather").mkdir(parents=True, exist_ok=True)
    jobs = []
    for sid in {v["station"] for v in st.values()}:
        for y in C.WEATHER_YEARS:
            for m in range(1, 13):
                p = C.RAW / "weather" / f"{code_of(sid)}_{y}_{m:02d}.csv"
                if not p.exists():
                    jobs.append((sid, y, m, p))
    print(len(jobs), "station-months to fetch", flush=True)

    def one(j):
        sid, y, m, p = j
        p.write_bytes(_get(C.WEATHER_URL.format(st=sid, y=y, m=m)))
    with cf.ThreadPoolExecutor(10) as ex:
        list(ex.map(one, jobs))
    print("weather ready", flush=True)


if __name__ == "__main__":
    download_weather()
