-- PostGIS schema for the H2S exposure record.
--
-- The SQLite schema in hse/store.py is deliberately the same shape, so a pilot can start on a
-- laptop and migrate here without the application layer changing. What PostGIS adds is the
-- part SQLite cannot do honestly: a real geography type, spatial indexes, and therefore
-- spatial queries that are correct rather than approximated with a lat/lng bounding box.
--
--   CREATE DATABASE h2s_dosimetry;
--   \c h2s_dosimetry
--   \i hse/schema_postgis.sql
--
-- Requires PostgreSQL 12+ with PostGIS 3.

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- Reference data
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS plant_units (
    code            TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    -- Polygon, not a circle. hse.core models units as circles because the demo coordinates
    -- are illustrative and a hand-drawn polygon would imply a survey accuracy they do not
    -- have. Once a site supplies its GIS boundaries that reservation disappears, and a
    -- polygon is what actually answers "was this scan inside the unit".
    boundary        geography(POLYGON, 4326),
    centroid        geography(POINT, 4326) NOT NULL,
    -- Relative H2S likelihood of the service, 0..1. Orders operator attention. It must never
    -- be used to adjust a measured dose - the badge measures what the worker was exposed to,
    -- and weighting that by an expectation would destroy the evidence.
    h2s_propensity  REAL NOT NULL DEFAULT 0.2,
    sour_service    BOOLEAN NOT NULL DEFAULT FALSE,
    note            TEXT
);

CREATE INDEX IF NOT EXISTS plant_units_boundary_gix ON plant_units USING GIST (boundary);
CREATE INDEX IF NOT EXISTS plant_units_centroid_gix ON plant_units USING GIST (centroid);

CREATE TABLE IF NOT EXISTS workers (
    worker_id       TEXT PRIMARY KEY,
    name            TEXT,
    role            TEXT,
    home_unit       TEXT REFERENCES plant_units(code),
    contact         TEXT,
    active          BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS badges (
    badge_serial    TEXT PRIMARY KEY,
    lot_code        TEXT,
    manufactured_on DATE,
    expires_on      DATE,
    -- Per-lot unexposed pad colour, measured from that lot rather than assumed. The printed
    -- substrate patches on the badge handle illumination, but they do not age with the
    -- reagent; for badges stored a long time a per-lot baseline is the more faithful
    -- reference, and this is where it lives.
    baseline_lab    REAL[3],
    retired_on      DATE
);

-- ---------------------------------------------------------------------------
-- The exposure record
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS scans (
    id              BIGSERIAL PRIMARY KEY,
    scanned_at      TIMESTAMPTZ NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    worker_id       TEXT NOT NULL REFERENCES workers(worker_id),
    shift_id        TEXT,
    badge_serial    TEXT REFERENCES badges(badge_serial),

    geom            geography(POINT, 4326),
    accuracy_m      REAL,
    -- TRUE when the coordinate was generated rather than observed (no GPS fix at scan time).
    -- Stored rather than inferred from a null accuracy: a demonstration coordinate must never
    -- be indistinguishable from a surveyed one in a record that gets audited.
    location_mocked BOOLEAN NOT NULL DEFAULT FALSE,
    unit_code       TEXT REFERENCES plant_units(code),

    -- Reading. ok=false rows are kept on purpose: an unreadable badge means the worker's
    -- shift went unmonitored, which is a finding in its own right, and deleting those rows
    -- would make the monitoring statistics look better than the monitoring was.
    ok              BOOLEAN NOT NULL,
    verdict         TEXT NOT NULL,
    band            TEXT NOT NULL,
    dose_ppm_hr     DOUBLE PRECISION,
    twa_ppm         DOUBLE PRECISION,
    shift_hours     DOUBLE PRECISION,

    -- Observables. delta_l_star is primary and drives the dose; delta_e00 is the
    -- conventional colorimetric figure and is recorded alongside it.
    delta_l_star    DOUBLE PRECISION,
    delta_e00       DOUBLE PRECISION,
    chroma_residual DOUBLE PRECISION,
    channel_balance DOUBLE PRECISION,

    -- Provenance. Without these the number is an assertion rather than a measurement.
    baseline_source TEXT,
    ccm_mode        TEXT,
    reproj_rmse_mm  DOUBLE PRECISION,
    stage_failed    TEXT,
    reason          TEXT,
    operator_hint   TEXT,
    warnings        JSONB NOT NULL DEFAULT '[]'::jsonb,
    device          TEXT,
    app_version     TEXT,
    client_scan_id  UUID UNIQUE,     -- idempotency key for the offline queue flush
    image_sha256    TEXT,
    image_path      TEXT,
    result_json     JSONB NOT NULL,

    CONSTRAINT scans_dose_nonneg CHECK (dose_ppm_hr IS NULL OR dose_ppm_hr >= 0),
    CONSTRAINT scans_band_known  CHECK (band IN ('safe','elevated','warning','critical',
                                                 'invalid'))
);

CREATE INDEX IF NOT EXISTS scans_geom_gix ON scans USING GIST (geom);
CREATE INDEX IF NOT EXISTS scans_time_ix  ON scans (scanned_at DESC);
CREATE INDEX IF NOT EXISTS scans_worker_ix ON scans (worker_id, scanned_at DESC);
CREATE INDEX IF NOT EXISTS scans_band_ix  ON scans (band) WHERE band IN ('warning','critical');
CREATE INDEX IF NOT EXISTS scans_unit_ix  ON scans (unit_code, scanned_at DESC);
-- The audit path: "show me every scan whose substrate baseline did not survive".
CREATE INDEX IF NOT EXISTS scans_result_gin ON scans USING GIN (result_json);

-- The row is immutable once written. An exposure record that can be edited in place is not
-- evidence; a correction is a new row with a reference to what it supersedes.
CREATE TABLE IF NOT EXISTS scan_corrections (
    id              BIGSERIAL PRIMARY KEY,
    scan_id         BIGINT NOT NULL REFERENCES scans(id),
    supersedes      BIGINT REFERENCES scans(id),
    corrected_by    TEXT NOT NULL,
    corrected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    rationale       TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Views the dashboard uses
-- ---------------------------------------------------------------------------

-- Per-worker rollup over the last 24 h. n_invalid sits next to the exposure numbers
-- deliberately: a worker whose badge keeps failing has no exposure record at all, and that
-- must be as visible as a high reading.
CREATE OR REPLACE VIEW v_worker_24h AS
SELECT w.worker_id,
       w.name,
       count(*)                                         AS n_scans,
       count(*) FILTER (WHERE NOT s.ok)                 AS n_invalid,
       max(s.twa_ppm)  FILTER (WHERE s.ok)              AS peak_twa_ppm,
       avg(s.twa_ppm)  FILTER (WHERE s.ok)              AS mean_twa_ppm,
       sum(s.dose_ppm_hr) FILTER (WHERE s.ok)           AS cumulative_ppm_hr,
       count(*) FILTER (WHERE s.ok AND s.twa_ppm >= 1.0) AS n_over_tlv,
       max(s.scanned_at)                                AS last_scan_at
FROM workers w
JOIN scans s ON s.worker_id = w.worker_id
WHERE s.scanned_at > now() - interval '24 hours'
GROUP BY w.worker_id, w.name;

-- Per-unit rollup, joined spatially rather than by the denormalised unit_code, so a scan
-- whose unit_code was never populated still lands in the right area.
CREATE OR REPLACE VIEW v_unit_24h AS
SELECT u.code,
       u.name,
       u.sour_service,
       count(s.id)                                       AS n_scans,
       count(DISTINCT s.worker_id)                       AS n_workers,
       count(s.id) FILTER (WHERE NOT s.ok)               AS n_invalid,
       max(s.twa_ppm) FILTER (WHERE s.ok)                AS peak_twa_ppm,
       count(s.id) FILTER (WHERE s.ok AND s.twa_ppm >= 1.0) AS n_over_tlv
FROM plant_units u
LEFT JOIN scans s
       ON s.scanned_at > now() - interval '24 hours'
      AND (
            (u.boundary IS NOT NULL AND ST_Covers(u.boundary, s.geom))
         OR (u.boundary IS NULL AND ST_DWithin(u.centroid, s.geom, 150))
          )
GROUP BY u.code, u.name, u.sour_service;

-- Spatial clusters of concerning scans. The application does this in hse.core for SQLite;
-- here it is one query, and ST_ClusterDBSCAN gives the same single-link grouping.
--
-- n_workers matters as much as n_scans: several high readings from one worker is a person
-- finding (their task, their PPE, or a faulty badge), whereas several workers in the same
-- place is an area finding, and only the second justifies dispatching a survey.
CREATE OR REPLACE VIEW v_clusters_24h AS
WITH hot AS (
    SELECT id, worker_id, twa_ppm, geom,
           ST_ClusterDBSCAN(geom::geometry, eps := 0.0011, minpoints := 2)
               OVER () AS cid
    FROM scans
    WHERE ok AND twa_ppm >= 0.5
      AND scanned_at > now() - interval '24 hours'
      AND geom IS NOT NULL
)
SELECT cid                                        AS cluster_id,
       count(*)                                   AS n_scans,
       count(DISTINCT worker_id)                   AS n_workers,
       max(twa_ppm)                               AS peak_twa_ppm,
       avg(twa_ppm)                               AS mean_twa_ppm,
       ST_Y(ST_Centroid(ST_Collect(geom::geometry))) AS lat,
       ST_X(ST_Centroid(ST_Collect(geom::geometry))) AS lng
FROM hot
WHERE cid IS NOT NULL
GROUP BY cid
ORDER BY peak_twa_ppm DESC;

-- ---------------------------------------------------------------------------
-- MRPL units, matching hse.core.MRPL
--
-- COORDINATES ARE APPROXIMATE AND FOR DEMONSTRATION. They place recognisable units in
-- roughly the right relative positions within the refinery footprint so distances and the
-- map are realistic. Replace from the site's GIS before operational use. The ordering of
-- h2s_propensity follows the process chemistry and is the part that carries real meaning.
-- ---------------------------------------------------------------------------

INSERT INTO plant_units (code, name, centroid, h2s_propensity, sour_service, note) VALUES
 ('SRU-1','Sulphur Recovery Unit 1', ST_MakePoint(74.8598,12.9760)::geography,0.95,TRUE,
  'Claus train. Acid gas feed is majority H2S.'),
 ('SRU-2','Sulphur Recovery Unit 2', ST_MakePoint(74.8611,12.9754)::geography,0.95,TRUE,NULL),
 ('ARU','Amine Regeneration Unit',   ST_MakePoint(74.8586,12.9771)::geography,0.90,TRUE,
  'Regenerator overhead is concentrated acid gas.'),
 ('SWS','Sour Water Stripper',       ST_MakePoint(74.8600,12.9779)::geography,0.88,TRUE,NULL),
 ('DCU','Delayed Coker Unit',        ST_MakePoint(74.8570,12.9744)::geography,0.75,TRUE,
  'Coke drum switching and decoking are the exposure events.'),
 ('HCU','Hydrocracker Unit',         ST_MakePoint(74.8546,12.9756)::geography,0.70,TRUE,NULL),
 ('DHDT','Diesel Hydrotreater',      ST_MakePoint(74.8534,12.9769)::geography,0.65,TRUE,NULL),
 ('CDU-1','Crude Distillation Unit 1',ST_MakePoint(74.8555,12.9795)::geography,0.45,TRUE,NULL),
 ('CDU-2','Crude Distillation Unit 2',ST_MakePoint(74.8572,12.9805)::geography,0.45,TRUE,NULL),
 ('TANK-N','Tank Farm North',        ST_MakePoint(74.8535,12.9820)::geography,0.35,TRUE,
  'Gauging hatches and confined-space entry.'),
 ('TANK-S','Tank Farm South',        ST_MakePoint(74.8524,12.9736)::geography,0.30,TRUE,NULL),
 ('ETP','Effluent Treatment Plant',  ST_MakePoint(74.8601,12.9725)::geography,0.55,TRUE,
  'Anaerobic pockets and sludge handling - a classic fatality setting.'),
 ('FLARE','Flare Area',              ST_MakePoint(74.8628,12.9740)::geography,0.40,TRUE,NULL),
 ('JETTY','Marine Terminal Lines',   ST_MakePoint(74.8480,12.9700)::geography,0.25,TRUE,NULL),
 ('PP','Polypropylene Unit',         ST_MakePoint(74.8620,12.9783)::geography,0.05,FALSE,
  'No sour service - present so the map shows a genuine low-risk area.'),
 ('UTIL','Utilities and Cooling Towers',ST_MakePoint(74.8600,12.9800)::geography,0.05,FALSE,NULL),
 ('ADMIN','Administration and Control Room',ST_MakePoint(74.8508,12.9812)::geography,0.02,FALSE,
  'Muster point and scanning kiosk.')
ON CONFLICT (code) DO NOTHING;
