"""End-to-end smoke test: real HTTP, real engine, real database.  ``python3 -m tests.smoke_endtoend``

This is a *plumbing* test, not an accuracy test. Engine accuracy is settled elsewhere; what is
unverified once a UI exists is the contract between the three layers - whether the keys the two
HTML pages read are the keys the server sends. A dashboard that silently renders ``undefined``
because a field was renamed is the failure this catches, and it is invisible in Python-level
tests of the service.

So it starts hse.serve_dev on a scratch database, renders two synthetic badge photographs,
posts them to /scan as multipart exactly as the scanner does, and then asserts that every field
webapp/index.html and dashboard/index.html dereference is present. The assertion lists below
are transcribed from those two files and are the point of the exercise.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from badge.make_badge import render_badge          # noqa: E402
from sim.render import RenderConfig, render_scan   # noqa: E402
from sim.illuminants import CAMERAS, ILLUMINANTS   # noqa: E402

PORT = int(os.environ.get("SMOKE_PORT", "8731"))
BASE = f"http://127.0.0.1:{PORT}"

# ---- the contracts, transcribed from the two pages ------------------------

SCAN_KEYS = [
    # webapp/index.html: render() and remember()
    "ok", "status", "band", "band_label", "colour", "action",
    "dose_ppm_hr", "twa_ppm", "shift_hours",
    "delta_e", "delta_e00", "delta_l_star",
    "reason", "operator_hint", "warnings",
    "scan_id", "duplicate", "worker_id", "lat", "lng", "location_mocked",
    "unit", "unit_name", "scanned_at", "image_sha256", "detail",
]
HEATMAP_KEYS = ["points", "grid", "clusters", "units", "plant", "bands",
                "n_scans", "n_located", "window", "stats", "workers", "server_time"]
POINT_KEYS = ["id", "worker_id", "scanned_at", "lat", "lng", "accuracy_m", "location_mocked",
              "dose_ppm_hr", "twa_ppm", "delta_l_star", "delta_e00", "verdict", "ok",
              "band", "colour", "unit"]
GRID_KEYS = ["nx", "ny", "bounds", "values", "support", "nearest_m", "radius_m", "power",
             "max", "note"]
BOUNDS_KEYS = ["min_lat", "max_lat", "min_lng", "max_lng"]
STATS_KEYS = ["n", "n_ok", "n_invalid", "n_workers", "n_critical", "n_warning", "n_elevated",
              "n_safe", "peak_twa", "read_rate", "last_scan_at"]
WORKER_KEYS = ["worker_id", "n_scans", "n_invalid", "peak_twa_ppm", "mean_twa_ppm",
               "cumulative_ppm_hr", "n_over_tlv", "last_scan_at"]
UNIT_KEYS = ["unit", "unit_name", "n_scans", "n_invalid", "n_workers", "peak_twa_ppm",
             "mean_twa_ppm", "n_over_tlv", "band", "sour_service"]
PLANT_UNIT_KEYS = ["code", "name", "lat", "lng", "radius_m", "h2s_propensity", "note"]
CLUSTER_KEYS = ["lat", "lng", "n_scans", "n_workers", "peak_twa_ppm", "mean_twa_ppm",
                "radius_m", "band", "unit", "unit_name", "sour_service", "interpretation"]

FAILURES = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f"   {detail}" if detail else ""))
    if not cond:
        FAILURES.append(f"{label} {detail}".strip())
    return cond


def check_keys(label, obj, keys):
    missing = [k for k in keys if k not in obj]
    return check(label, not missing, "" if not missing else f"missing {missing}")


# ---- HTTP helpers ---------------------------------------------------------

def post_multipart(url, fields, image_bytes, filename="badge.jpg"):
    boundary = "----smoke" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        if v is None:
            continue
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n"
                     f"{v}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
                 f"filename=\"{filename}\"\r\nContent-Type: image/jpeg\r\n\r\n".encode()
                 + image_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body))})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        # A 4xx is an expected outcome for parts of this test, not an exception.
        return e.code, json.loads(e.read())


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.status, json.loads(r.read())


def post_empty(url):
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ---- a synthetic photograph -----------------------------------------------

def photo(dose_ppm_hr, illuminant="d65", camera="midrange_a", seed=3, jpeg_quality=92):
    art = render_badge(dose_ppm_hr=dose_ppm_hr, dpi=600.0)
    cfg = RenderConfig(illuminant=ILLUMINANTS[illuminant], camera=CAMERAS[camera],
                       out_size=(1280, 960), shading=0.22, seed=seed)
    bgr = render_scan(art, cfg)
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
    if not ok:
        raise RuntimeError("could not encode the rendered scan")
    return buf.tobytes()


def main():
    tmp = tempfile.mkdtemp(prefix="h2s-smoke-")
    db = os.path.join(tmp, "smoke.db")
    env = dict(os.environ, PYTHONPATH=ROOT)
    proc = subprocess.Popen(
        [sys.executable, "-m", "hse.serve_dev", "--host", "127.0.0.1", "--port", str(PORT),
         "--db", db, "--images", os.path.join(tmp, "img")],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    try:
        # ---- wait for the port ------------------------------------------
        up = False
        for _ in range(60):
            if proc.poll() is not None:
                print(proc.stdout.read())
                raise RuntimeError("server exited during startup")
            try:
                get_json(f"{BASE}/api/health")
                up = True
                break
            except Exception:
                time.sleep(0.4)
        if not check("server starts and answers /api/health", up):
            return 1

        print("\n[1] POST /scan - moderate exposure, with a GPS fix")
        img = photo(3.2)
        st, a = post_multipart(f"{BASE}/scan", {
            "worker_id": "W-1042", "shift_hours": "8", "lat": "12.9771", "lng": "74.8586",
            "accuracy_m": "12.4", "badge_serial": "LOT7-00031", "shift_id": "A",
            "device": "smoke-test", "app_version": "smoke-1.0",
            "client_scan_id": str(uuid.uuid4()),
        }, img)
        check("HTTP 200", st == 200, f"got {st}")
        check_keys("response carries every field the scanner binds", a, SCAN_KEYS)
        check("engine produced a reading", a.get("ok") is True, a.get("reason", ""))
        check("dose is a finite number", isinstance(a.get("dose_ppm_hr"), (int, float)),
              f"dose={a.get('dose_ppm_hr')}")
        check("both darkening observables present",
              a.get("delta_l_star") is not None and a.get("delta_e00") is not None,
              f"-dL*={a.get('delta_l_star')} dE00={a.get('delta_e00')}")
        check("delta_e mirrors delta_e00 for the UI", a.get("delta_e") == a.get("delta_e00"))
        check("band is one the pages know how to colour",
              a.get("band") in ("safe", "elevated", "warning", "critical", "invalid"),
              str(a.get("band")))
        check("supplied coordinate was not overwritten", a.get("location_mocked") is False)
        check("scan was assigned to the ARU it sits inside", a.get("unit") == "ARU",
              str(a.get("unit")))
        check("row was written", isinstance(a.get("scan_id"), int))
        print(f"       dose {a['dose_ppm_hr']} ppm.hr, TWA {a['twa_ppm']} ppm -> "
              f"{a['status']} / {a['band']}")

        print("\n[2] POST /scan - no coordinate supplied, mock GPS path")
        st, b = post_multipart(f"{BASE}/scan", {
            "worker_id": "W-2088", "shift_hours": "8",
            "client_scan_id": str(uuid.uuid4())}, photo(11.0, seed=11))
        check("HTTP 200", st == 200, f"got {st}")
        check("coordinate was generated and flagged", b.get("location_mocked") is True)
        check("a coordinate was nevertheless produced for the map",
              isinstance(b.get("lat"), float) and isinstance(b.get("lng"), float))
        check("higher dose reads higher",
              (b.get("dose_ppm_hr") or 0) > (a.get("dose_ppm_hr") or 0),
              f"{a.get('dose_ppm_hr')} -> {b.get('dose_ppm_hr')}")

        print("\n[3] idempotency - the offline queue may flush the same capture twice")
        cid = str(uuid.uuid4())
        st, c1 = post_multipart(f"{BASE}/scan", {"worker_id": "W-3001",
                                                 "client_scan_id": cid}, img)
        st, c2 = post_multipart(f"{BASE}/scan", {"worker_id": "W-3001",
                                                 "client_scan_id": cid}, img)
        check("replay is recognised, not double-logged",
              c2.get("duplicate") is True and c2.get("scan_id") == c1.get("scan_id"),
              f"{c1.get('scan_id')} vs {c2.get('scan_id')} dup={c2.get('duplicate')}")

        print("\n[4] a malformed request is a 4xx, an unreadable badge is not")
        st, err = post_multipart(f"{BASE}/scan", {"worker_id": "W-9"}, b"")
        check("no image -> 400", st == 400, f"got {st}")
        st, err = post_multipart(f"{BASE}/scan", {"worker_id": "W-9"}, b"this is not a jpeg")
        check("undecodable file -> 400", st == 400, f"got {st}")
        blank = cv2.imencode(".jpg", np.full((640, 480, 3), 40, np.uint8))[1].tobytes()
        st, d = post_multipart(f"{BASE}/scan", {"worker_id": "W-9",
                                                "client_scan_id": str(uuid.uuid4())}, blank)
        check("badge absent from the frame -> 200 with ok:false", st == 200 and not d.get("ok"),
              f"status={st} ok={d.get('ok')}")
        check("failure carries an operator hint the scanner can display",
              bool(d.get("operator_hint")), repr(d.get("operator_hint"))[:90])
        check("failed scan is still logged", isinstance(d.get("scan_id"), int))
        check("failed scan bands as invalid", d.get("band") == "invalid", str(d.get("band")))

        print("\n[5] seed demo rows, then GET /api/heatmap")
        st, seeded = post_empty(f"{BASE}/api/demo/seed?n=70&hours=8")
        check("demo seed accepted", st == 200 and seeded.get("inserted") == 70,
              str(seeded.get("inserted")))
        st, h = get_json(f"{BASE}/api/heatmap?hours=24&nx=56&ny=56")
        check("HTTP 200", st == 200, f"got {st}")
        check_keys("payload carries every top-level key the dashboard reads", h, HEATMAP_KEYS)
        check_keys("grid", h.get("grid", {}), GRID_KEYS)
        check_keys("grid.bounds", h.get("grid", {}).get("bounds", {}), BOUNDS_KEYS)
        check_keys("stats", h.get("stats", {}), STATS_KEYS)
        if h.get("points"):
            check_keys("points[0]", h["points"][0], POINT_KEYS)
        if h.get("workers"):
            check_keys("workers[0]", h["workers"][0], WORKER_KEYS)
        if h.get("units"):
            check_keys("units[0]", h["units"][0], UNIT_KEYS)
        if h.get("clusters"):
            check_keys("clusters[0]", h["clusters"][0], CLUSTER_KEYS)
        else:
            check("clusters is a list even when empty", isinstance(h.get("clusters"), list))
        check_keys("plant.units[0]", h.get("plant", {}).get("units", [{}])[0], PLANT_UNIT_KEYS)

        g = h["grid"]
        check("grid rows match ny", len(g["values"]) == g["ny"], f"{len(g['values'])}/{g['ny']}")
        check("grid cols match nx", all(len(r) == g["nx"] for r in g["values"]))
        check("support layer has the same shape as values",
              len(g["support"]) == g["ny"] and all(len(r) == g["nx"] for r in g["support"]))
        check("nearest_m layer has the same shape as values",
              len(g["nearest_m"]) == g["ny"] and all(len(r) == g["nx"] for r in g["nearest_m"]))
        flat = [v for row in g["values"] for v in row]
        n_null = sum(1 for v in flat if v is None)
        check("unsupported cells are null rather than coloured green", n_null > 0,
              f"{n_null}/{len(flat)} cells have no badge within {g['radius_m']} m")
        check("interpolated maximum does not exceed the highest badge",
              g["max"] is None or g["max"] <= max(
                  [p["twa_ppm"] for p in h["points"] if p.get("twa_ppm") is not None] or [0])
              + 1e-9, f"grid max {g['max']}")
        check("bounds are ordered", g["bounds"]["min_lat"] < g["bounds"]["max_lat"]
              and g["bounds"]["min_lng"] < g["bounds"]["max_lng"])
        check("demo rows are identifiable as synthetic",
              any(str(w["worker_id"]).startswith("DEMO-") for w in h["workers"]))
        check("measured rows sit alongside them",
              any(w["worker_id"] == "W-1042" for w in h["workers"]))
        check("read_rate reflects the deliberately-failed scan",
              h["stats"]["read_rate"] is not None and h["stats"]["read_rate"] < 1.0,
              f"read_rate={h['stats']['read_rate']}")
        print(f"       {h['n_scans']} scans, {h['n_located']} located, "
              f"{len(h['clusters'])} clusters, peak TWA {h['stats']['peak_twa']} ppm")

        print("\n[6] the remaining routes the pages hit")
        st, det = get_json(f"{BASE}/api/scans/{a['scan_id']}")
        check("GET /api/scans/{id} -> 200", st == 200, f"got {st}")
        check("audit record embeds the full engine result",
              isinstance(det.get("result"), dict) and "colour" in det["result"])
        check("the reading can be re-derived from the stored result",
              abs((det["result"]["exposure"]["dose_ppm_hr"] or 0)
                  - (a["dose_ppm_hr"] or 0)) < 1e-9)
        st, sc = get_json(f"{BASE}/api/scans?limit=5")
        check("GET /api/scans -> 200 with rows", st == 200 and sc.get("n", 0) > 0)
        st, pl = get_json(f"{BASE}/api/plant")
        check("GET /api/plant -> 17 units", st == 200 and len(pl.get("units", [])) == 17,
              str(len(pl.get("units", []))))
        st, stt = get_json(f"{BASE}/api/stats")
        check("GET /api/stats -> 200", st == 200 and "stats" in stt)

        print("\n[7] the pages are actually served")
        for path, needle in (("/", b"Scan Badge"),
                             ("/webapp/index.html", b"getUserMedia"),
                             ("/manifest.webmanifest", b"H2S Scanner"),
                             ("/sw.js", b"h2s-scanner"),
                             ("/webapp/icon.svg", b"<svg"),
                             ("/dashboard/", b"api/heatmap")):
            try:
                with urllib.request.urlopen(BASE + path, timeout=20) as r:
                    body = r.read()
                check(f"GET {path}", r.status == 200 and needle in body,
                      f"{r.status}, {len(body)} bytes")
            except Exception as e:
                check(f"GET {path}", False, str(e))

        print("\n[8] clear demo removes only the synthetic rows")
        st, cl = post_empty(f"{BASE}/api/demo/clear")
        st, h2 = get_json(f"{BASE}/api/heatmap?hours=24")
        check("demo rows gone", not any(str(w["worker_id"]).startswith("DEMO-")
                                       for w in h2["workers"]))
        check("measured rows survive", any(w["worker_id"] == "W-1042"
                                          for w in h2["workers"]))

        print("\n" + "=" * 72)
        if FAILURES:
            print(f"  {len(FAILURES)} FAILURE(S)")
            for f in FAILURES:
                print("   - " + f)
            return 1
        print("  all checks passed - scanner, dashboard, API, engine and store agree")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
