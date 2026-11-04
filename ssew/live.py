"""Live forecasts for every city, saved at build time. The dashboard asks the forecast services itself where its host allows that,
and shows this snapshot, with its date, where it doesn't (a claude.ai artifact can't reach other websites)."""
import json
import datetime as dt
import urllib.request

from . import config as C

DAILY = "temperature_2m_min,apparent_temperature_min,apparent_temperature_max,wind_gusts_10m_max,precipitation_sum,precipitation_hours,snowfall_sum,weather_code"
UA = {"User-Agent": "site-safety-early-warning/1.0"}


def _get(url):
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read())


def snapshot(cities):
    path = C.OUT / "live_snapshot.json"
    try:
        lat, lon = ",".join(str(c[2]) for c in cities), ",".join(str(c[3]) for c in cities)
        fc = _get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily={DAILY}&timezone=auto&forecast_days=7")
        aq = _get(f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&hourly=pm2_5&timezone=auto&forecast_days=5")
        out = {"fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "source": "Open-Meteo", "cities": {}}
        for c, f, a in zip(cities, fc, aq):
            d = f["daily"]
            by_day = {}
            for t, v in zip(a["hourly"]["time"], a["hourly"]["pm2_5"]):
                if v is not None and 7 <= int(t[11:13]) <= 15:
                    by_day.setdefault(t[:10], []).append(v)
            out["cities"][c[0]] = {"d": d["time"], "gust": d["wind_gusts_10m_max"], "hi": d["apparent_temperature_max"], "lo": d["apparent_temperature_min"], "tmin": d["temperature_2m_min"],
                                   "ph": d["precipitation_hours"], "mm": d["precipitation_sum"], "snow": d["snowfall_sum"], "code": d["weather_code"],
                                   "pm": [round(sum(by_day[x]) / len(by_day[x]), 1) if x in by_day else None for x in d["time"]]}
        path.write_text(json.dumps(out))
        print("live snapshot:", len(out["cities"]), "cities", out["fetched"])
        return out
    except Exception as e:
        print("live snapshot not refreshed:", repr(e)[:200])
        return json.loads(path.read_text()) if path.exists() else None