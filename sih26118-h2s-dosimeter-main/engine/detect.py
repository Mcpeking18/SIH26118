"""
Fiducial detection and geometric rectification.

Turns an arbitrary hand-held photograph of the badge into the canonical
600 x 600 px fronto-parallel plane defined by :mod:`engine.badge_spec`, so every
downstream ROI is at a fixed, known pixel location.

Handles the OpenCV ArUco API break: the module was reorganised in 4.7 (functional
``detectMarkers`` -> ``ArucoDetector`` class) and again lightly in 5.x. Hackathon
laptops will have anything from 4.5 to 5.0, so the shim below probes at import time
rather than pinning a version.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from .badge_spec import BADGE, BadgeSpec

__all__ = [
    "DetectionResult",
    "aruco_dictionary",
    "generate_marker",
    "detect_markers",
    "solve_homography",
    "warp_to_canonical",
    "rectify",
    "draw_detection_overlay",
]


# ---------------------------------------------------------------------------
# OpenCV ArUco compatibility shim
# ---------------------------------------------------------------------------

_ARUCO = getattr(cv2, "aruco", None)
if _ARUCO is None:  # pragma: no cover
    raise ImportError(
        "cv2.aruco is missing. Install the contrib build:\n"
        "    pip uninstall -y opencv-python\n"
        "    pip install opencv-contrib-python"
    )

#: True when the modern class-based detector is available (OpenCV >= 4.7).
_MODERN_API = hasattr(_ARUCO, "ArucoDetector")


def aruco_dictionary(name: str = None):
    """Fetch a predefined ArUco dictionary by name across OpenCV versions."""
    name = name or BADGE.aruco_dict
    if not hasattr(_ARUCO, name):
        raise ValueError(f"cv2.aruco has no dictionary {name!r}")
    key = getattr(_ARUCO, name)
    if hasattr(_ARUCO, "getPredefinedDictionary"):
        return _ARUCO.getPredefinedDictionary(key)
    return _ARUCO.Dictionary_get(key)          # OpenCV <= 4.6


def _detector_params():
    if hasattr(_ARUCO, "DetectorParameters"):
        try:
            return _ARUCO.DetectorParameters()
        except TypeError:                       # 4.6 exposed a factory instead
            return _ARUCO.DetectorParameters_create()
    return _ARUCO.DetectorParameters_create()


def _tuned_params():
    """Detector parameters tuned for small printed markers in industrial lighting.

    Two deliberate departures from the defaults:

    * ``cornerRefinementMethod = CORNER_REFINE_SUBPIX`` - marker corners drive the
      homography, and a half-pixel corner error propagates into the pad ROI position.
      Sub-pixel refinement is cheap here (four small markers) and materially improves
      the warp.
    * a wider ``adaptiveThreshWinSize`` sweep - a 4.5 mm marker photographed at arm's
      length is only ~25 px across, and the default window range misses it when a
      sodium lamp puts a strong brightness gradient across the badge.
    """
    p = _detector_params()
    try:
        p.cornerRefinementMethod = _ARUCO.CORNER_REFINE_SUBPIX
        p.cornerRefinementWinSize = 5
        p.cornerRefinementMaxIterations = 50
        p.cornerRefinementMinAccuracy = 0.01
        p.adaptiveThreshWinSizeMin = 3
        p.adaptiveThreshWinSizeMax = 43
        p.adaptiveThreshWinSizeStep = 4
        p.minMarkerPerimeterRate = 0.01     # allow small/far markers
        p.maxMarkerPerimeterRate = 4.0
        p.polygonalApproxAccuracyRate = 0.05
    except AttributeError:                  # pragma: no cover - very old builds
        pass
    return p


def generate_marker(marker_id: int, side_px: int, dictionary=None) -> np.ndarray:
    """Render one ArUco marker as a uint8 grayscale image (for the print artwork)."""
    d = dictionary if dictionary is not None else aruco_dictionary()
    if hasattr(_ARUCO, "generateImageMarker"):
        return _ARUCO.generateImageMarker(d, marker_id, side_px)
    return _ARUCO.drawMarker(d, marker_id, side_px)      # OpenCV <= 4.6


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

@dataclass
class DetectionResult:
    """Outcome of locating the badge in one frame."""

    found_ids: tuple = ()
    #: id -> (4, 2) outer corner pixels in the source image, TL/TR/BR/BL order.
    corners: dict = field(default_factory=dict)
    homography: Optional[np.ndarray] = None
    #: RMS reprojection error of the marker corners, expressed in millimetres on
    #: the badge. This is the honest measure of geometric trust.
    reproj_rmse_mm: float = float("nan")
    warped: Optional[np.ndarray] = None
    ok: bool = False
    reason: str = ""

    @property
    def n_markers(self) -> int:
        return len(self.found_ids)


def detect_markers(image: np.ndarray, spec: BadgeSpec = BADGE) -> dict:
    """Locate the badge's ArUco markers. Returns ``{id: (4,2) float64 corners}``.

    Only IDs declared in ``spec.marker_ids`` are kept, so an unrelated marker
    elsewhere in the frame (a wall placard, another worker's badge in the background)
    cannot corrupt the homography.
    """
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    dictionary = aruco_dictionary(spec.aruco_dict)
    params = _tuned_params()

    if _MODERN_API:
        detector = _ARUCO.ArucoDetector(dictionary, params)
        corners, ids, _ = detector.detectMarkers(gray)
    else:                                       # pragma: no cover
        corners, ids, _ = _ARUCO.detectMarkers(gray, dictionary, parameters=params)

    out = {}
    if ids is None:
        return out
    wanted = set(int(i) for i in spec.marker_ids)
    for c, i in zip(corners, ids.flatten()):
        i = int(i)
        if i in wanted and i not in out:        # first detection of each id wins
            out[i] = np.asarray(c, dtype=np.float64).reshape(4, 2)
    return out


# ---------------------------------------------------------------------------
# Homography
# ---------------------------------------------------------------------------

def solve_homography(found: dict, spec: BadgeSpec = BADGE, min_markers: int = 2):
    """Least-squares homography from source pixels to the canonical plane.

    Every corner of every detected marker contributes a correspondence, so four
    markers give 16 point pairs for 8 unknowns - a comfortably overdetermined fit whose
    residual is a usable quality metric.

    Why ``min_markers=2``: a single 4.5 mm marker does yield four points and a formally
    valid homography, but the badge head is ~7x the marker width, so the pad ROI sits far
    outside the convex hull of the correspondences. Small corner noise then levers the
    pad centre several millimetres off. Two diagonal markers span the head and remove
    that extrapolation. One marker is accepted only with an explicit override.

    Returns
    -------
    (H, rmse_mm) or (None, nan)
    """
    if len(found) < min_markers:
        return None, float("nan")

    dst_all_mm = spec.marker_outer_corners_mm()          # (4, 4, 2) indexed by position
    id_to_pos = {int(mid): pos for pos, mid in enumerate(spec.marker_ids)}

    src, dst = [], []
    for mid, quad in found.items():
        pos = id_to_pos[int(mid)]
        src.append(quad)
        dst.append(spec.mm_to_px(dst_all_mm[pos]))
    src = np.concatenate(src, axis=0).astype(np.float64)
    dst = np.concatenate(dst, axis=0).astype(np.float64)

    # Plain least squares (method=0): the correspondences are already filtered by
    # marker ID, so there are no outliers for RANSAC to reject, and RANSAC would
    # discard good points and inflate the residual.
    H, _ = cv2.findHomography(src, dst, method=0)
    if H is None:
        return None, float("nan")

    proj = cv2.perspectiveTransform(src.reshape(-1, 1, 2), H).reshape(-1, 2)
    rmse_px = float(np.sqrt(np.mean(np.sum((proj - dst) ** 2, axis=1))))
    return H, rmse_px / spec.px_per_mm


def warp_to_canonical(image: np.ndarray, H: np.ndarray, spec: BadgeSpec = BADGE) -> np.ndarray:
    """Warp the source frame onto the canonical badge plane.

    ``INTER_AREA`` is used when downscaling and ``INTER_LINEAR`` when upscaling.
    This matters colorimetrically: ``INTER_CUBIC`` has negative lobes that overshoot at
    the hard pad/well boundary, injecting a bright halo into the outer pad pixels and
    biasing the sampled mean. Never "upgrade" this to cubic or Lanczos.
    """
    n = spec.canonical_px
    h, w = image.shape[:2]
    src_span = max(h, w)
    flags = cv2.INTER_AREA if src_span > n * 1.2 else cv2.INTER_LINEAR
    return cv2.warpPerspective(
        image, H, (n, n), flags=flags, borderMode=cv2.BORDER_CONSTANT, borderValue=0
    )


def rectify(
    image: np.ndarray,
    spec: BadgeSpec = BADGE,
    min_markers: int = 2,
    max_reproj_mm: float = 0.35,
) -> DetectionResult:
    """Full geometry stage: detect -> homography -> warp, with quality gating.

    ``max_reproj_mm`` defaults to 0.35 mm, about 3% of the 10 mm pad. Beyond that the
    pad ROI can start clipping the well wall, so the scan is rejected and the operator
    is asked to retake rather than being handed a confidently wrong dose.
    """
    res = DetectionResult()
    found = detect_markers(image, spec)
    res.found_ids = tuple(sorted(found))
    res.corners = found

    if len(found) < min_markers:
        res.reason = (
            f"found {len(found)} of {len(spec.marker_ids)} fiducials, need {min_markers}"
            " - move closer, wipe the badge, or add light"
        )
        return res

    H, rmse_mm = solve_homography(found, spec, min_markers)
    if H is None:
        res.reason = "degenerate marker geometry, homography could not be solved"
        return res

    res.homography = H
    res.reproj_rmse_mm = rmse_mm

    if not np.isfinite(rmse_mm) or rmse_mm > max_reproj_mm:
        res.reason = (
            f"geometry unstable: {rmse_mm:.3f} mm reprojection RMSE "
            f"exceeds {max_reproj_mm:.2f} mm - hold the camera steadier / flatter"
        )
        return res

    res.warped = warp_to_canonical(image, H, spec)
    res.ok = True
    res.reason = "ok"
    return res


# ---------------------------------------------------------------------------
# Debug overlay
# ---------------------------------------------------------------------------

def draw_detection_overlay(image: np.ndarray, res: DetectionResult,
                           spec: BadgeSpec = BADGE) -> np.ndarray:
    """Annotate the source frame with detected markers and the projected badge outline."""
    vis = image.copy()
    if vis.ndim == 2:
        vis = cv2.cvtColor(vis, cv2.COLOR_GRAY2BGR)

    for mid, quad in res.corners.items():
        pts = quad.astype(np.int32).reshape(-1, 1, 2)
        cv2.polylines(vis, [pts], True, (0, 255, 0), 2)
        cv2.putText(vis, str(mid), tuple(quad[0].astype(int)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

    if res.homography is not None:
        Hinv = np.linalg.inv(res.homography)
        n = spec.canonical_px
        box = np.array([[0, 0], [n, 0], [n, n], [0, n]], dtype=np.float64).reshape(-1, 1, 2)
        outline = cv2.perspectiveTransform(box, Hinv).astype(np.int32)
        cv2.polylines(vis, [outline], True, (0, 200, 255), 2)

        c = spec.mm_to_px(np.array([spec.centre_mm], dtype=np.float64)).reshape(-1, 1, 2)
        ctr = cv2.perspectiveTransform(c, Hinv).reshape(2).astype(int)
        cv2.drawMarker(vis, tuple(ctr), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)

    label = (f"{res.n_markers} markers  rmse={res.reproj_rmse_mm:.3f}mm"
             if res.n_markers else "no fiducials")
    cv2.putText(vis, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (0, 255, 0) if res.ok else (0, 0, 255), 2)
    return vis
