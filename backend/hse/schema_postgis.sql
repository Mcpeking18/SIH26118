-- PostGIS schema for production deployments.
-- SQLite is fine for a laptop pilot, but a refinery-wide deployment needs spatial queries
-- and concurrent writes. This schema exactly matches store.py's SQLite layout but uses
-- native PostGIS types where appropriate.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS measurements (
    id              SERIAL PRIMARY KEY,
    measured_at     TIMESTAMPTZ NOT NULL,
    received_at     TIMESTAMPTZ NOT NULL,
    worker_id       TEXT    NOT NULL,
    worker_name     TEXT,
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    accuracy_m      DOUBLE PRECISION,
    location_mocked BOOLEAN NOT NULL DEFAULT false,
    unit_code       TEXT,
    ok              BOOLEAN NOT NULL,
    verdict         TEXT    NOT NULL,
    band            TEXT    NOT NULL,
    dose_ppm_hr     DOUBLE PRECISION,
    twa_ppm         DOUBLE PRECISION,
    temperature_c   DOUBLE PRECISION,
    humidity_rh     DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS measurements_time   ON measurements(measured_at);
CREATE INDEX IF NOT EXISTS measurements_worker ON measurements(worker_id, measured_at);
CREATE INDEX IF NOT EXISTS measurements_space  ON measurements(lat, lng);
CREATE INDEX IF NOT EXISTS measurements_band   ON measurements(band, measured_at);

CREATE TABLE IF NOT EXISTS workers (
    worker_id   TEXT PRIMARY KEY,
    name        TEXT,
    role        TEXT,
    unit_code   TEXT,
    contact     TEXT
);
