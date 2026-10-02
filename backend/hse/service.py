"""Route logic, with no web framework in it.

Every endpoint's actual work lives here as a plain function: bytes and dicts in, a
``(status_code, payload)`` tuple out. :mod:`hse.api` (FastAPI) and :mod:`hse.serve_dev`
(stdlib ``http.server``) are both thin adapters over these functions.

That split is not architectural decoration. FastAPI is not installable in every environment
this has to run in - an air-gapped refinery laptop being the obvious one - and a demo that
cannot start because a wheel is missing is a demo that does not happen. Keeping the logic
framework-free means the stdlib server is not a toy reimplementation that drifts from the
real one: it calls the same functions, so behaviour is identical and only the HTTP plumbing
differs.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from .core import MRPL, band_for, haversine_m, heatmap_payload
from .store import MeasurementStore, utc_now_iso

__all__ = ["MeasurementService"]

_MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _num(v, default=None):
    if v is None or v == "":
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


class MeasurementService:
    """Holds the store, the scan configuration and the plant layout."""

    def __init__(self, db_path: str = "hse_measurements.db", image_dir: str = None,
                 keep_images: bool = True):
        self.store = MeasurementStore(db_path, image_dir=image_dir)
        self.image_dir = image_dir
        # Images are kept by default. A colorimetric exposure record whose source photograph
        # was discarded cannot be re-examined if the reading is later disputed, and disputes
        # are exactly what an occupational exposure record exists to settle. Sites with a
        # privacy rule against storing photographs can pass keep_images=False; the reading,
        # its diagnostics and the image hash are still stored, so tampering remains
        # detectable even when the image is not retained.
        self.keep_images = keep_images and bool(image_dir)

    # ------------------------------------------------------------------

    def mock_location(self, seed=None) -> tuple:
        """A plausible coordinate inside a process unit, weighted towards sour service."""
        rnd = random.Random(f"{seed}-{uuid.uuid4()}")
        units = [u for u in MRPL.units]
        weights = [max(u.h2s_propensity, 0.02) for u in units]
        u = rnd.choices(units, weights=weights, k=1)[0]
        r = u.radius_m * math.sqrt(rnd.random())
        th = rnd.uniform(0, 2 * math.pi)
        dlat = (r * math.sin(th)) / 111320.0
        dlng = (r * math.cos(th)) / (111320.0 * math.cos(math.radians(u.lat)))
        return round(u.lat + dlat, 6), round(u.lng + dlng, 6)

    # ------------------------------------------------------------------
    # GET endpoints
    # ------------------------------------------------------------------

    def measurements(self, q: dict = None) -> tuple:
        q = q or {}
        rows = self.store.list_measurements(
            since=q.get("since"), until=q.get("until"),
            worker_id=q.get("worker_id"), band=q.get("band"),
            include_invalid=str(q.get("include_invalid", "1")).lower()
            not in ("0", "false", "no"),
            limit=int(_num(q.get("limit"), 500)),
        )
        return 200, {"measurements": rows, "n": len(rows), "server_time": utc_now_iso()}

    def measurement_detail(self, measurement_id: int) -> tuple:
        row = self.store.get_measurement(measurement_id)
        if row is None:
            return 404, {"error": f"no scan with id {measurement_id}"}
        return 200, row

    def heatmap(self, q: dict = None) -> tuple:
        q = q or {}
        hours = _num(q.get("hours"), 24.0)
        since = q.get("since")
        if since is None and hours and hours > 0:
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(
                microsecond=0).isoformat().replace("+00:00", "Z")
        rows = self.store.list_measurements(since=since, limit=int(_num(q.get("limit"), 2000)))
        payload = heatmap_payload(
            rows,
            nx=int(_num(q.get("nx"), 48)), ny=int(_num(q.get("ny"), 48)),
            radius_m=_num(q.get("radius_m"), 350.0),
            power=_num(q.get("power"), 2.0),
        )
        payload["window"] = {"since": since, "hours": hours}
        payload["stats"] = self.store.stats(since=since)
        payload["workers"] = self.store.worker_rollup(since=since)
        payload["server_time"] = utc_now_iso()
        return 200, payload

    def plant(self) -> tuple:
        return 200, MRPL.as_dict()

    def stats(self, q: dict = None) -> tuple:
        q = q or {}
        return 200, {"stats": self.store.stats(since=q.get("since")),
                     "workers": self.store.worker_rollup(since=q.get("since")),
                     "server_time": utc_now_iso()}

    def health(self) -> tuple:
        return 200, {"ok": True, "service": "sih26118-h2s-dosimeter",
                     "plant": MRPL.name,
                     "server_time": utc_now_iso()}

    # ------------------------------------------------------------------
    # Demo data
    # ------------------------------------------------------------------

    def seed_demo(self, q: dict = None) -> tuple:
        """Populate the log with synthetic measurements so the dashboard has something to show.

        Every row it writes is marked ``DEMO`` in ``shift_id`` and ``synthetic: true`` in the
        stored result JSON, and the worker IDs are prefixed ``DEMO-``. That labelling is
        deliberate and load-bearing: demonstration data and measured data must never be
        indistinguishable inside an exposure database, or the database stops being evidence.

        The doses are drawn from the unit's H2S propensity, so the map shows a pattern that
        matches the process - the SRU and amine areas run high, polypropylene and admin run
        clean - which is what makes the visualisation legible in a review. It is generated,
        not measured, and the dashboard labels the whole window as demo data when any is
        present.
        """
        q = q or {}
        n = int(_num(q.get("n"), 60))
        n = max(1, min(n, 500))
        hours = _num(q.get("hours"), 12.0)
        rnd = random.Random(int(_num(q.get("seed"), 7)))
        now = datetime.now(timezone.utc)
        units = list(MRPL.units)
        weights = [max(u.h2s_propensity, 0.03) for u in units]
        written = []
        for i in range(n):
            u = rnd.choices(units, weights=weights, k=1)[0]
            r = u.radius_m * math.sqrt(rnd.random())
            th = rnd.uniform(0, 2 * math.pi)
            lat = u.lat + (r * math.sin(th)) / 111320.0
            lng = u.lng + (r * math.cos(th)) / (111320.0 * math.cos(math.radians(u.lat)))
            shift_hours = 8.0
            # Lognormal about a mean set by the unit's propensity: occupational exposure
            # distributions are right-skewed, so a normal draw would understate the tail that
            # actually matters.
            mu = 0.10 + 2.6 * (u.h2s_propensity ** 2.2)
            twa = max(0.0, rnd.lognormvariate(math.log(max(mu, 0.02)), 0.75))
            dose = twa * shift_hours
            ok = rnd.random() > 0.06
            band = band_for(twa, ok=ok)
            when = (now - timedelta(hours=rnd.uniform(0, hours))).replace(
                microsecond=0).isoformat().replace("+00:00", "Z")
            wid = f"DEMO-{100 + rnd.randrange(38)}"
            result = {
                "ok": ok,
                "verdict": band["label"].upper() if ok else "INVALID",
                "dose_ppm_hr": round(dose, 3) if ok else None,
                "twa_ppm": round(twa, 4) if ok else None,
            }
            row = self.store.insert_measurement(
                result=result, worker_id=wid, band=band["key"], measured_at=when,
                lat=round(lat, 6), lng=round(lng, 6),
                accuracy_m=round(rnd.uniform(4, 28), 1), unit_code=u.code,
                # Generated coordinates, so they are flagged as such and the dashboard draws
                # them hollow alongside the DEMO labelling.
                location_mocked=True)
            written.append(row["id"])
        return 200, {"inserted": len(written), "ids": written[:20],
                     "note": "Synthetic demonstration data. Delete with /api/demo/clear."}

    def clear_demo(self) -> tuple:
        cur = self.store._conn.execute("DELETE FROM measurements WHERE worker_id LIKE 'DEMO-%'")
        self.store._conn.commit()
        return 200, {"deleted": cur.rowcount}
