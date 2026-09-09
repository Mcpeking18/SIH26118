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

from .service import ScanService

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.environ.get("H2S_DB", os.path.join(ROOT, "out", "hse_scans.db"))
IMAGE_DIR = os.environ.get("H2S_IMAGES", os.path.join(ROOT, "out", "scan_images"))

service = ScanService(db_path=DB_PATH, image_dir=IMAGE_DIR)

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


@app.post("/scan")
async def post_scan(
    image: UploadFile = File(..., description="JPEG or PNG frame containing the badge"),
    worker_id: str = Form("UNKNOWN"),
    worker_name: Optional[str] = Form(None),
    shift_id: Optional[str] = Form(None),
    badge_serial: Optional[str] = Form(None),
    lat: Optional[str] = Form(None),
    lng: Optional[str] = Form(None),
    accuracy_m: Optional[str] = Form(None),
    shift_hours: Optional[str] = Form(None),
    scanned_at: Optional[str] = Form(None),
    device: Optional[str] = Form(None),
    app_version: Optional[str] = Form(None),
    client_scan_id: Optional[str] = Form(None),
):
    """Read one badge photograph.

    Returns 200 with ``ok: false`` when the image could not be read into a defensible
    number - that is a legitimate outcome carrying an operator hint, not a server error.
    """
    data = await image.read()
    return _reply(service.scan(data, {
        "worker_id": worker_id, "worker_name": worker_name, "shift_id": shift_id,
        "badge_serial": badge_serial, "lat": lat, "lng": lng, "accuracy_m": accuracy_m,
        "shift_hours": shift_hours, "scanned_at": scanned_at, "device": device,
        "app_version": app_version, "client_scan_id": client_scan_id,
    }))


@app.get("/api/heatmap")
async def get_heatmap(hours: float = 24.0, nx: int = 48, ny: int = 48,
                      radius_m: float = 350.0, power: float = 2.0, limit: int = 2000):
    """Scan points, the interpolated risk surface, spatial clusters and unit rollups."""
    return _reply(service.heatmap({"hours": hours, "nx": nx, "ny": ny,
                                   "radius_m": radius_m, "power": power, "limit": limit}))


@app.get("/api/scans")
async def get_scans(since: Optional[str] = None, until: Optional[str] = None,
                    worker_id: Optional[str] = None, band: Optional[str] = None,
                    include_invalid: str = "1", limit: int = 500):
    return _reply(service.scans({"since": since, "until": until, "worker_id": worker_id,
                                 "band": band, "include_invalid": include_invalid,
                                 "limit": limit}))


@app.get("/api/scans/{scan_id}")
async def get_scan(scan_id: int):
    """The full audit record for one scan, including the complete engine result."""
    return _reply(service.scan_detail(scan_id))


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
    """Write labelled synthetic scans so the dashboard has data without a badge to hand."""
    return _reply(service.seed_demo({"n": n, "hours": hours, "seed": seed}))


@app.post("/api/demo/clear")
async def post_clear():
    return _reply(service.clear_demo())


# ---- static: the scanner and the dashboard --------------------------------
# Mounted last so the API routes above take precedence over any same-named file.

WEBAPP = os.path.join(ROOT, "webapp")
DASHBOARD = os.path.join(ROOT, "dashboard")

if os.path.isdir(WEBAPP):
    app.mount("/webapp", StaticFiles(directory=WEBAPP, html=True), name="webapp")
if os.path.isdir(DASHBOARD):
    app.mount("/dashboard", StaticFiles(directory=DASHBOARD, html=True), name="dashboard")


@app.get("/")
async def index():
    """Land on the scanner, since that is what a worker at the gate opens."""
    page = os.path.join(WEBAPP, "index.html")
    if os.path.exists(page):
        return FileResponse(page)
    return JSONResponse({"service": "sih26118", "endpoints": ["/scan", "/api/heatmap",
                                                              "/api/scans", "/api/plant",
                                                              "/api/health", "/docs"]})
