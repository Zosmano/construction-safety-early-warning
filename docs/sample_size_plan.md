# How much real data the accuracy test needs

This is a planning study (`analysis/sample_size.py`). It resamples whole sites from the simulated
test period, 71 sites over 10 months, to see how precisely each accuracy figure is pinned down
by a given amount of data. It says how big a real test must be, not what the test will find.

## Precision by number of incidents

95% ranges, near misses and injuries combined:

| Incidents | Typical source | Share warned in advance | Ranking quality (AUC) |
|---:|---|---|---|
| about 25 | 3 sites × 10 months | 49% to 100% | 0.64 to 0.89 |
| about 70 | 10 sites × 6 months | 75% to 96% | 0.69 to 0.83 |
| about 170 | 20 sites × 10 months | 75% to 91% | 0.74 to 0.83 |
| about 350 | 40 sites × 10 months | 76% to 88% | 0.76 to 0.82 |

- **Under about 50 incidents:** any result is too uncertain to quote. A 10-percentage-point
  difference could be chance.
- **About 150 to 200 incidents:** enough to quote the share warned within about ±8 points, and
  the ranking quality within about ±0.05.
- **About 300 or more:** enough for figures precise enough to compare provinces or zone types.

## What that means in site data

A simulated site averages 65 workers and records about 2.6 injuries (time-loss plus health-care
claims) and 6.6 high-potential near misses a year. That injury rate is in line with BC
construction's roughly 3 claims per 100 workers.

| Data you get | Incidents per site-year | Site-years for about 170 incidents |
|---|---:|---:|
| Daily logs with near misses and injuries | about 9 | about 19 (e.g. 20 sites for a year) |
| Injury claims only | about 2.6 | about 65 |

**Near misses matter most.** A contractor who logs near misses gives about 3.5 times as much
test data per site as injury claims alone.

## Caveats

- **Real performance may be lower:** these ranges assume real sites behave like the simulated
  ones. If the real signal is weaker, the gap over the crew-size baseline (simulated: AUC 0.79
  against 0.71) shrinks, and more data is needed to show it.
- **WorkSafeBC claims can't test the daily model alone.** The model scores daily inputs (near
  misses, hazard observations, crew, weather). Claim records give outcomes but usually not those
  inputs. They can check injury rates by trade and site size, while the full test needs
  contractors' daily logs alongside the outcomes.
- **One site per company isn't enough:** days on one site are alike, so 20 sites over a year
  tells you more than 5 sites over four years.

## What to ask for

1. **From WorkSafeBC:** construction claims by month, trade (classification unit), employer size
   and injury type for 2019 to 2025, anonymized. This calibrates base rates and checks the
   season and weather effects.
2. **From pilot contractors:** daily site logs (crew by area, near misses, hazard observations,
   inspections) with their recorded incidents for at least 12 months. Aim for about 20 sites in
   total, which could come from 3 or 4 contractors.
3. **Then a forward test:** score each day before it happens on the pilot sites, and compare the
   warnings with what follows for 6 to 12 months.
