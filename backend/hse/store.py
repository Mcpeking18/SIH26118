"""SQLite scan log. The exposure record, and it has to survive being audited.

Two design decisions worth stating, because both cost a little and buy something specific.

**The full engine result is stored verbatim.** Every row keeps the complete
``ScanResult.as_dict()`` JSON alongside the extracted columns. An occupational exposure
figure that cannot be re-derived is not defensible: two years from now someone may need to
know which CCM mode produced a reading, what the reprojection error was, whether the
substrate baseline survived, and what the operator was warned about. Columns are for
querying, the JSON is for answering.

**Failed measurements are stored too.** A scan that could not be read is not a non-event - it means
a worker's shift went unmonitored, which is itself a finding, and a badge or a lamp or an
area that produces repeated failures is a pattern worth seeing. Discarding them would make
the compliance statistics look better than the monitoring actually was, which is the exact
failure mode a dosimetry programme exists to prevent.

The schema mirrors ``schema_postgis.sql`` so a pilot can start on SQLite on a laptop and
migrate to PostGIS without the application layer changing shape.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from datetime import datetime, timezone

__all__ = ["MeasurementStore", "utc_now_iso"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS measurements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    measured_at      TEXT    NOT NULL,
    received_at     TEXT    NOT NULL,
    worker_id       TEXT    NOT NULL,
    worker_name     TEXT,
    lat             REAL,
    lng             REAL,
    accuracy_m      REAL,
    location_mocked INTEGER NOT NULL DEFAULT 0,
    unit_code       TEXT,
    ok              INTEGER NOT NULL,
    verdict         TEXT    NOT NULL,
    band            TEXT    NOT NULL,
    dose_ppm_hr     REAL,
    twa_ppm         REAL,
    temperature_c   REAL,
    humidity_rh     REAL
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
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _f(v):
    """Float or None - and None for NaN, because NaN is not valid JSON."""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class MeasurementStore:
    """Thin, explicit data access layer. No ORM, so the SQL is auditable as written."""

    def __init__(self, path: str = "hse_measurements.db", image_dir: str = None):
        self.path = path
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        """Add columns that post-date an existing database file."""
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(measurements)")}
        for col, decl in (("location_mocked", "INTEGER NOT NULL DEFAULT 0"),
                          ("temperature_c", "REAL"),
                          ("humidity_rh", "REAL")):
            if col not in have:
                self._conn.execute(f"ALTER TABLE measurements ADD COLUMN {col} {decl}")

    def close(self):
        self._conn.close()

    # ---- writes ---------------------------------------------------------

    def insert_measurement(self, *, result: dict, worker_id: str, band: str,
                    measured_at: str = None, worker_name: str = None,
                    lat=None, lng=None, accuracy_m=None, unit_code: str = None,
                    location_mocked: bool = False,
                    temperature_c=None, humidity_rh=None) -> dict:
        row = dict(
            measured_at=measured_at or utc_now_iso(),
            received_at=utc_now_iso(),
            worker_id=str(worker_id),
            worker_name=worker_name,
            lat=_f(lat), lng=_f(lng), accuracy_m=_f(accuracy_m),
            location_mocked=1 if location_mocked else 0,
            unit_code=unit_code,
            ok=1 if result.get("ok") else 0,
            verdict=str(result.get("verdict") or "UNKNOWN"),
            band=band,
            dose_ppm_hr=_f(result.get("dose_ppm_hr")),
            twa_ppm=_f(result.get("twa_ppm")),
            temperature_c=_f(temperature_c), humidity_rh=_f(humidity_rh),
        )
        cols = ", ".join(row)
        marks = ", ".join(f":{k}" for k in row)
        cur = self._conn.execute(
            f"INSERT INTO measurements ({cols}) VALUES ({marks})", row)
        self._conn.commit()
        return {"id": int(cur.lastrowid), "duplicate": False}

    def upsert_worker(self, worker_id: str, name: str = None, role: str = None,
                      unit_code: str = None, contact: str = None):
        self._conn.execute(
            "INSERT INTO workers (worker_id, name, role, unit_code, contact) "
            "VALUES (?,?,?,?,?) ON CONFLICT(worker_id) DO UPDATE SET "
            "name=COALESCE(excluded.name, name), role=COALESCE(excluded.role, role), "
            "unit_code=COALESCE(excluded.unit_code, unit_code), "
            "contact=COALESCE(excluded.contact, contact)",
            (str(worker_id), name, role, unit_code, contact))
        self._conn.commit()

    # ---- reads ----------------------------------------------------------

    def list_measurements(self, *, since: str = None, until: str = None, worker_id: str = None,
                   band: str = None, bbox: dict = None, include_invalid: bool = True,
                   limit: int = 2000) -> list:
        sql = ["SELECT * FROM measurements WHERE 1=1"]
        args = []
        if since:
            sql.append("AND measured_at >= ?"); args.append(since)
        if until:
            sql.append("AND measured_at <= ?"); args.append(until)
        if worker_id:
            sql.append("AND worker_id = ?"); args.append(str(worker_id))
        if band:
            sql.append("AND band = ?"); args.append(band)
        if not include_invalid:
            sql.append("AND ok = 1")
        if bbox:
            sql.append("AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?")
            args += [bbox["min_lat"], bbox["max_lat"], bbox["min_lng"], bbox["max_lng"]]
        sql.append("ORDER BY measured_at DESC, id DESC LIMIT ?")
        args.append(int(limit))
        rows = self._conn.execute(" ".join(sql), args).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_measurement(self, measurement_id: int) -> dict:
        r = self._conn.execute("SELECT * FROM measurements WHERE id = ?", (int(measurement_id),)).fetchone()
        return None if r is None else self._row_to_dict(r, with_result=True)

    def worker_rollup(self, *, since: str = None, limit: int = 500) -> list:
        """Per-worker exposure summary over the window, worst first.

        ``n_invalid`` is carried deliberately alongside the exposure numbers: a worker whose
        badge keeps failing to read has no exposure record, and that must be visible next to
        the workers who do rather than buried.
        """
        sql = ["SELECT worker_id, MAX(worker_name) AS worker_name,",
               "COUNT(*) AS n_measurements,",
               "SUM(CASE WHEN ok=1 THEN 0 ELSE 1 END) AS n_invalid,",
               "MAX(CASE WHEN ok=1 THEN twa_ppm END) AS peak_twa_ppm,",
               "AVG(CASE WHEN ok=1 THEN twa_ppm END) AS mean_twa_ppm,",
               "SUM(CASE WHEN ok=1 AND twa_ppm >= 1.0 THEN 1 ELSE 0 END) AS n_over_tlv,",
               "SUM(CASE WHEN ok=1 THEN dose_ppm_hr ELSE 0 END) AS cumulative_ppm_hr,",
               "MAX(measured_at) AS last_measurement_at",
               "FROM measurements WHERE 1=1"]
        args = []
        if since:
            sql.append("AND measured_at >= ?"); args.append(since)
        sql.append("GROUP BY worker_id ORDER BY peak_twa_ppm DESC NULLS LAST, n_measurements DESC")
        sql.append("LIMIT ?"); args.append(int(limit))
        out = []
        for r in self._conn.execute(" ".join(sql), args).fetchall():
            d = dict(r)
            for k in ("peak_twa_ppm", "mean_twa_ppm", "cumulative_ppm_hr"):
                d[k] = None if d[k] is None else round(float(d[k]), 3)
            out.append(d)
        return out

    def stats(self, *, since: str = None) -> dict:
        where, args = ("WHERE measured_at >= ?", [since]) if since else ("", [])
        r = self._conn.execute(
            f"SELECT COUNT(*) n, SUM(ok) n_ok, "
            f"SUM(CASE WHEN band='critical' THEN 1 ELSE 0 END) n_critical, "
            f"SUM(CASE WHEN band='warning'  THEN 1 ELSE 0 END) n_warning, "
            f"SUM(CASE WHEN band='elevated' THEN 1 ELSE 0 END) n_elevated, "
            f"SUM(CASE WHEN band='safe'     THEN 1 ELSE 0 END) n_safe, "
            f"COUNT(DISTINCT worker_id) n_workers, "
            f"MAX(CASE WHEN ok=1 THEN twa_ppm END) peak_twa, "
            f"MAX(measured_at) last_measurement_at FROM measurements {where}", args).fetchone()
        d = {k: r[k] for k in r.keys()}
        d["n"] = int(d["n"] or 0)
        for k in ("n_ok", "n_critical", "n_warning", "n_elevated", "n_safe", "n_workers"):
            d[k] = int(d[k] or 0)
        d["n_invalid"] = d["n"] - d["n_ok"]
        d["peak_twa"] = None if d["peak_twa"] is None else round(float(d["peak_twa"]), 3)
        # Monitoring coverage, not compliance: the fraction of attempted measurements that produced
        # a usable record. Reported because a programme with 100% "safe" results and 30%
        # unreadable badges is not a safe programme.
        d["read_rate"] = round(d["n_ok"] / d["n"], 4) if d["n"] else None
        return d

    def _row_to_dict(self, r: sqlite3.Row, with_result: bool = False) -> dict:
        d = {k: r[k] for k in r.keys()}
        d["ok"] = bool(d["ok"])
        d["location_mocked"] = bool(d.get("location_mocked"))
        d["unit"] = d.get("unit_code")
        return d
