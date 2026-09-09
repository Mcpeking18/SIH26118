"""Spatial and risk logic for the HSE layer: plant layout, banding, interpolation.

Pure stdlib plus numpy. No web framework, no database, no I/O - everything here is a
function of its arguments, so the same code serves the FastAPI app, the stdlib development
server and any offline analysis, and can be checked without either of them running.

WHAT THIS LAYER IS ALLOWED TO CLAIM
-----------------------------------
It turns a set of point scans into a map. It is worth being precise about what that map is,
because a smooth coloured surface is extremely persuasive and this one is an interpolation
between sparse badge readings, not a gas dispersion model.

Each scan is a *worker's cumulative personal exposure* over a shift, tagged with the place
the badge was scanned - which is usually the exit kiosk or wherever the supervisor stood,
not where the gas was. Inverse-distance weighting between those points produces a field
that answers "whose badges near here came back high?" It does not answer "what is the
concentration here now", it has no wind in it, no source term, no atmospheric stability
class, and it cannot see a leak in an area nobody walked through. It is a *screening and
triage* aid: it ranks areas for attention and it makes a spatial pattern in the exposure
record visible. Fixed-point gas detectors, and a survey with a portable monitor, remain the
instruments that tell you where a leak is.

The functions below therefore report their own support - how many scans, how far away the
nearest one was - alongside every interpolated value, so the UI can grey out a cell that is
being extrapolated from one badge 400 m away instead of colouring it confidently.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

__all__ = [
    "PlantUnit", "Plant", "MRPL", "H2S_UNITS",
    "haversine_m", "local_xy_m", "bounds_of",
    "RISK_BANDS", "band_for", "band_for_dose",
    "idw_grid", "cluster_scans", "unit_rollup", "heatmap_payload",
]


# ---------------------------------------------------------------------------
# Plant layout
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlantUnit:
    """One process area, as a labelled circle.

    A circle rather than a polygon on purpose: the boundary here is *illustrative*, and a
    hand-drawn polygon would imply a survey accuracy this layout does not have. Anyone
    deploying this replaces :data:`MRPL` with the site's own GIS coordinates, at which point
    polygons become appropriate and the PostGIS schema is ready for them.
    """

    code: str
    name: str
    lat: float
    lng: float
    radius_m: float
    #: Relative H2S likelihood for this kind of unit, 0-1. Used only to order the operator's
    #: attention and to seed the demo, never to modify a measured dose.
    h2s_propensity: float = 0.2
    note: str = ""


@dataclass(frozen=True)
class Plant:
    name: str
    lat: float
    lng: float
    units: tuple = ()

    def unit(self, code: str) -> PlantUnit:
        for u in self.units:
            if u.code == code:
                return u
        raise KeyError(code)

    def nearest_unit(self, lat: float, lng: float):
        """``(unit, distance_m)`` for the closest unit centre, or ``(None, inf)``."""
        best, best_d = None, float("inf")
        for u in self.units:
            d = haversine_m(lat, lng, u.lat, u.lng)
            if d < best_d:
                best, best_d = u, d
        return best, best_d

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "lat": self.lat,
            "lng": self.lng,
            "units": [asdict(u) for u in self.units],
        }


#: MRPL Phase-1/2/3 process areas, Katipalla, Mangalore.
#:
#: COORDINATES ARE APPROXIMATE AND FOR DEMONSTRATION. They place recognisable units in
#: roughly the right relative positions inside the real refinery's footprint so the map is
#: legible and the distances are realistic; they are not surveyed positions and must be
#: replaced from the site's GIS before this is used operationally. The ordering of
#: ``h2s_propensity`` is the part that carries real information, and it follows the
#: process chemistry rather than being assigned arbitrarily: sour water and amine
#: regeneration handle dissolved and stripped H2S directly, the SRU exists to convert it,
#: the coker and hydrotreaters generate it, and the polypropylene and utility areas have
#: no sour service at all.
MRPL = Plant(
    name="MRPL Refinery, Mangalore",
    lat=12.9782,
    lng=74.8560,
    units=(
        PlantUnit("SRU-1", "Sulphur Recovery Unit 1", 12.9760, 74.8598, 90, 0.95,
                  "Claus train. Acid gas feed is majority H2S - highest inherent exposure "
                  "potential on site."),
        PlantUnit("SRU-2", "Sulphur Recovery Unit 2", 12.9754, 74.8611, 90, 0.95,
                  "Second Claus train, same service as SRU-1."),
        PlantUnit("ARU", "Amine Regeneration Unit", 12.9771, 74.8586, 75, 0.90,
                  "Rich amine stripping. Regenerator overhead is concentrated acid gas; "
                  "flange and sample-point leaks are the usual exposure route."),
        PlantUnit("SWS", "Sour Water Stripper", 12.9779, 74.8600, 65, 0.88,
                  "Strips H2S and NH3 from sour water. Sample points and the stripper "
                  "overhead line are the hot spots."),
        PlantUnit("DCU", "Delayed Coker Unit", 12.9744, 74.8570, 120, 0.75,
                  "Thermal cracking liberates H2S; coke drum switching and decoking are "
                  "the exposure events."),
        PlantUnit("HCU", "Hydrocracker Unit", 12.9756, 74.8546, 110, 0.70,
                  "High-pressure hydrotreating converts sulphur to H2S in the recycle gas."),
        PlantUnit("DHDT", "Diesel Hydrotreater", 12.9769, 74.8534, 95, 0.65,
                  "Sour stripper offgas."),
        PlantUnit("CDU-1", "Crude Distillation Unit 1", 12.9795, 74.8555, 130, 0.45,
                  "Crude preheat and atmospheric column. Sour crude carries H2S into the "
                  "overhead system."),
        PlantUnit("CDU-2", "Crude Distillation Unit 2", 12.9805, 74.8572, 130, 0.45),
        PlantUnit("TANK-N", "Tank Farm North", 12.9820, 74.8535, 160, 0.35,
                  "Sour crude and intermediate storage. Tank roof and gauging-hatch "
                  "exposures; confined space on entry."),
        PlantUnit("TANK-S", "Tank Farm South", 12.9736, 74.8524, 150, 0.30),
        PlantUnit("ETP", "Effluent Treatment Plant", 12.9725, 74.8601, 100, 0.55,
                  "Biological treatment. H2S from anaerobic pockets, sumps and sludge "
                  "handling - a classic fatality setting because the source is not obvious."),
        PlantUnit("FLARE", "Flare Area", 12.9740, 74.8628, 70, 0.40,
                  "Knock-out drum and seal water. Elevated risk during flame-out."),
        PlantUnit("JETTY", "Marine Terminal Lines", 12.9700, 74.8480, 140, 0.25,
                  "Product transfer. Sour service only during specific movements."),
        PlantUnit("PP", "Polypropylene Unit", 12.9783, 74.8620, 100, 0.05,
                  "No sour service. Present so the map shows a genuine low-risk area "
                  "rather than implying the whole refinery is hazardous."),
        PlantUnit("UTIL", "Utilities and Cooling Towers", 12.9800, 74.8600, 110, 0.05),
        PlantUnit("ADMIN", "Administration and Control Room", 12.9812, 74.8508, 80, 0.02,
                  "Muster point and scanning kiosk location."),
    ),
)

#: The units whose service actually contains H2S, worst first. The dashboard uses this to
#: order its attention list; a high reading in an area on this list is consistent with a
#: process leak, whereas the same reading at ADMIN points at a badge or scanning problem.
H2S_UNITS = tuple(u.code for u in sorted(MRPL.units, key=lambda u: -u.h2s_propensity)
                  if u.h2s_propensity >= 0.30)


# ---------------------------------------------------------------------------
# Geodesy - small enough distances that the simple forms are exact enough
# ---------------------------------------------------------------------------

_EARTH_R_M = 6371008.8


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres. Sub-metre agreement at refinery scale."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R_M * math.asin(math.sqrt(min(1.0, a)))


def local_xy_m(lat, lng, lat0: float, lng0: float):
    """Equirectangular projection to local metres about ``(lat0, lng0)``.

    Used for the interpolation grid and the clustering, where thousands of pairwise
    distances are needed and a vectorised approximation is worth having. Over a 3 km
    refinery the error against haversine is well under a metre, which is far below the
    accuracy of a phone's GPS fix - the dominant spatial uncertainty here is the 5-30 m
    of the fix itself, and near tall columns and steel structures it is worse.
    """
    lat = np.asarray(lat, dtype=np.float64)
    lng = np.asarray(lng, dtype=np.float64)
    k = math.cos(math.radians(lat0))
    x = np.radians(lng - lng0) * k * _EARTH_R_M
    y = np.radians(lat - lat0) * _EARTH_R_M
    return x, y


def bounds_of(points, pad_m: float = 250.0) -> dict:
    """Bounding box around ``[(lat, lng), ...]``, padded, falling back to the plant."""
    pts = [(float(a), float(b)) for a, b in points
           if a is not None and b is not None
           and math.isfinite(float(a)) and math.isfinite(float(b))]
    if not pts:
        c = MRPL
        d = 0.02
        return {"min_lat": c.lat - d, "max_lat": c.lat + d,
                "min_lng": c.lng - d, "max_lng": c.lng + d}
    lats = [p[0] for p in pts]
    lngs = [p[1] for p in pts]
    mid = sum(lats) / len(lats)
    dlat = pad_m / 111320.0
    dlng = pad_m / max(111320.0 * math.cos(math.radians(mid)), 1.0)
    return {"min_lat": min(lats) - dlat, "max_lat": max(lats) + dlat,
            "min_lng": min(lngs) - dlng, "max_lng": max(lngs) + dlng}


# ---------------------------------------------------------------------------
# Risk banding
# ---------------------------------------------------------------------------

#: Bands in TWA terms against the 1 ppm ACGIH TLV-TWA, worst first.
#:
#: The engine already returns a per-scan verdict from
#: :class:`engine.dosimetry.ExposureLimits`; this is the *map's* banding, which needs a
#: fourth level the single-scan verdict does not have. A worker at 0.6 ppm TWA is compliant
#: and must not be shown as a violation, but an area where several badges land at 0.6 is
#: exactly what an HSE lead wants to look at before it becomes an exceedance. So ELEVATED
#: exists between SAFE and WARNING, and it is explicitly labelled as sub-limit.
RISK_BANDS = (
    {"key": "critical", "label": "Critical", "colour": "#c62828",
     "min_twa": 5.0, "action": "Evacuate the area, escalate to the shift in-charge, and "
                              "send the worker for medical assessment now."},
    {"key": "warning", "label": "Warning", "colour": "#ef6c00",
     "min_twa": 1.0, "action": "Over the 1 ppm TLV-TWA. Withdraw the worker from sour "
                              "service, survey the area with a portable monitor, and "
                              "investigate the source before the next shift."},
    {"key": "elevated", "label": "Elevated", "colour": "#f9a825",
     "min_twa": 0.5, "action": "Below the limit but trending. Worth a walkdown of the "
                              "area and a look at whether the same unit keeps appearing."},
    {"key": "safe", "label": "Safe", "colour": "#2e7d32",
     "min_twa": 0.0, "action": "Within limits. File the record."},
)

_INVALID_BAND = {"key": "invalid", "label": "Unreadable", "colour": "#616161",
                 "min_twa": float("nan"),
                 "action": "The scan did not produce a defensible reading. Rescan the "
                           "badge following the on-screen hint; if it fails again the "
                           "badge goes to the lab, and the worker is treated as "
                           "unmonitored for the shift, which is itself a finding."}


def band_for(twa_ppm, ok: bool = True) -> dict:
    """Band for a TWA in ppm. ``ok=False`` or a non-finite TWA gives the invalid band."""
    if not ok or twa_ppm is None or not math.isfinite(float(twa_ppm)):
        return _INVALID_BAND
    v = float(twa_ppm)
    for b in RISK_BANDS:
        if v >= b["min_twa"]:
            return b
    return RISK_BANDS[-1]


def band_for_dose(dose_ppm_hr, shift_hours: float = 8.0, ok: bool = True) -> dict:
    """Band from a cumulative dose, by converting to TWA over the shift first."""
    if not ok or dose_ppm_hr is None or not math.isfinite(float(dose_ppm_hr)):
        return _INVALID_BAND
    h = max(float(shift_hours), 1e-6)
    return band_for(float(dose_ppm_hr) / h, ok=True)


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

def idw_grid(scans, nx: int = 44, ny: int = 44, power: float = 2.0,
             radius_m: float = 350.0, smoothing_m: float = 25.0,
             bounds: dict = None, value_key: str = "twa_ppm") -> dict:
    """Inverse-distance-weighted surface over the scan points.

    Returns a dict with the grid geometry, the interpolated values, and - importantly - a
    support layer, so the front end can distinguish "0.2 ppm, six badges within 80 m" from
    "0.2 ppm, one badge 300 m away".

    Parameters
    ----------
    power
        IDW exponent. 2.0 is the conventional choice and behaves sensibly here: it decays
        fast enough that a single high badge does not smear a red blob across the site, but
        not so fast that the surface degenerates into isolated dots at each scan.
    radius_m
        Points beyond this contribute nothing, and a cell with no point inside it is
        returned as ``None`` rather than as a number. This is the honest behaviour: with no
        badge nearby there is no evidence either way, and painting such a cell green is a
        false reassurance while painting it red is a false alarm. The front end leaves it
        uncoloured.
    smoothing_m
        Added in quadrature to each distance, which does two things. It stops the weight
        going to infinity at a scan location, and it stops the surface pretending to a
        spatial resolution finer than the GPS fix that produced the points - roughly 5-30 m
        on a phone, worse among steel structure.

    Notes
    -----
    IDW is an exact interpolator, so at a scan point the surface equals that scan. It cannot
    extrapolate above the highest observation or below the lowest, which means **this surface
    systematically under-represents a sharp local source**: a leak between two badges reads
    as the average of them, not as the peak. Treat the map as a lower bound on the spatial
    pattern, and never as a concentration field.
    """
    pts = []
    for s in scans:
        lat, lng = s.get("lat"), s.get("lng")
        v = s.get(value_key)
        if lat is None or lng is None or v is None:
            continue
        try:
            lat, lng, v = float(lat), float(lng), float(v)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lng) and math.isfinite(v)):
            continue
        pts.append((lat, lng, v))

    bb = bounds or bounds_of([(p[0], p[1]) for p in pts])
    lat0 = 0.5 * (bb["min_lat"] + bb["max_lat"])
    lng0 = 0.5 * (bb["min_lng"] + bb["max_lng"])
    glat = np.linspace(bb["min_lat"], bb["max_lat"], ny)
    glng = np.linspace(bb["min_lng"], bb["max_lng"], nx)
    out = {
        "nx": nx, "ny": ny, "bounds": bb, "power": power, "radius_m": radius_m,
        "value_key": value_key, "n_points": len(pts),
        "lat": [round(float(v), 6) for v in glat],
        "lng": [round(float(v), 6) for v in glng],
        "values": [], "support": [], "nearest_m": [],
        "note": ("Inverse-distance interpolation between badge scans. A screening aid, not "
                 "a dispersion model: it cannot exceed the highest badge it is drawn from, "
                 "and cells with no scan within the radius are returned null."),
    }
    if not pts:
        out["values"] = [[None] * nx for _ in range(ny)]
        out["support"] = [[0] * nx for _ in range(ny)]
        out["nearest_m"] = [[None] * nx for _ in range(ny)]
        out["max"] = None
        return out

    plat = np.array([p[0] for p in pts])
    plng = np.array([p[1] for p in pts])
    pval = np.array([p[2] for p in pts])
    px, py = local_xy_m(plat, plng, lat0, lng0)

    GLAT, GLNG = np.meshgrid(glat, glng, indexing="ij")
    gx, gy = local_xy_m(GLAT, GLNG, lat0, lng0)

    # (ny, nx, n) distances. Grids here are ~44x44x(<=2000) which is small enough to do
    # densely; a site with 10^5 stored scans should pre-filter by bbox and time first, which
    # is what the store's list_scans(bbox=..., since=...) is for.
    d = np.sqrt((gx[..., None] - px[None, None, :]) ** 2
                + (gy[..., None] - py[None, None, :]) ** 2)
    near = d.min(axis=2)
    inside = d <= radius_m
    w = np.where(inside, 1.0 / np.power(np.sqrt(d ** 2 + smoothing_m ** 2), power), 0.0)
    wsum = w.sum(axis=2)
    with np.errstate(invalid="ignore", divide="ignore"):
        vals = np.where(wsum > 0, (w * pval[None, None, :]).sum(axis=2) / wsum, np.nan)

    out["values"] = [[None if not math.isfinite(v) else round(float(v), 4) for v in row]
                     for row in vals]
    out["support"] = [[int(v) for v in row] for row in inside.sum(axis=2)]
    out["nearest_m"] = [[None if not math.isfinite(v) else round(float(v), 1) for v in row]
                        for row in near]
    finite = vals[np.isfinite(vals)]
    out["max"] = round(float(finite.max()), 4) if finite.size else None
    return out


def cluster_scans(scans, eps_m: float = 120.0, min_twa: float = 0.5,
                  min_points: int = 2) -> list:
    """Single-link spatial clusters of concerning scans, worst first.

    The point of clustering rather than just listing high scans is that one high badge is a
    *worker* finding - it could be that person's task, their PPE, or a badge fault - whereas
    several high badges in the same place is an *area* finding, and only the second justifies
    sending someone with a portable monitor. So the returned records carry both the count and
    the number of distinct workers: three high scans from one worker is still one worker.

    ``eps_m`` of 120 m is chosen against the plant layout rather than tuned: it is a little
    over the radius of the process units in :data:`MRPL`, so scans within the same unit group
    together while scans in adjacent units generally do not. Single-link agglomeration is
    used because with tens of points per shift it is exact, deterministic and trivially
    explainable in an audit - which matters more here than the asymptotics.
    """
    hot = []
    for s in scans:
        lat, lng, twa = s.get("lat"), s.get("lng"), s.get("twa_ppm")
        if lat is None or lng is None or twa is None:
            continue
        try:
            lat, lng, twa = float(lat), float(lng), float(twa)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(lat) and math.isfinite(lng) and math.isfinite(twa)):
            continue
        if twa >= min_twa:
            hot.append({**s, "lat": lat, "lng": lng, "twa_ppm": twa})
    n = len(hot)
    if n == 0:
        return []

    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if haversine_m(hot[i]["lat"], hot[i]["lng"],
                           hot[j]["lat"], hot[j]["lng"]) <= eps_m:
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(hot[i])

    out = []
    for members in groups.values():
        if len(members) < min_points:
            continue
        twas = [m["twa_ppm"] for m in members]
        lat = sum(m["lat"] for m in members) / len(members)
        lng = sum(m["lng"] for m in members) / len(members)
        unit, dist = MRPL.nearest_unit(lat, lng)
        spread = max(haversine_m(lat, lng, m["lat"], m["lng"]) for m in members)
        workers = sorted({str(m.get("worker_id") or "?") for m in members})
        peak = max(twas)
        out.append({
            "lat": round(lat, 6), "lng": round(lng, 6),
            "n_scans": len(members),
            "n_workers": len(workers),
            "workers": workers[:12],
            "peak_twa_ppm": round(peak, 3),
            "mean_twa_ppm": round(sum(twas) / len(twas), 3),
            "radius_m": round(max(spread, 25.0), 1),
            "band": band_for(peak)["key"],
            "unit": None if unit is None else unit.code,
            "unit_name": None if unit is None else unit.name,
            "unit_distance_m": None if unit is None else round(dist, 1),
            "sour_service": bool(unit is not None and unit.code in H2S_UNITS),
            "interpretation": _cluster_note(unit, len(workers), peak),
        })
    out.sort(key=lambda c: (-c["peak_twa_ppm"], -c["n_scans"]))
    return out


def _cluster_note(unit, n_workers: int, peak_twa: float) -> str:
    where = "an unmapped location" if unit is None else unit.name
    if unit is not None and unit.code in H2S_UNITS:
        site = (f"{where} is in sour service, so a process leak is a plausible cause and "
                "should be ruled out with a portable monitor before the next shift.")
    else:
        site = (f"{where} has no sour service in the layout, so a process leak is a poor "
                "first explanation - check whether the badges were scanned here rather "
                "than worn here, which is the common cause of a false hot spot at a kiosk "
                "or muster point.")
    who = ("Multiple workers, which points at the area rather than the person."
           if n_workers > 1 else
           "A single worker, so this may be that person's task or PPE rather than the "
           "area - confirm with a second badge before acting on the location.")
    urgency = ("Peak is above the 5 ppm STEL-equivalent band: act now. " if peak_twa >= 5.0
               else "")
    return f"{urgency}{who} {site}"


def unit_rollup(scans) -> list:
    """Per-unit exposure summary, assigning each scan to the nearest unit it falls inside.

    Scans outside every unit's radius are collected under ``OUTSIDE`` rather than being
    forced into the nearest unit, because silently attributing a roadside scan to a process
    area would put a finding on the wrong unit's record.
    """
    buckets = {}
    for s in scans:
        lat, lng = s.get("lat"), s.get("lng")
        code, name = "OUTSIDE", "Outside mapped units"
        if lat is not None and lng is not None:
            try:
                u, d = MRPL.nearest_unit(float(lat), float(lng))
            except (TypeError, ValueError):
                u, d = None, float("inf")
            if u is not None and d <= u.radius_m * 1.5:
                code, name = u.code, u.name
        b = buckets.setdefault(code, {"unit": code, "unit_name": name, "n_scans": 0,
                                      "n_invalid": 0, "workers": set(), "twas": []})
        b["n_scans"] += 1
        twa = s.get("twa_ppm")
        okflag = s.get("ok", True)
        if s.get("worker_id"):
            b["workers"].add(str(s["worker_id"]))
        try:
            twa = float(twa)
        except (TypeError, ValueError):
            twa = float("nan")
        if okflag and math.isfinite(twa):
            b["twas"].append(twa)
        else:
            b["n_invalid"] += 1

    out = []
    for b in buckets.values():
        twas = b["twas"]
        peak = max(twas) if twas else float("nan")
        rec = {
            "unit": b["unit"], "unit_name": b["unit_name"],
            "n_scans": b["n_scans"], "n_invalid": b["n_invalid"],
            "n_workers": len(b["workers"]),
            "peak_twa_ppm": None if not twas else round(peak, 3),
            "mean_twa_ppm": None if not twas else round(sum(twas) / len(twas), 3),
            "n_over_tlv": sum(1 for v in twas if v >= 1.0),
            "band": band_for(peak, ok=bool(twas))["key"],
            "sour_service": b["unit"] in H2S_UNITS,
        }
        out.append(rec)
    out.sort(key=lambda r: (-(r["peak_twa_ppm"] or -1), -r["n_scans"]))
    return out


def heatmap_payload(scans, **grid_kw) -> dict:
    """Everything the map needs in one response: points, grid, clusters, unit rollup."""
    pts = []
    for s in scans:
        band = band_for(s.get("twa_ppm"), ok=bool(s.get("ok", True)))
        pts.append({
            "id": s.get("id"),
            "worker_id": s.get("worker_id"),
            "scanned_at": s.get("scanned_at"),
            "lat": s.get("lat"), "lng": s.get("lng"),
            "accuracy_m": s.get("accuracy_m"),
            # Carried so the map can draw a generated coordinate differently from an observed
            # one. Without it the two are indistinguishable on screen, which is the one thing
            # a demonstration coordinate must never be.
            "location_mocked": bool(s.get("location_mocked")),
            "dose_ppm_hr": s.get("dose_ppm_hr"),
            "twa_ppm": s.get("twa_ppm"),
            "delta_l_star": s.get("delta_l_star"),
            "delta_e00": s.get("delta_e00"),
            "verdict": s.get("verdict"),
            "ok": bool(s.get("ok", True)),
            "band": band["key"],
            "colour": band["colour"],
            "unit": s.get("unit"),
        })
    grid = idw_grid(scans, **grid_kw)
    clusters = cluster_scans(scans)
    return {
        "points": pts,
        "grid": grid,
        "clusters": clusters,
        "units": unit_rollup(scans),
        "plant": MRPL.as_dict(),
        "bands": list(RISK_BANDS),
        "n_scans": len(pts),
        "n_located": sum(1 for p in pts if p["lat"] is not None and p["lng"] is not None),
    }
