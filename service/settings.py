"""Settings come only from the environment, so no secret ever sits in the code or the repository.

SSEW_DB               SQLite file for local runs (production uses PostgreSQL, see schema_postgres.sql)
SSEW_WEBHOOK_SECRETS  JSON {tenant_id: secret} or a path to such a file; signs daily-log webhooks
SSEW_API_KEYS         JSON {tenant_id: key} or a path; read access for a tenant's own projects
SSEW_REPORT_TOKENS    JSON {project_id: token} or a path; printed in the gate-poster QR code
SSEW_ID_PEPPER        random string used to de-duplicate workers within one request; never stored
SSEW_MAX_SKEW_S       accepted webhook clock difference in seconds (default 300)
"""
import json
import os
from pathlib import Path


class SettingsError(RuntimeError):
    pass


def _mapping(name, required=True):
    raw = os.environ.get(name, "").strip()
    if not raw:
        if required:
            raise SettingsError(f"{name} is not set. See service/settings.py.")
        return {}
    if not raw.startswith("{"):
        raw = Path(raw).read_text(encoding="utf-8")
    data = json.loads(raw)
    weak = [k for k, v in data.items() if len(str(v)) < 32]
    if weak:
        raise SettingsError(f"{name}: secrets must be at least 32 characters (too short for {', '.join(weak)})")
    return data


def load():
    pepper = os.environ.get("SSEW_ID_PEPPER", "")
    if len(pepper) < 32:
        raise SettingsError("SSEW_ID_PEPPER must be set to a random string of at least 32 characters.")
    return {
        "db": os.environ.get("SSEW_DB", str(Path(__file__).resolve().parent.parent / "data" / "service.db")),
        "webhook_secrets": _mapping("SSEW_WEBHOOK_SECRETS"),
        "api_keys": _mapping("SSEW_API_KEYS"),
        "report_tokens": _mapping("SSEW_REPORT_TOKENS", required=False),
        "pepper": pepper.encode(),
        "max_skew": int(os.environ.get("SSEW_MAX_SKEW_S", "300")),
    }
