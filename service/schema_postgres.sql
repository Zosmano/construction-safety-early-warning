-- Production schema (PostgreSQL 15+). Same tables as service/db.py, plus row-level security so a
-- tenant can only ever read or write its own rows, even if application code forgets a filter.
-- The API sets the tenant per request:  SET LOCAL app.tenant_id = '<tenant uuid>';

CREATE TYPE account_type AS ENUM ('general_contractor', 'subcontractor');
CREATE TYPE sector AS ENUM ('construction', 'manufacturing');
CREATE TYPE site_event_kind AS ENUM ('High-potential near miss', 'Health-care injury', 'Time-loss injury');

CREATE TABLE tenants (
    tenant_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name         text NOT NULL,
    account_type account_type NOT NULL,
    sector       sector NOT NULL DEFAULT 'construction',
    active       boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- Zone layouts are data, not a CHECK constraint, so a manufacturing layout can be added later
-- without changing any table.
CREATE TABLE zone_layouts (
    sector    sector NOT NULL,
    zone_code text NOT NULL,
    zone_name text NOT NULL,
    PRIMARY KEY (sector, zone_code)
);
INSERT INTO zone_layouts VALUES
 ('construction','EXC','Excavation & shoring'), ('construction','CRN','Tower crane & lift zone'),
 ('construction','FRM','Formwork & concrete pours'), ('construction','DCK','Open decks & slab edges'),
 ('construction','SCF','Scaffold & facade'), ('construction','ROF','Roof & mechanical penthouse'),
 ('construction','MEP','Electrical & mechanical rough-in'), ('construction','INT','Interior finishing'),
 ('construction','GTE','Gate, loading dock & site traffic'), ('construction','LAY','Laydown, hoist & material handling');

CREATE TABLE projects (
    project_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    uuid NOT NULL REFERENCES tenants ON DELETE CASCADE,
    name         text NOT NULL,
    jurisdiction char(2) NOT NULL CHECK (jurisdiction IN ('BC','AB','SK','MB','ON','QC','NB','NS','PE','NL','YT','NT','NU')),
    city         text NOT NULL,
    latitude     numeric(9,6),
    longitude    numeric(9,6),
    sector       sector NOT NULL DEFAULT 'construction',
    active       boolean NOT NULL DEFAULT true,
    UNIQUE (tenant_id, project_id)
);

CREATE TABLE ingestion_events (
    tenant_id   uuid NOT NULL,
    event_id    text NOT NULL,                   -- the sender's id: makes retries idempotent
    project_id  uuid NOT NULL,
    source      text NOT NULL,
    log_date    date NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, project_id) ON DELETE CASCADE
);

-- One row per project, day and zone. Counts only: no worker names, IDs or hashes are stored.
CREATE TABLE zone_days (
    tenant_id       uuid NOT NULL,
    project_id      uuid NOT NULL,
    log_date        date NOT NULL,
    zone_code       text NOT NULL,
    crew            integer NOT NULL CHECK (crew >= 0),
    crew_hours      numeric(8,1) NOT NULL,
    near_misses     integer NOT NULL DEFAULT 0,
    hazard_obs      integer NOT NULL DEFAULT 0,
    ppe_gaps_pct    numeric(5,1) NOT NULL DEFAULT 0,
    housekeeping    numeric(5,1) NOT NULL DEFAULT 85,
    new_workers_pct numeric(5,1) NOT NULL DEFAULT 0,
    overtime_pct    numeric(5,1) NOT NULL DEFAULT 0,
    trades          integer NOT NULL DEFAULT 1,
    permit_issues   integer NOT NULL DEFAULT 0,
    source          text NOT NULL,
    event_id        text NOT NULL,
    received_at     timestamptz NOT NULL,
    PRIMARY KEY (project_id, log_date, zone_code),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, project_id) ON DELETE CASCADE
) PARTITION BY RANGE (log_date);
CREATE TABLE zone_days_2026 PARTITION OF zone_days FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE zone_days_2027 PARTITION OF zone_days FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');

CREATE TABLE day_weather (
    tenant_id uuid NOT NULL, project_id uuid NOT NULL, log_date date NOT NULL,
    gust numeric(5,1), humidex numeric(4,1), wet boolean, freeze boolean,
    PRIMARY KEY (project_id, log_date),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE site_events (
    tenant_id uuid NOT NULL, project_id uuid NOT NULL, log_date date NOT NULL, zone_code text NOT NULL,
    kind site_event_kind NOT NULL, event_id text NOT NULL,
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE TABLE programme_activities (
    tenant_id uuid NOT NULL, project_id uuid NOT NULL, activity text NOT NULL, zone_code text NOT NULL,
    start_date date NOT NULL, finish_date date NOT NULL CHECK (finish_date >= start_date),
    crew integer NOT NULL CHECK (crew >= 0), source text NOT NULL, synced_at timestamptz NOT NULL,
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, project_id) ON DELETE CASCADE
);

-- Anonymous worker reports. Date only: no time, IP address or device id, so a report can't be
-- traced to the person who sent it.
CREATE TABLE worker_reports (
    report_id          bigserial PRIMARY KEY,
    tenant_id          uuid NOT NULL,
    project_id         uuid NOT NULL,
    zone_code          text,
    category           text NOT NULL CHECK (category IN ('hazard','near_miss','idea','other')),
    text               text NOT NULL CHECK (length(text) <= 2000),
    language_code      text NOT NULL,                 -- e.g. en, fr, pa, zh-hant
    translation_status text NOT NULL CHECK (translation_status IN ('not_needed','pending','done')),
    text_en            text,
    received_date      date NOT NULL DEFAULT current_date,
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX ON zone_days (tenant_id, project_id, log_date);
CREATE INDEX ON ingestion_events (tenant_id, project_id, received_at);
CREATE INDEX ON worker_reports (tenant_id, project_id, language_code, translation_status);

-- Row-level security: every tenant-owned table is visible only to the tenant set for the session.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['projects','ingestion_events','zone_days','day_weather','site_events',
                           'programme_activities','worker_reports'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'')::uuid) '
                   'WITH CHECK (tenant_id = current_setting(''app.tenant_id'')::uuid)', t);
  END LOOP;
END $$;
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_self ON tenants USING (tenant_id = current_setting('app.tenant_id')::uuid);
