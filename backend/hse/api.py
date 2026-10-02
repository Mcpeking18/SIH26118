"""FastAPI application. ``uvicorn hse.api:app --host 0.0.0.0 --port 8000``

All the work happens in :class:`hse.service.ScanService`; this module is the HTTP surface and
nothing else. If FastAPI is not installed, :mod:`hse.serve_dev` serves the identical routes on
the standard library alone - see the README.

Serve over HTTPS in the field. Browsers only grant ``getUserMedia`` and ``geolocation`` to
secure origins, with ``localhost`` the one exception, so the scanner page will silently fail
to open the camera on a phone pointed at a plain-HTTP LAN address. ``--ssl-keyfile`` and
``--ssl-certfile`` on uvicorn, or any reverse proxy, is enough for a pilot.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI, File, Form, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .service import MeasurementService

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.environ.get("H2S_DB", os.path.join(ROOT, "out", "hse_measurements.db"))
IMAGE_DIR = os.environ.get("H2S_IMAGES", os.path.join(ROOT, "out", "measurement_images"))

service = MeasurementService(db_path=DB_PATH, image_dir=IMAGE_DIR)

app = FastAPI(
    title="SIH26118 - Passive Colorimetric H2S Exposure Dosimeter",
    description=(
        "Reads a passive lead-acetate dosimeter badge from an ordinary phone camera and "
        "returns the wearer's cumulative H2S exposure. The wearable badge contains no "
        "electronics, so it is intrinsically safe for ATEX/PESO Zone 0; all measurement is "
        "done here, from the photograph."
    ),
    version="1.0.0",
)

# The scanner may be served from a different origin during development (a phone hitting a
# laptop's IP while the page is opened from a file). Tighten this to the known origins before
# any deployment - an exposure database should not accept cross-origin writes from anywhere.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("H2S_CORS", "*").split(","),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _reply(pair):
    status, payload = pair
    return JSONResponse(status_code=status, content=payload)





@app.get("/api/heatmap")
async def get_heatmap(hours: float = 24.0, nx: int = 48, ny: int = 48,
                      radius_m: float = 350.0, power: float = 2.0, limit: int = 2000):
    """Scan points, the interpolated risk surface, spatial clusters and unit rollups."""
    return _reply(service.heatmap({"hours": hours, "nx": nx, "ny": ny,
                                   "radius_m": radius_m, "power": power, "limit": limit}))





@app.get("/api/plant")
async def get_plant():
    return _reply(service.plant())


@app.get("/api/stats")
async def get_stats(since: Optional[str] = None):
    return _reply(service.stats({"since": since}))


@app.get("/api/health")
async def get_health():
    return _reply(service.health())


@app.post("/api/demo/seed")
async def post_seed(n: int = Query(60), hours: float = Query(12.0), seed: int = Query(7)):
    """Write labelled synthetic measurements so the dashboard has data without a badge to hand."""
    return _reply(service.seed_demo({"n": n, "hours": hours, "seed": seed}))


@app.post("/api/demo/clear")
async def post_clear():
    return _reply(service.clear_demo())


from pydantic import BaseModel, Field
from typing import List, Optional

class MeasurementCreate(BaseModel):
    worker_id: str
    worker_name: Optional[str] = None
    zone: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timestamp: Optional[str] = None
    dose_ppm_hr: float
    twa_ppm: float
    status: str
    temperature_c: Optional[float] = None
    humidity_rh: Optional[float] = None

class MeasurementResponse(BaseModel):
    id: int
    worker_id: str
    worker_name: Optional[str] = None
    zone: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    timestamp: str
    dose_ppm_hr: float
    twa_ppm: float
    status: str
    temperature_c: Optional[float] = None
    humidity_rh: Optional[float] = None

@app.post("/api/measurements", response_model=MeasurementResponse)
async def create_measurement(m: MeasurementCreate):
    from datetime import datetime, timezone
    import sqlite3
    ts = m.timestamp or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    cur = service.store._conn.cursor()
    cur.execute("""
        INSERT INTO measurements (
            measured_at, received_at, worker_id, worker_name, unit_code, lat, lng,
            ok, verdict, band, dose_ppm_hr, twa_ppm, temperature_c, humidity_rh
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
    """, (ts, ts, m.worker_id, m.worker_name, m.zone, m.lat, m.lng, m.status, m.status.lower(), m.dose_ppm_hr, m.twa_ppm, m.temperature_c, m.humidity_rh))
    service.store._conn.commit()
    measurement_id = cur.lastrowid
    return MeasurementResponse(
        id=measurement_id, worker_id=m.worker_id, worker_name=m.worker_name, zone=m.zone, 
        lat=m.lat, lng=m.lng, timestamp=ts, dose_ppm_hr=m.dose_ppm_hr, twa_ppm=m.twa_ppm, status=m.status,
        temperature_c=m.temperature_c, humidity_rh=m.humidity_rh
    )

@app.get("/api/measurements", response_model=List[MeasurementResponse])
async def get_measurements(limit: int = 50):
    cur = service.store._conn.cursor()
    cur.execute("""
        SELECT id, worker_id, worker_name, unit_code, lat, lng, measured_at, dose_ppm_hr, twa_ppm, verdict, temperature_c, humidity_rh
        FROM measurements ORDER BY measured_at DESC LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    return [MeasurementResponse(
        id=r['id'], worker_id=r['worker_id'], worker_name=r['worker_name'], zone=r['unit_code'],
        lat=r['lat'], lng=r['lng'],
        timestamp=r['measured_at'], dose_ppm_hr=r['dose_ppm_hr'] or 0.0, twa_ppm=r['twa_ppm'] or 0.0, status=r['verdict'],
        temperature_c=r['temperature_c'], humidity_rh=r['humidity_rh']
    ) for r in rows]

@app.get("/api/measurements/latest", response_model=Optional[MeasurementResponse])
async def get_latest_measurement():
    cur = service.store._conn.cursor()
    cur.execute("""
        SELECT id, worker_id, worker_name, unit_code, lat, lng, measured_at, dose_ppm_hr, twa_ppm, verdict, temperature_c, humidity_rh
        FROM measurements ORDER BY measured_at DESC LIMIT 1
    """)
    r = cur.fetchone()
    if not r: return None
    return MeasurementResponse(
        id=r['id'], worker_id=r['worker_id'], worker_name=r['worker_name'], zone=r['unit_code'],
        lat=r['lat'], lng=r['lng'],
        timestamp=r['measured_at'], dose_ppm_hr=r['dose_ppm_hr'] or 0.0, twa_ppm=r['twa_ppm'] or 0.0, status=r['verdict'],
        temperature_c=r['temperature_c'], humidity_rh=r['humidity_rh']
    )

@app.get("/api/measurements/{id}", response_model=MeasurementResponse)
async def get_measurement(id: int):
    cur = service.store._conn.cursor()
    cur.execute("""
        SELECT id, worker_id, worker_name, unit_code, lat, lng, measured_at, dose_ppm_hr, twa_ppm, verdict, temperature_c, humidity_rh
        FROM measurements WHERE id = ?
    """, (id,))
    r = cur.fetchone()
    if not r: return JSONResponse(status_code=404, content={"detail": "Not Found"})
    return MeasurementResponse(
        id=r['id'], worker_id=r['worker_id'], worker_name=r['worker_name'], zone=r['unit_code'],
        lat=r['lat'], lng=r['lng'],
        timestamp=r['measured_at'], dose_ppm_hr=r['dose_ppm_hr'] or 0.0, twa_ppm=r['twa_ppm'] or 0.0, status=r['verdict'],
        temperature_c=r['temperature_c'], humidity_rh=r['humidity_rh']
    )

# ---- static
# ---- static: the scanner and the dashboard --------------------------------
# Mounted last so the API routes above take precedence over any same-named file.

DASHBOARD = os.path.join(ROOT, "dashboard")

if os.path.isdir(DASHBOARD):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD, html=True), name="dashboard")


@app.get("/")
async def index():
    """Redirect to the dashboard since the Android app is now the primary scanner."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard")
