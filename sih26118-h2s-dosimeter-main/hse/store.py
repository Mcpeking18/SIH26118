"""SQLite scan log. The exposure record, and it has to survive being audited.

Two design decisions worth stating, because both cost a little and buy something specific.

**The full engine result is stored verbatim.** Every row keeps the complete
``ScanResult.as_dict()`` JSON alongside the extracted columns. An occupational exposure
figure that cannot be re-derived is not defensible: two years from now someone may need to
know which CCM mode produced a reading, what the reprojection error was, whether the
substrate baseline survived, and what the operator was warned about. Columns are for
querying, the JSON is for answering.

**Failed scans are stored too.** A scan that could not be read is not a non-event - it means
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

__all__ = ["ScanStore", "utc_now_iso"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scanned_at      TEXT    NOT NULL,          -- ISO-8601 UTC, when the badge was read
    received_at     TEXT    NOT NULL,          -- when the server stored it; differs for
                                               -- queued offline scans, and the gap matters
    worker_id       TEXT    NOT NULL,
    worker_name     TEXT,
    shift_id        TEXT,
    badge_serial    TEXT,
    lat             REAL,
    lng             REAL,
    accuracy_m      REAL,                      -- GPS reported accuracy; a 500 m fix is not
                                               -- a location and the map must be able to say so
    location_mocked INTEGER NOT NULL DEFAULT 0, -- 1 = coordinate was generated, not observed.
                                               -- Stored rather than inferred: a demonstration
                                               -- coordinate must never be indistinguishable
                                               -- from a surveyed one, and "accuracy_m is null"
                                               -- is a guess, not provenance
    unit_code       TEXT,                      -- nearest mapped process unit, if inside one
    ok              INTEGER NOT NULL,          -- did the engine produce a defensible reading
    verdict         TEXT    NOT NULL,          -- SAFE / WARNING / CRITICAL / SUSPECT / ...
    band            TEXT    NOT NULL,          -- map banding, see hse.core.RISK_BANDS
    dose_ppm_hr     REAL,
    twa_ppm         REAL,
    shift_hours     REAL,
    delta_l_star    REAL,                      -- primary darkening observable
    delta_e00       REAL,                      -- secondary, recorded
    chroma_residual REAL,
    channel_balance REAL,
    baseline_source TEXT,
    ccm_mode        TEXT,
    reproj_rmse_mm  REAL,
    stage_failed    TEXT,
    reason          TEXT,
    operator_hint   TEXT,
    warnings        TEXT,                      -- JSON array
    device          TEXT,
    app_version     TEXT,
    client_scan_id  TEXT,                      -- idempotency key from the offline queue
    image_sha256    TEXT,
    image_path      TEXT,
    result_json     TEXT    NOT NULL           -- complete ScanResult.as_dict()
);
CREATE UNIQUE INDEX IF NOT EXISTS scans_client_id ON scans(client_scan_id)
    WHERE client_scan_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS scans_time   ON scans(scanned_at);
CREATE INDEX IF NOT EXISTS scans_worker ON scans(worker_id, scanned_at);
CREATE INDEX IF NOT EXISTS scans_space  ON scans(lat, lng);
CREATE INDEX IF NOT EXISTS scans_band   ON scans(band, scanned_at);

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


class ScanStore:
    """Thin, explicit data access layer. No ORM, so the SQL is auditable as written."""

    def __init__(self, path: str = "hse_scans.db", image_dir: str = None):
        self.path = path
        self.image_dir = image_dir
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        if image_dir:
            os.makedirs(image_dir, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL so the dashboard can read while the scanner endpoint writes. A refinery gate at
        # shift change is a burst of concurrent writes and long-polling reads, which is
        # precisely the case rollback-journal mode handles badly.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        """Add columns that post-date an existing database file.

        A pilot's SQLite file is an exposure record; recreating it to pick up a schema change
        would destroy monitoring history, so new columns are added in place. Kept explicit and
        tiny rather than pulling in a migration framework.
        """
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(scans)")}
        for col, decl in (("location_mocked", "INTEGER NOT NULL DEFAULT 0"),):
            if col not in have:
                self._conn.execute(f"ALTER TABLE scans ADD COLUMN {col} {decl}")

    def close(self):
        self._conn.close()

    # ---- writes ---------------------------------------------------------

    def insert_scan(self, *, result: dict, worker_id: str, band: str,
                    scanned_at: str = None, worker_name: str = None,
                    shift_id: str = None, badge_serial: str = None,
                    lat=None, lng=None, accuracy_m=None, unit_code: str = None,
                    location_mocked: bool = False,
                    device: str = None, app_version: str = None,
                    client_scan_id: str = None, image_sha256: str = None,
                    image_path: str = None) -> dict:
        """Insert one scan. Idempotent on ``client_scan_id``.

        Idempotency is not a nicety here. The scanner queues scans offline and flushes them
        when it regains signal; a flush that half-succeeds and retries would otherwise log
        the same badge reading twice, and a duplicated exposure record is a false compliance
        signal in both directions - it double-counts a violation and inflates the monitoring
        coverage. The client generates a UUID per capture and the unique index enforces it.
        """
        colour = (result.get("colour") or {})
        geom = (result.get("geometry") or {})
        # ``exposure`` is the engine's key for the dosimetry block; see engine.pipeline.
        assess = (result.get("exposure") or {})
        row = dict(
            scanned_at=scanned_at or utc_now_iso(),
            received_at=utc_now_iso(),
            worker_id=str(worker_id),
            worker_name=worker_name,
            shift_id=shift_id,
            badge_serial=badge_serial,
            lat=_f(lat), lng=_f(lng), accuracy_m=_f(accuracy_m),
            location_mocked=1 if location_mocked else 0,
            unit_code=unit_code,
            ok=1 if result.get("ok") else 0,
            verdict=str(assess.get("verdict") or ("INVALID" if not result.get("ok")
                                                  else "UNKNOWN")),
            band=band,
            dose_ppm_hr=_f(assess.get("dose_ppm_hr")),
            twa_ppm=_f(assess.get("twa_ppm")),
            shift_hours=_f(assess.get("shift_hours")),
            delta_l_star=_f(colour.get("delta_l_star")),
            delta_e00=_f(colour.get("delta_e00")),
            chroma_residual=_f(colour.get("chroma_residual")),
            channel_balance=_f(colour.get("channel_balance")),
            baseline_source=colour.get("baseline_source"),
            ccm_mode=colour.get("ccm_mode"),
            reproj_rmse_mm=_f(geom.get("reproj_rmse_mm")),
            stage_failed=result.get("stage_failed") or None,
            reason=result.get("reason") or None,
            operator_hint=result.get("operator_hint") or None,
            warnings=json.dumps(result.get("warnings") or []),
            device=device, app_version=app_version,
            client_scan_id=client_scan_id,
            image_sha256=image_sha256, image_path=image_path,
            result_json=json.dumps(result, allow_nan=False),
        )
        cols = ", ".join(row)
        marks = ", ".join(f":{k}" for k in row)
        try:
            cur = self._conn.execute(
                f"INSERT INTO scans ({cols}) VALUES ({marks})", row)
            self._conn.commit()
            return {"id": int(cur.lastrowid), "duplicate": False}
        except sqlite3.IntegrityError:
            # Already have this client_scan_id: return the original row's id so the client
            # can clear its queue entry rather than retrying forever.
            cur = self._conn.execute(
                "SELECT id FROM scans WHERE client_scan_id = ?", (client_scan_id,))
            got = cur.fetchone()
            return {"id": int(got["id"]) if got else None, "duplicate": True}

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

    def list_scans(self, *, since: str = None, until: str = None, worker_id: str = None,
                   band: str = None, bbox: dict = None, include_invalid: bool = True,
                   limit: int = 2000) -> list:
        sql = ["SELECT * FROM scans WHERE 1=1"]
        args = []
        if since:
            sql.append("AND scanned_at >= ?"); args.append(since)
        if until:
            sql.append("AND scanned_at <= ?"); args.append(until)
        if worker_id:
            sql.append("AND worker_id = ?"); args.append(str(worker_id))
        if band:
            sql.append("AND band = ?"); args.append(band)
        if not include_invalid:
            sql.append("AND ok = 1")
        if bbox:
            sql.append("AND lat BETWEEN ? AND ? AND lng BETWEEN ? AND ?")
            args += [bbox["min_lat"], bbox["max_lat"], bbox["min_lng"], bbox["max_lng"]]
        sql.append("ORDER BY scanned_at DESC, id DESC LIMIT ?")
        args.append(int(limit))
        rows = self._conn.execute(" ".join(sql), args).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_scan(self, scan_id: int) -> dict:
        r = self._conn.execute("SELECT * FROM scans WHERE id = ?", (int(scan_id),)).fetchone()
        return None if r is None else self._row_to_dict(r, with_result=True)

    def worker_rollup(self, *, since: str = None, limit: int = 500) -> list:
        """Per-worker exposure summary over the window, worst first.

        ``n_invalid`` is carried deliberately alongside the exposure numbers: a worker whose
        badge keeps failing to read has no exposure record, and that must be visible next to
        the workers who do rather than buried.
        """
        sql = ["SELECT worker_id, MAX(worker_name) AS worker_name,",
               "COUNT(*) AS n_scans,",
               "SUM(CASE WHEN ok=1 THEN 0 ELSE 1 END) AS n_invalid,",
               "MAX(CASE WHEN ok=1 THEN twa_ppm END) AS peak_twa_ppm,",
               "AVG(CASE WHEN ok=1 THEN twa_ppm END) AS mean_twa_ppm,",
               "SUM(CASE WHEN ok=1 AND twa_ppm >= 1.0 THEN 1 ELSE 0 END) AS n_over_tlv,",
               "SUM(CASE WHEN ok=1 THEN dose_ppm_hr ELSE 0 END) AS cumulative_ppm_hr,",
               "MAX(scanned_at) AS last_scan_at",
               "FROM scans WHERE 1=1"]
        args = []
        if since:
            sql.append("AND scanned_at >= ?"); args.append(since)
        sql.append("GROUP BY worker_id ORDER BY peak_twa_ppm DESC NULLS LAST, n_scans DESC")
        sql.append("LIMIT ?"); args.append(int(limit))
        out = []
        for r in self._conn.execute(" ".join(sql), args).fetchall():
            d = dict(r)
            for k in ("peak_twa_ppm", "mean_twa_ppm", "cumulative_ppm_hr"):
                d[k] = None if d[k] is None else round(float(d[k]), 3)
            out.append(d)
        return out

    def stats(self, *, since: str = None) -> dict:
        where, args = ("WHERE scanned_at >= ?", [since]) if since else ("", [])
        r = self._conn.execute(
            f"SELECT COUNT(*) n, SUM(ok) n_ok, "
            f"SUM(CASE WHEN band='critical' THEN 1 ELSE 0 END) n_critical, "
            f"SUM(CASE WHEN band='warning'  THEN 1 ELSE 0 END) n_warning, "
            f"SUM(CASE WHEN band='elevated' THEN 1 ELSE 0 END) n_elevated, "
            f"SUM(CASE WHEN band='safe'     THEN 1 ELSE 0 END) n_safe, "
            f"COUNT(DISTINCT worker_id) n_workers, "
            f"MAX(CASE WHEN ok=1 THEN twa_ppm END) peak_twa, "
            f"MAX(scanned_at) last_scan_at FROM scans {where}", args).fetchone()
        d = {k: r[k] for k in r.keys()}
        d["n"] = int(d["n"] or 0)
        for k in ("n_ok", "n_critical", "n_warning", "n_elevated", "n_safe", "n_workers"):
            d[k] = int(d[k] or 0)
        d["n_invalid"] = d["n"] - d["n_ok"]
        d["peak_twa"] = None if d["peak_twa"] is None else round(float(d["peak_twa"]), 3)
        # Monitoring coverage, not compliance: the fraction of attempted scans that produced
        # a usable record. Reported because a programme with 100% "safe" results and 30%
        # unreadable badges is not a safe programme.
        d["read_rate"] = round(d["n_ok"] / d["n"], 4) if d["n"] else None
        return d

    def _row_to_dict(self, r: sqlite3.Row, with_result: bool = False) -> dict:
        d = {k: r[k] for k in r.keys()}
        d["ok"] = bool(d["ok"])
        d["location_mocked"] = bool(d.get("location_mocked"))
        try:
            d["warnings"] = json.loads(d.get("warnings") or "[]")
        except (TypeError, ValueError):
            d["warnings"] = []
        raw = d.pop("result_json", None)
        if with_result:
            try:
                d["result"] = json.loads(raw) if raw else None
            except (TypeError, ValueError):
                d["result"] = None
        d["unit"] = d.get("unit_code")
        return d
