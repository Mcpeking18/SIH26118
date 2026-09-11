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

import numpy as np

from engine.pipeline import ScanConfig, scan_image
from .core import MRPL, band_for, haversine_m, heatmap_payload
from .store import ScanStore, utc_now_iso

__all__ = ["ScanService"]

_MAX_UPLOAD_BYTES = 12 * 1024 * 1024


def _num(v, default=None):
    if v is None or v == "":
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


class ScanService:
    """Holds the store, the scan configuration and the plant layout."""

    def __init__(self, db_path: str = "hse_scans.db", image_dir: str = None,
                 config: ScanConfig = None, keep_images: bool = True):
        self.store = ScanStore(db_path, image_dir=image_dir)
        self.config = config or ScanConfig()
        self.image_dir = image_dir
        # Images are kept by default. A colorimetric exposure record whose source photograph
        # was discarded cannot be re-examined if the reading is later disputed, and disputes
        # are exactly what an occupational exposure record exists to settle. Sites with a
        # privacy rule against storing photographs can pass keep_images=False; the reading,
        # its diagnostics and the image hash are still stored, so tampering remains
        # detectable even when the image is not retained.
        self.keep_images = keep_images and bool(image_dir)

    # ------------------------------------------------------------------
    # POST /scan
    # ------------------------------------------------------------------

    def scan(self, image_bytes: bytes, fields: dict = None) -> tuple:
        """Run one badge image through the engine, log it, and return the reading.

        ``fields`` carries the multipart form values: ``worker_id``, ``lat``, ``lng``,
        ``accuracy_m``, ``shift_hours``, ``badge_serial``, ``shift_id``, ``device``,
        ``app_version``, ``client_scan_id``, ``scanned_at``.

        A failed *reading* is still a successful *request*: HTTP 200 with ``ok: false``, the
        engine's reason and an operator hint. The scanner needs the hint in order to tell the
        worker what to change, and an error status would push it into a generic network-error
        path instead. HTTP 4xx is reserved for a malformed request - no image, wrong field,
        undecodable file.
        """
        fields = fields or {}
        if not image_bytes:
            return 400, {"error": "no image uploaded; expected a multipart field named "
                                  "'image'"}
        if len(image_bytes) > _MAX_UPLOAD_BYTES:
            return 413, {"error": f"image too large ({len(image_bytes)} bytes); limit is "
                                  f"{_MAX_UPLOAD_BYTES}"}

        import cv2
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if bgr is None:
            return 400, {"error": "could not decode the uploaded file as an image"}

        cfg = self.config
        sh = _num(fields.get("shift_hours"))
        if sh and sh > 0:
            cfg = ScanConfig(**{**cfg.__dict__, "shift_hours": sh})

        result = scan_image(bgr, cfg).as_dict()

        assess = result.get("exposure") or {}
        band = band_for(assess.get("twa_ppm"), ok=bool(result.get("ok")))

        lat = _num(fields.get("lat"))
        lng = _num(fields.get("lng"))
        mocked = False
        if lat is None or lng is None:
            # Mock GPS. A laptop webcam has no location and a phone indoors often refuses
            # one, and without coordinates the map has nothing to draw - so a scan with no
            # fix is placed at a plausible point inside a process unit, weighted towards
            # sour service. It is flagged ``location_mocked`` in the response and in the
            # stored record, and the dashboard draws those pins hollow: a demonstration
            # coordinate must never be indistinguishable from a surveyed one.
            lat, lng = self.mock_location(fields.get("worker_id"))
            mocked = True

        unit, dist = MRPL.nearest_unit(lat, lng)
        unit_code = unit.code if (unit is not None and dist <= unit.radius_m * 1.5) else None

        sha = hashlib.sha256(image_bytes).hexdigest()
        path = None
        if self.keep_images:
            path = os.path.join(self.image_dir, f"{sha[:16]}.jpg")
            if not os.path.exists(path):
                with open(path, "wb") as fh:
                    fh.write(image_bytes)

        row = self.store.insert_scan(
            result=result,
            worker_id=fields.get("worker_id") or "UNKNOWN",
            worker_name=fields.get("worker_name"),
            shift_id=fields.get("shift_id"),
            badge_serial=fields.get("badge_serial"),
            band=band["key"],
            scanned_at=fields.get("scanned_at") or utc_now_iso(),
            lat=lat, lng=lng, accuracy_m=_num(fields.get("accuracy_m")),
            unit_code=unit_code, location_mocked=mocked,
            device=fields.get("device"), app_version=fields.get("app_version"),
            client_scan_id=fields.get("client_scan_id") or str(uuid.uuid4()),
            image_sha256=sha, image_path=path,
        )

        payload = {
            # The flat fields the scanner UI binds to directly.
            "ok": bool(result.get("ok")),
            "status": assess.get("verdict") or ("INVALID" if not result.get("ok")
                                                else "UNKNOWN"),
            "band": band["key"],
            "band_label": band["label"],
            "colour": band["colour"],
            "action": band["action"],
            "dose_ppm_hr": assess.get("dose_ppm_hr"),
            "twa_ppm": assess.get("twa_ppm"),
            "shift_hours": assess.get("shift_hours"),
            "delta_e": (result.get("colour") or {}).get("delta_e00"),
            "delta_e00": (result.get("colour") or {}).get("delta_e00"),
            "delta_l_star": (result.get("colour") or {}).get("delta_l_star"),
            "reason": result.get("reason") or "",
            "operator_hint": result.get("operator_hint") or "",
            "warnings": result.get("warnings") or [],
            # Provenance and the full audit record.
            "scan_id": row["id"],
            "duplicate": row["duplicate"],
            "worker_id": fields.get("worker_id") or "UNKNOWN",
            "lat": lat, "lng": lng,
            "location_mocked": mocked,
            "unit": unit_code,
            "unit_name": None if unit_code is None else unit.name,
            "scanned_at": fields.get("scanned_at") or utc_now_iso(),
            "image_sha256": sha,
            "detail": result,
        }
        return 200, payload

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

    def scans(self, q: dict = None) -> tuple:
        q = q or {}
        rows = self.store.list_scans(
            since=q.get("since"), until=q.get("until"),
            worker_id=q.get("worker_id"), band=q.get("band"),
            include_invalid=str(q.get("include_invalid", "1")).lower()
            not in ("0", "false", "no"),
            limit=int(_num(q.get("limit"), 500)),
        )
        return 200, {"scans": rows, "n": len(rows), "server_time": utc_now_iso()}

    def scan_detail(self, scan_id: int) -> tuple:
        row = self.store.get_scan(scan_id)
        if row is None:
            return 404, {"error": f"no scan with id {scan_id}"}
        return 200, row

    def heatmap(self, q: dict = None) -> tuple:
        q = q or {}
        hours = _num(q.get("hours"), 24.0)
        since = q.get("since")
        if since is None and hours and hours > 0:
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(
                microsecond=0).isoformat().replace("+00:00", "Z")
        rows = self.store.list_scans(since=since, limit=int(_num(q.get("limit"), 2000)))
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
                     "engine": "engine.pipeline", "plant": MRPL.name,
                     "observable": self.config.calibration.observable,
                     "shift_hours": self.config.shift_hours,
                     "server_time": utc_now_iso()}

    # ------------------------------------------------------------------
    # Demo data
    # ------------------------------------------------------------------

    def seed_demo(self, q: dict = None) -> tuple:
        """Populate the log with synthetic scans so the dashboard has something to show.

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
                "ok": ok, "synthetic": True,
                "stage_failed": "" if ok else "normalize",
                "reason": "" if ok else ("synthetic unreadable scan - demo data, stands in "
                                         "for a badge that failed its integrity checks"),
                "operator_hint": "" if ok else "Switch the torch on and retake.",
                "warnings": [] if ok else ["synthetic"],
                "exposure": ({"verdict": band["label"].upper() if ok else "INVALID",
                                "dose_ppm_hr": round(dose, 3) if ok else None,
                                "twa_ppm": round(twa, 4) if ok else None,
                                "shift_hours": shift_hours}),
                "colour": {"delta_l_star": round(2.5 + 3.2 * twa, 3) if ok else None,
                           "delta_e00": round(1.7 + 2.1 * twa, 3) if ok else None,
                           "ccm_mode": "root6",
                           "baseline_source": "onbadge:SUBSTRATE_A+SUBSTRATE_B"},
                "geometry": {"reproj_rmse_mm": round(rnd.uniform(0.01, 0.12), 4)},
            }
            row = self.store.insert_scan(
                result=result, worker_id=wid, band=band["key"], scanned_at=when,
                shift_id="DEMO", badge_serial=f"DEMO-B{rnd.randrange(9000):04d}",
                lat=round(lat, 6), lng=round(lng, 6),
                accuracy_m=round(rnd.uniform(4, 28), 1), unit_code=u.code,
                # Generated coordinates, so they are flagged as such and the dashboard draws
                # them hollow alongside the DEMO labelling.
                location_mocked=True,
                device="seed_demo", app_version="demo",
                client_scan_id=f"demo-{uuid.uuid4()}")
            written.append(row["id"])
        return 200, {"inserted": len(written), "ids": written[:20],
                     "note": "Synthetic demonstration data, labelled shift_id=DEMO and "
                             "worker_id DEMO-*. Delete with /api/demo/clear."}

    def clear_demo(self) -> tuple:
        cur = self.store._conn.execute("DELETE FROM scans WHERE shift_id = 'DEMO'")
        self.store._conn.commit()
        return 200, {"deleted": cur.rowcount}
