"""Send one signed sample daily log to a running service, to test an installation end to end.

    python -m service.send_sample http://localhost:8770 T1 P1        (uses SSEW_WEBHOOK_SECRETS for T1)
"""
import json
import os
import sys
import urllib.request
import uuid
from datetime import date
from pathlib import Path

from .security import sign


def main(argv=None):
    url, tenant, project = (argv if argv is not None else sys.argv[1:])[:3]
    raw = os.environ["SSEW_WEBHOOK_SECRETS"]
    secret = json.loads(raw if raw.strip().startswith("{") else Path(raw).read_text())[tenant]
    payload = {"event_id": str(uuid.uuid4()), "project_id": project, "log_date": date.today().isoformat(), "source": "sample",
               "weather": {"gust": 38, "wet": False},
               "zones": {"FRM": {"near_misses": 1, "hazard_obs": 3, "housekeeping": 82.5, "roster": [
                   {"worker_ref": "SAMPLE-0001", "trade": "Formwork", "hours": 10, "new_hire": True},
                   {"worker_ref": "SAMPLE-0002", "trade": "Electrical", "hours": 8}]}}}
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url.rstrip("/") + "/v1/daily-logs", data=body, method="POST", headers={
        "Content-Type": "application/json", "X-SSEW-Tenant": tenant, "X-SSEW-Signature": sign(secret, body)})
    with urllib.request.urlopen(req) as r:
        print(r.status, r.read().decode())


if __name__ == "__main__":
    main()
