# SIH26118 — Passive Colorimetric H₂S Exposure-Dosimeter Wristband

Smart India Hackathon 2026 · MRPL (Mangalore Refinery and Petrochemicals Limited)

A worker wears a badge with no electronics in it. Lead acetate in the reagent pad reacts with
hydrogen sulphide that diffuses through an ePTFE membrane — Pb(CH₃COO)₂ + H₂S → PbS↓ +
2CH₃COOH — and the pad darkens in proportion to accumulated dose. At the end of the shift
someone photographs the badge with an ordinary phone and this software turns that photograph
into a number in ppm·hr, a time-weighted average in ppm, and a verdict against the ACGIH
limits.

The wearable is passive because it has to be: MRPL's sour-service areas are ATEX/PESO Zone 0,
where an intrinsically safe electronic dosimeter is expensive and a non-certified one is
forbidden. Every gram of intelligence therefore lives on this side of the camera.

## Quick start

Zero-install path — no FastAPI, no wheels, standard library only:

```bash
python3 -m hse.serve_dev --port 8000 --seed-demo 80
```

Then open the scanner at <http://localhost:8000/> and the HSE dashboard at
<http://localhost:8000/dashboard/>. `--seed-demo 80` writes 80 clearly-labelled synthetic
scans so the map has something on it; without it both pages come up empty and correct.

FastAPI path, if the wheels are present, for the OpenAPI docs at `/docs`:

```bash
pip install -r requirements.txt
uvicorn hse.api:app --host 0.0.0.0 --port 8000
```

Both serve the same routes over the same service layer. `hse/service.py` holds the route logic
as plain functions — bytes and dicts in, `(status, payload)` out — and the two servers are thin
adapters over it, so the stdlib one is not a toy that drifts from the real one.

### Reading a badge from the phone

The camera and the GPS both require a secure origin. `http://localhost` counts, so a laptop
webcam works immediately, but a phone pointed at your machine's LAN address will silently get
no camera. Either tunnel it (`cloudflared tunnel --url http://localhost:8000`, or ngrok) or
put a TLS terminator in front. This is a browser rule, not something the app can opt out of.

Scanning is a full-frame operation: fill the reticle with the badge head, keep the four corner
markers visible, and **switch the torch on**. The torch is treated as part of the instrument
rather than a convenience. Under refinery sodium vapour lighting the red/blue channel balance
collapses to 0.005–0.2 and the reading is not defensible; with the torch on it recovers to
0.53–0.72 and reads within about 3%. The scanner warns below a channel balance of 0.30.

If the network is down the capture is queued in IndexedDB and flushed later — the photograph
is the part that cannot be retaken, so it is never blocked on connectivity. A queued scan
shows a QUEUED card that explicitly says the worker is *not yet cleared*.

### Printing badges

```bash
python3 -m badge.make_badge badge  --dose 2.0 -o out/badge.png --dpi 600
python3 -m badge.make_badge sheet  --outdir out          # A4 of blanks
python3 -m badge.make_badge series --outdir out          # dose ladder + truth CSV
```

The artwork carries four ArUco markers for pose, and — the part that matters — twelve
reference patches on a ring around the well, including two neutral SUBSTRATE patches. The dose
is measured as a *difference* between the pad and those on-badge patches in the same exposure,
so most absolute colour error cancels before it reaches the arithmetic. Print at 600 dpi on
matte stock; glossy stock specularly reflects the torch into the pad.

## Endpoints

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/scan` | multipart badge photo → reading. `image` plus `worker_id`, `shift_hours`, `lat`, `lng`, `accuracy_m`, `client_scan_id`, … |
| GET | `/api/heatmap?hours=8&nx=48&ny=48` | pins, IDW grid, clusters, per-unit and per-worker rollups |
| GET | `/api/scans?limit=500` | scan log |
| GET | `/api/scans/{id}` | one scan with the complete engine result embedded |
| GET | `/api/plant` | the 17 mapped MRPL process units |
| GET | `/api/stats` | window statistics and worker rollup |
| GET | `/api/health` | liveness, active observable, shift length |
| POST | `/api/demo/seed?n=80&hours=8` | synthetic rows, labelled `shift_id=DEMO` |
| POST | `/api/demo/clear` | delete only those rows |

A failed *reading* is still a successful *request*: HTTP 200 with `ok: false`, the engine's
reason and an operator hint the scanner can display. 4xx is reserved for a malformed request —
no image, undecodable file, oversized upload. `client_scan_id` makes `/scan` idempotent, which
the offline queue depends on; a duplicated exposure record is a false compliance signal in both
directions.

Configuration is by environment for the FastAPI app (`H2S_DB`, `H2S_IMAGES`, `H2S_CORS`) and by
flag for the dev server (`--db`, `--images`, `--no-images`).

## Verifying it

```bash
python3 -m tests.test_ciede2000     # CIEDE2000 against the Sharma reference vectors
python3 -m tests.smoke_endtoend     # the whole stack over real HTTP
```

The smoke test starts a server on a scratch database, renders synthetic badge photographs
through the illuminant/camera simulator, posts them as multipart exactly as the scanner does,
and then asserts that every field the two HTML pages dereference is present in the response.
That last part is the point: engine accuracy is settled elsewhere, but a dashboard rendering
`undefined` because a field was renamed is invisible to Python-level tests. It caught exactly
that — the service was reading `result["assessment"]` where the engine emits `result["exposure"]`,
so every scan through the API was losing its dose and every pin on the map would have been grey.

## Deploying for a pilot

`hse/schema_postgis.sql` is the migration. The SQLite store mirrors it column for column, so a
pilot can start on a laptop and move to PostGIS without the application layer changing shape.

On an air-gapped network the dashboard's two `unpkg.com` tags for Leaflet 1.9.4 will not
resolve. Vendor them — drop `leaflet.js`, `leaflet.css` and the `images/` directory into
`dashboard/vendor/` and repoint the two tags. The page already degrades to an explanatory
message rather than a blank screen if Leaflet is absent, but that is a diagnostic, not a
deployment.

Scan images are retained by default, because a colorimetric exposure figure whose source
photograph was discarded cannot be re-examined when it is disputed, and disputes are what an
exposure record exists to settle. Sites with a rule against storing photographs can pass
`--no-images`; the reading, the diagnostics and the SHA-256 are still stored, so tampering
stays detectable.

## What this is not, and where it is soft

**The unit coordinates are approximate.** The 17 MRPL process units in `hse/core.py` are
plausible demonstration positions, not survey data. Replace them from site GIS before anyone
draws a conclusion from where a pin sits.

**The heat layer is interpolation, not dispersion.** It is inverse-distance weighting over
badge readings, power 2, 350 m radius, 25 m smoothing. Being an exact interpolator it can never
exceed its highest observation, and it systematically under-represents a sharp local source —
the surface peak generally sits somewhere between several high badges rather than on the worst
one. Read it as "where have we measured exposure", never as a plume model. Cells with no badge
within the radius are left uncoloured rather than painted green, and thin evidence is drawn
faint, because a confident green where nothing was measured is the most dangerous thing a
safety map can show.

**Colour is never the only channel.** Each verdict is a colour block *and* the word *and* a
distinct glyph. Roughly one man in twelve has a red/green deficiency, and a safety signal that
exists only as a hue is not a safety signal.

**The calibration curve is simulator-derived.** This is the real limitation. Dose is currently
mapped from −ΔL\* using coefficients fitted against rendered badges, not against a gas chamber,
and there is a known systematic positive bias of roughly +11% in the low-dose region around
4 ppm·hr. Before any field use the curve must be re-fitted against certified H₂S atmospheres at
known concentration-time products, with the pad chemistry, membrane lot and print stock that
will actually be worn. The engine reports −ΔL\* and ΔE₀₀ alongside every dose precisely so that
a re-fit does not require touching the vision code.

**Humidity, temperature and lot variation are unmodelled.** Lead acetate response depends on
all three. Membrane lot and badge serial are recorded per scan so the dependence can be
characterised later; nothing corrects for it yet.

## Layout

`engine/` is the measurement path — badge geometry, ArUco detection and homography, ROI
sampling, illumination normalisation, colorimetry, dosimetry, and `pipeline.py` which chains
them and returns one auditable result dict. `sim/` renders synthetic badge photographs under 40
illuminant × camera combinations and is what the engine was tuned against. `badge/` generates
printable artwork from the same spec constants the scanner draws its reticle from, so guide and
artwork cannot drift. `hse/` is the service, store and plant model. `webapp/` is the worker's
scanner as an offline-capable PWA; `dashboard/` is the HSE risk map.

Around 7,500 lines of Python plus the two pages. Python 3.10, numpy and OpenCV, nothing else
required.

## Why −ΔL\* rather than ΔE₀₀

The obvious choice for "how much did this colour change" is CIEDE2000, and it is the wrong one
here. PbS deposition moves the pad almost purely along the lightness axis — 97% of the locus —
so ΔE₀₀ spends most of its sensitivity on chroma noise it should be ignoring. Measured across
40 camera × illuminant combinations at 8 ppm·hr: ΔE₀₀ gave 11.6% rms error and 40.4% worst
case, −ΔL\* gave 4.9% and 14.8%. ΔE₀₀ is still computed and stored on every scan, as a
secondary observable and an integrity check on the chroma that should not have moved.
