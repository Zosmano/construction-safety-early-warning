"""Set up tenants and projects, and export a project's logged days for retraining.

    python -m service.admin add-tenant T1 "Example Builders" general_contractor
    python -m service.admin add-project T1 P1 "East Hastings School Expansion" BC Vancouver
    python -m service.admin export-feed T1 P1 feed.json     # then: python run_all.py --feed feed.json
    python -m service.admin new-secret                      # prints a random 48-character secret
"""
import json
import os
import secrets
import sys
from pathlib import Path

from . import db
from .app import feed_docs


def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    if a[0] == "new-secret":
        print(secrets.token_urlsafe(36))
        return 0
    con = db.connect(os.environ.get("SSEW_DB", str(Path(__file__).resolve().parent.parent / "data" / "service.db")))
    if a[0] == "add-tenant":
        _, tid, name, kind, *rest = a
        with con:
            con.execute("INSERT INTO tenants (tenant_id, name, account_type, sector) VALUES (?,?,?,?)",
                        (tid, name, kind, rest[0] if rest else "construction"))
    elif a[0] == "add-project":
        _, tid, pid, name, jur, city, *rest = a
        sector = con.execute("SELECT sector FROM tenants WHERE tenant_id = ?", (tid,)).fetchone()["sector"]
        with con:
            con.execute("INSERT INTO projects (project_id, tenant_id, name, jurisdiction, city, sector) VALUES (?,?,?,?,?,?)",
                        (pid, tid, name, jur.upper(), city, sector))
    elif a[0] == "export-feed":
        _, tid, pid, out = a
        docs = feed_docs(con, tid, pid)
        Path(out).write_text(json.dumps({"docs": docs}, indent=1), encoding="utf-8")
        print(f"{len(docs)} logged days written to {out}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
