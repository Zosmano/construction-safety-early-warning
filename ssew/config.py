"""Every assumption in one place."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs"

# --- Public sources (fetched by `python run_all.py --download`) -----------------------------------------
SOURCES = {
    "worksafebc_statistics_2024.pdf": "https://www.worksafebc.com/-/media/WorksafeBC/Resources/about-us/annual-reports-and-statistics-reports/statistics-2024-pdf-en.ashx",
    "awcbc_nwisp_2020_2022.pdf": "https://awcbc.org/files/publications/National-Work-Injury-Disease-and-Fatality-Statistics-2020-2022.pdf",
    "alberta_psi_construction_2020.pdf": "https://open.alberta.ca/dataset/fac91ce1-e115-4ef6-9969-cb16baabce70/resource/d06f34a5-7a18-41ae-a47f-21ef761e51f1/download/lbr-psi-wcb-sector-report-2020-construction-and-construction-trade-services.pdf",
}
STATCAN_LFS = ("statcan_14100023.zip", "https://www150.statcan.gc.ca/n1/tbl/csv/14100023-eng.zip")
PROVINCES = {  # ECCC hourly station at each province's main construction market; AWCBC column name
    "BC": {"name": "British Columbia", "station": 51442, "code": "yvr", "city": "Vancouver Int'l A", "geo": "British Columbia"},
    "ON": {"name": "Ontario", "station": 51459, "code": "yyz", "city": "Toronto Int'l A", "geo": "Ontario"},
    "AB": {"name": "Alberta", "station": 50430, "code": "yyc", "city": "Calgary Int'l A", "geo": "Alberta"},
}
WEATHER_STATION = 51442          # Environment and Climate Change Canada: Vancouver Int'l A (hourly)
WEATHER_YEARS = (2023, 2024, 2025)
WEATHER_URL = ("https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID={st}"
               "&Year={y}&Month={m}&Day=1&timeframe=1")

# --- Calibration -----------------------------------------------------------------------------------------
PERSON_YEAR_HOURS = 2000          # WorkSafeBC rates are per 100 person-years of employment
# The site's base injury rate is set to BC general construction's (parsed from WorkSafeBC Statistics 2024):
# time-loss claims per 100 person-years (Figure 2.10) and the serious-injury rate (Figure 1.9).
NEAR_MISS_RATIO = 3.0            # high-potential near misses per injury: Alberta construction PSIs 2020, 75% without injury

# --- The site (hypothetical) -----------------------------------------------------------------------------
SITE_NAME = "Hypothetical 6-storey mixed-use build, Burnaby, BC"
START, END = "2023-03-01", "2025-08-29"     # 30-month programme, weekdays, on real Vancouver weather
SHIFT = (7, 15)                            # 07:00 to 15:30 working hours used for weather exposure
SEED = 11

# --- Early warning -----------------------------------------------------------------------------------------
HORIZON_DAYS = 5                 # predict a recordable injury or high-potential near miss in the next 5 work days
TRAIN_END = "2024-10-31"         # model trained on everything before; validated on the following 10 months
RED_SHARE, AMBER_SHARE = 0.05, 0.20   # alert bands: top 5% of zone-days red, next 15% amber (set on training data)

# Weather triggers (screening thresholds; site procedures and manufacturer limits govern in practice)
CRANE_GUST_KMH = 50              # tower-crane wind stand-down screen
HUMIDEX_HEAT = 30                # WorkSafeBC heat-stress screening begins around humidex 30
FREEZE_C = 1.0                   # ice/frost risk on decks and ramps
WET_HOURS = 3                    # shift hours with rain, drizzle or showers that make decks and ramps slippery
