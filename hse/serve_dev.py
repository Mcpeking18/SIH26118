"""The same API on the standard library alone. ``python3 -m hse.serve_dev --port 8000``

Exists because FastAPI and uvicorn are wheels that have to be downloaded, and this has to be
demonstrable on a machine where that is not possible - an air-gapped plant laptop, a locked-down
lab PC, or any environment where ``pip install`` is blocked. The routes, the JSON and the
database are identical to :mod:`hse.api`, because both call the same
:class:`hse.service.ScanService` methods; only the HTTP plumbing here is hand-rolled.

It is single-threaded-per-request via ``ThreadingHTTPServer`` and has no TLS, so it is for
development, demonstration and offline use. Anything carrying real exposure records belongs
behind the FastAPI app and a proper server with HTTPS - and note that phones will refuse to
open the camera over plain HTTP anyway, so for a phone demo either use a tunnel that
terminates TLS or accept ``localhost`` on the laptop's own webcam.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hse.service import ScanService  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

_CT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def parse_multipart(body: bytes, content_type: str) -> tuple:
    """Minimal ``multipart/form-data`` parser: returns ``(fields, files)``.

    Hand-written rather than using ``cgi.FieldStorage`` because ``cgi`` is deprecated in 3.11
    and removed in 3.13, and this file's whole purpose is to run wherever Python runs without
    anything being installed. It handles exactly what the scanner sends: flat text fields plus
    one binary file part, no nested multipart, no transfer encodings.
    """
    fields, files = {}, {}
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type or "", re.I)
    if not m:
        return fields, files
    boundary = (m.group(1) or m.group(2)).strip().encode()
    sep = b"--" + boundary
    for part in body.split(sep):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        head, _, data = part.partition(b"\r\n\r\n")
        if not _:
            continue
        headers = head.decode("utf-8", "replace")
        nm = re.search(r'name="([^"]*)"', headers)
        if not nm:
            continue
        name = nm.group(1)
        fn = re.search(r'filename="([^"]*)"', headers)
        data = data[:-2] if data.endswith(b"\r\n") else data
        if fn:
            files[name] = {"filename": fn.group(1), "data": data}
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


class Handler(BaseHTTPRequestHandler):
    server_version = "sih26118-dev"
    service: ScanService = None

    # ---- helpers --------------------------------------------------------

    def _json(self, status: int, payload):
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, base: str, rel: str):
        rel = rel.lstrip("/") or "index.html"
        path = os.path.normpath(os.path.join(base, rel))
        if not path.startswith(os.path.abspath(base)):
            return self._json(403, {"error": "path traversal refused"})
        if os.path.isdir(path):
            path = os.path.join(path, "index.html")
        if not os.path.exists(path):
            return self._json(404, {"error": f"no such file: {rel}"})
        with open(path, "rb") as fh:
            data = fh.read()
        ct = _CT_TYPES.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        # No caching in development: a stale service worker or scanner page is the single
        # most confusing failure mode when iterating on this UI.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s - %s\n" % (self.address_string(), fmt % args))

    # ---- routes ---------------------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        p = u.path.rstrip("/") or "/"
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        svc = self.service

        if p == "/api/health":
            return self._json(*svc.health())
        if p == "/api/heatmap":
            return self._json(*svc.heatmap(q))
        if p == "/api/scans":
            return self._json(*svc.scans(q))
        if re.fullmatch(r"/api/scans/\d+", p):
            return self._json(*svc.scan_detail(int(p.rsplit("/", 1)[1])))
        if p == "/api/plant":
            return self._json(*svc.plant())
        if p == "/api/stats":
            return self._json(*svc.stats(q))
        if p == "/":
            return self._static(os.path.join(ROOT, "webapp"), "index.html")
        if p.startswith("/webapp"):
            return self._static(os.path.join(ROOT, "webapp"), p[len("/webapp"):])
        if p.startswith("/dashboard"):
            return self._static(os.path.join(ROOT, "dashboard"), p[len("/dashboard"):])
        # Service-worker scope requires sw.js at the root it controls.
        if p in ("/sw.js", "/manifest.webmanifest"):
            return self._static(os.path.join(ROOT, "webapp"), p)
        return self._json(404, {"error": f"no route for {p}"})

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path.rstrip("/") or "/"
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        svc = self.service
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""

        if p == "/scan":
            ct = self.headers.get("Content-Type", "")
            if "multipart/form-data" in ct.lower():
                fields, files = parse_multipart(body, ct)
                part = files.get("image") or files.get("file") or (
                    next(iter(files.values())) if files else None)
                return self._json(*svc.scan(part["data"] if part else b"", fields))
            if "application/json" in ct.lower():
                # Base64 fallback, used by the offline queue flush where a stored Blob is
                # easier to replay as a data URL than to rebuild as a multipart body.
                import base64
                try:
                    payload = json.loads(body or b"{}")
                except ValueError:
                    return self._json(400, {"error": "malformed JSON body"})
                raw = payload.pop("image_base64", "") or ""
                raw = raw.split(",", 1)[1] if raw.startswith("data:") else raw
                try:
                    data = base64.b64decode(raw)
                except Exception:
                    return self._json(400, {"error": "image_base64 is not valid base64"})
                return self._json(*svc.scan(data, {k: (None if v is None else str(v))
                                                   for k, v in payload.items()}))
            return self._json(415, {"error": "send multipart/form-data with an 'image' part, "
                                             "or JSON with 'image_base64'"})
        if p == "/api/demo/seed":
            return self._json(*svc.seed_demo(q))
        if p == "/api/demo/clear":
            return self._json(*svc.clear_demo())
        return self._json(404, {"error": f"no route for {p}"})


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--db", default=os.environ.get(
        "H2S_DB", os.path.join(ROOT, "out", "hse_scans.db")))
    ap.add_argument("--images", default=os.environ.get(
        "H2S_IMAGES", os.path.join(ROOT, "out", "scan_images")))
    ap.add_argument("--no-images", action="store_true",
                    help="do not retain uploaded photographs (hash is still stored)")
    ap.add_argument("--seed-demo", type=int, default=0,
                    help="write N labelled synthetic scans on startup")
    args = ap.parse_args(argv)

    Handler.service = ScanService(db_path=args.db,
                                  image_dir=None if args.no_images else args.images)
    if args.seed_demo:
        status, out = Handler.service.seed_demo({"n": args.seed_demo})
        print(f"  seeded {out.get('inserted')} synthetic scans (shift_id=DEMO)")

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    shown = "localhost" if args.host in ("0.0.0.0", "") else args.host
    print(f"\n  SIH26118 H2S dosimeter - stdlib server (no FastAPI required)")
    print(f"  database        {args.db}")
    print(f"  scanner         http://{shown}:{args.port}/")
    print(f"  dashboard       http://{shown}:{args.port}/dashboard/")
    print(f"  heatmap JSON    http://{shown}:{args.port}/api/heatmap?hours=24")
    print(f"\n  Note: browsers only allow camera and geolocation on a secure origin, so the")
    print(f"  scanner's camera works at localhost but not at a plain-http LAN address. Use")
    print(f"  the file-upload fallback on the page, or terminate TLS in front of it.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
