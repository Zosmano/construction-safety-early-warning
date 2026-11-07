"""Local storage (SQLite). Same tables and columns as schema_postgres.sql, minus row-level security,
which PostgreSQL enforces in production. Every query filters by tenant_id."""
import sqlite3
from pathlib import Path

CONSTRUCTION_ZONES = {
    "EXC": "Excavation & shoring", "CRN": "Tower crane & lift zone", "FRM": "Formwork & concrete pours",
    "DCK": "Open decks & slab edges", "SCF": "Scaffold & facade", "ROF": "Roof & mechanical penthouse",
    "MEP": "Electrical & mechanical rough-in", "INT": "Interior finishing", "GTE": "Gate, loading dock & site traffic",
    "LAY": "Laydown, hoist & material handling",
}

DDL = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('general_contractor', 'subcontractor')),
    sector TEXT NOT NULL DEFAULT 'construction' CHECK (sector IN ('construction', 'manufacturing')),
    active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS zone_layouts (
    sector TEXT NOT NULL, zone_code TEXT NOT NULL, zone_name TEXT NOT NULL, PRIMARY KEY (sector, zone_code));
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY, tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL, jurisdiction TEXT NOT NULL CHECK (jurisdiction IN
        ('BC','AB','SK','MB','ON','QC','NB','NS','PE','NL','YT','NT','NU')),
    city TEXT NOT NULL, latitude REAL, longitude REAL,
    sector TEXT NOT NULL DEFAULT 'construction', active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS ingestion_events (
    event_id TEXT NOT NULL, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, source TEXT NOT NULL,
    log_date TEXT NOT NULL, received_at TEXT NOT NULL, PRIMARY KEY (tenant_id, event_id));
CREATE TABLE IF NOT EXISTS zone_days (
    tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, log_date TEXT NOT NULL, zone_code TEXT NOT NULL,
    crew INTEGER NOT NULL, crew_hours REAL NOT NULL, near_misses INTEGER NOT NULL DEFAULT 0,
    hazard_obs INTEGER NOT NULL DEFAULT 0, ppe_gaps_pct REAL NOT NULL DEFAULT 0, housekeeping REAL NOT NULL DEFAULT 85,
    new_workers_pct REAL NOT NULL DEFAULT 0, overtime_pct REAL NOT NULL DEFAULT 0, trades INTEGER NOT NULL DEFAULT 1,
    permit_issues INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL, event_id TEXT NOT NULL, received_at TEXT NOT NULL,
    PRIMARY KEY (project_id, log_date, zone_code));
CREATE TABLE IF NOT EXISTS day_weather (
    project_id TEXT NOT NULL, log_date TEXT NOT NULL, gust REAL, humidex REAL, wet INTEGER, freeze INTEGER,
    PRIMARY KEY (project_id, log_date));
CREATE TABLE IF NOT EXISTS site_events (
    tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, log_date TEXT NOT NULL, zone_code TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('High-potential near miss', 'Health-care injury', 'Time-loss injury')), event_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS programme_activities (
    tenant_id TEXT NOT NULL, project_id TEXT NOT NULL, activity TEXT NOT NULL, zone_code TEXT NOT NULL,
    start_date TEXT NOT NULL, finish_date TEXT NOT NULL, crew INTEGER NOT NULL, source TEXT NOT NULL, synced_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS worker_reports (
    report_id INTEGER PRIMARY KEY AUTOINCREMENT, tenant_id TEXT NOT NULL, project_id TEXT NOT NULL,
    zone_code TEXT, category TEXT NOT NULL, text TEXT NOT NULL, language_code TEXT NOT NULL,
    translation_status TEXT NOT NULL CHECK (translation_status IN ('not_needed', 'pending', 'done')),
    text_en TEXT, received_date TEXT NOT NULL);   -- date only: no time, IP or device, to keep reports anonymous
"""


def connect(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(DDL)
    con.executemany("INSERT OR IGNORE INTO zone_layouts VALUES ('construction', ?, ?)", CONSTRUCTION_ZONES.items())
    con.commit()
    return con


def zones_for(con, sector):
    return {r["zone_code"] for r in con.execute("SELECT zone_code FROM zone_layouts WHERE sector = ?", (sector,))}
