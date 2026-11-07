"""Weekly programme sync: pull each project's look-ahead schedule into programme_activities.

    python -m service.schedule_sync --all          # every active project (run weekly, e.g. Sunday 22:00)
    python -m service.schedule_sync --project P1

Connectors, chosen per project in SSEW_SCHEDULE_SOURCES (JSON {project_id: {"type": ..., ...}} or a path):
  file      {"type": "file", "path": ".../programme.csv"}  CSV exported from Primavera P6 or MS Project in the
            dashboard's format (activity, zone, start, finish, crew). Works today, e.g. on a shared folder.
  procore   {"type": "procore", ...}   needs an approved Procore app (OAuth client) and its schedule API.
  autodesk  {"type": "autodesk", ...}  needs an Autodesk Platform Services app and Build schedule access.
The two platform connectors are deliberately not implemented until there is sandbox access to test against.
"""
import argparse
import csv
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import db


class NotConfigured(RuntimeError):
    pass


def read_csv(path, allowed_zones):
    rows, problems = [], []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for i, r in enumerate(csv.DictReader(fh), start=2):
            try:
                z = r["zone"].strip().upper()
                start, finish = date.fromisoformat(r["start"].strip()), date.fromisoformat(r["finish"].strip())
                crew = int(float(r["crew"]))
                if z not in allowed_zones:
                    raise ValueError(f"unknown zone {z}")
                if finish < start or crew < 0:
                    raise ValueError("finish before start or negative crew")
                rows.append((r["activity"].strip(), z, start.isoformat(), finish.isoformat(), crew))
            except (KeyError, ValueError) as e:
                problems.append(f"line {i}: {e}")
    return rows, problems


def fetch(source, allowed_zones):
    kind = source.get("type")
    if kind == "file":
        return read_csv(source["path"], allowed_zones)
    if kind in ("procore", "autodesk"):
        raise NotConfigured(f"{kind} connector needs an approved developer app and sandbox access; "
                            "use the file connector until then")
    raise NotConfigured(f"unknown schedule source type {kind!r}")


def sources():
    raw = os.environ.get("SSEW_SCHEDULE_SOURCES", "").strip()
    if not raw:
        return {}
    return json.loads(raw if raw.startswith("{") else Path(raw).read_text(encoding="utf-8"))


def sync_project(con, project, source):
    rows, problems = fetch(source, db.zones_for(con, project["sector"]))
    if problems and not rows:
        return {"project": project["project_id"], "status": "failed", "problems": problems[:10]}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with con:     # replace the project's programme in one transaction, so a failed sync leaves the old one
        con.execute("DELETE FROM programme_activities WHERE project_id = ?", (project["project_id"],))
        con.executemany("INSERT INTO programme_activities VALUES (?,?,?,?,?,?,?,?,?)",
                        [(project["tenant_id"], project["project_id"], *r, source["type"], now) for r in rows])
    return {"project": project["project_id"], "status": "synced", "activities": len(rows), "skipped_lines": problems}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true")
    g.add_argument("--project")
    args = ap.parse_args(argv)
    con = db.connect(os.environ.get("SSEW_DB", str(Path(__file__).resolve().parent.parent / "data" / "service.db")))
    src = sources()
    q = "SELECT * FROM projects WHERE active = 1" + ("" if args.all else " AND project_id = ?")
    projects = con.execute(q, () if args.all else (args.project,)).fetchall()
    code = 0
    for p in projects:
        if p["project_id"] not in src:
            print(f"{p['project_id']}: no schedule source configured, skipped")
            continue
        try:
            res = sync_project(con, p, src[p["project_id"]])
        except (NotConfigured, OSError) as e:
            res, code = {"project": p["project_id"], "status": "failed", "problems": [str(e)]}, 1
        if res["status"] == "failed":
            code = 1
        print(json.dumps(res))
    return code


if __name__ == "__main__":
    sys.exit(main())
