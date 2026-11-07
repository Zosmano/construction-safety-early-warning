# Ingestion service

This service takes site data into the early-warning model automatically, so a supervisor doesn't
have to type every day into the dashboard. It's a Python (FastAPI) service, in the same language
as the model, and stores data per tenant.

| Endpoint | What it does |
|---|---|
| `POST /v1/daily-logs` | Signed webhook: one project-day of zone readings, as counts or as a gate/badge roster |
| `POST /v1/projects/{id}/worker-reports` | Anonymous report from the gate-poster QR code, with its language |
| `GET /v1/projects/{id}/confidence` | Scan confidence, using the same rule as the dashboard |
| `GET /v1/projects/{id}/feed` | Logged days in the dashboard's feed format, for retraining |

A weekly job (`schedule_sync.py`) refreshes each project's look-ahead programme.

## Run it locally

```
pip install -r requirements.txt
python -m service.admin new-secret          # run once for each secret below
```

Then set these, using your own generated values, never the examples:

```
$env:SSEW_ID_PEPPER = "<secret>"
$env:SSEW_WEBHOOK_SECRETS = '{"T1": "<secret>"}'
$env:SSEW_API_KEYS = '{"T1": "<secret>"}'
$env:SSEW_REPORT_TOKENS = '{"P1": "<secret>"}'
python -m service.admin add-tenant T1 "Example Builders" general_contractor
python -m service.admin add-project T1 P1 "East Hastings School Expansion" BC Vancouver
uvicorn service.app:app --port 8770
python -m service.send_sample http://localhost:8770 T1 P1
```

The last command sends a signed sample log and prints `202` with `"status": "accepted"`.

To retrain on what has come in:

```
python -m service.admin export-feed T1 P1 feed.json
python run_all.py --feed feed.json
```

Tests: `python -m pytest tests` (no secrets or network needed).

## Security and privacy

- **Signed webhooks:** `X-SSEW-Signature: t=<unix>,v1=<HMAC-SHA256 of "<t>." + raw body>`. The
  HMAC covers the exact bytes received, a timestamp older than 5 minutes is refused to block
  replays, and the comparison runs in constant time. Each tenant has its own secret.
- **Retries are safe:** each log carries an `event_id`, and the same id is accepted only once.
- **No secrets in code:** the service won't start without its secrets set, and refuses any secret
  under 32 characters.
- **No worker identifiers are kept:** a roster of badge numbers is turned into counts (crew,
  hours, trades, new-worker and overtime shares), and the badge numbers are then dropped.
  De-duplication uses a keyed hash that exists only in memory during the request. Even a salted
  hash isn't stored, because anyone holding the salt can re-link it to a person, so it still
  counts as personal information.
- **Anonymous reports stay anonymous:** they keep the date only, with no time, IP address or
  device. Reports not in English are marked `pending` for translation. Nothing is sent to an
  outside translation service automatically, because the worker's words would leave your
  systems. Add one only with a data-processing agreement.
- **Tenants are isolated:** every query filters by tenant. In production, the row-level security
  in `schema_postgres.sql` enforces this in the database itself.
- **Inputs are checked:** zones must belong to the project's layout, numbers have ranges, and
  unknown top-level fields are refused, so a sender can't slip in names.

## Programme sync

`python -m service.schedule_sync --all` replaces each project's programme in one step. If a file
is bad, the old programme stays. Schedule it weekly:

```
schtasks /Create /TN "ssew-programme-sync" /SC WEEKLY /D SUN /ST 22:00 /TR "powershell -File C:\path\to\run_weekly_sync.ps1"
```

The `file` connector reads a Primavera P6 or MS Project export saved as CSV in the dashboard's
format (`activity, zone, start, finish, crew`), from a shared folder for example.

The Procore and Autodesk Build connectors are placeholders. They need an approved developer app
(OAuth) and sandbox access to build and test against, so they refuse to run until then rather
than guess at those platforms' APIs. Each platform also signs its webhooks its own way, so each
connector must verify that platform's documented scheme.

## Multi-tenancy and other sectors

Tenants are general contractors or subcontractors, and each has a sector. Zone codes live in a
`zone_layouts` table, not in a fixed check, so a manufacturing layout can be added as rows later.
The model itself is trained on construction zones only: a factory layout would need its own data
and training before it could be scored.
