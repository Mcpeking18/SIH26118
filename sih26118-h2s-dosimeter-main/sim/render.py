"""
Synthetic scan renderer: badge artwork -> realistic phone photograph.

Applies the degradations a real capture suffers, in the order the physics imposes them.
Order is not cosmetic - getting it wrong makes the simulation easier than reality and the
accuracy claims worthless:

    1. geometry      pose the flat badge in 3D, project to the image plane
    2. illuminate    multiply reflectance by the illuminant, IN LINEAR LIGHT
    3. shade         directional falloff and an optional specular glare blob
    4. sensor        camera gamut matrix, then partial auto white balance
    5. expose        auto-exposure to a target mean, with clipping
    6. noise         photon shot noise (signal-dependent) + read noise (fixed)
    7. encode        sRGB gamma, 8-bit quantisation, JPEG compression

Steps 2-6 must happen in linear light, because that is where light actually adds and
multiplies. Only step 7 encodes. A simulator that applies a colour cast to gamma-encoded
pixels produces a different - and gentler - distortion than a real light does, and a reader
validated against it will fail in the field.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from engine.badge_spec import BADGE, BadgeSpec
from engine.colorimetry import linear_to_srgb, srgb_to_linear
from sim.illuminants import CAMERAS, ILLUMINANTS, CameraModel, Illuminant

__all__ = ["Pose", "RenderConfig", "render_scan", "render_dataset"]

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


@dataclass
class Pose:
    """Camera pose relative to the badge, in degrees and millimetres.

    Framing is specified by ``fill_fraction`` - how much of the frame's short edge the
    badge spans - rather than by distance, and the distance is solved for. This is the
    right parameterisation because it is what the operator actually controls: the scanner
    UI draws a reticle and says "fill this". Specifying distance instead produced a badge
    only 160 px wide in a 1280x960 frame, which starved the 4.5 mm fiducials to ~24 px and
    made every synthetic scan fail for reasons that had nothing to do with the algorithm.

    Set ``distance_mm`` explicitly to override, e.g. to test an out-of-spec far shot.
    """

    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    fill_fraction: float = 0.60
    distance_mm: Optional[float] = None
    offset_x_mm: float = 0.0
    offset_y_mm: float = 0.0
    focal_mm: float = 4.2             # phone main camera
    sensor_width_mm: float = 5.6

    def resolve_distance_mm(self, spec: BadgeSpec, out_size: tuple) -> float:
        """Distance that makes the badge span ``fill_fraction`` of the short edge."""
        if self.distance_mm is not None:
            return float(self.distance_mm)
        w, h = out_size
        fx = self.focal_mm * w / self.sensor_width_mm
        target_px = max(self.fill_fraction * min(w, h), 8.0)
        return float(spec.head_mm * fx / target_px)


@dataclass
class RenderConfig:
    """Everything about one synthetic capture."""

    illuminant: Illuminant = field(default_factory=lambda: ILLUMINANTS["d65"])
    camera: CameraModel = field(default_factory=lambda: CAMERAS["reference"])
    pose: Pose = field(default_factory=Pose)
    out_size: tuple = (1280, 960)
    background_srgb: tuple = (70, 74, 78)     # dark industrial background
    #: Target mean linear level for auto-exposure. 0.28 is roughly where phone AE lands.
    ae_target: float = 0.28
    #: Directional shading strength: 0 = flat, 1 = strong gradient across the badge.
    shading: float = 0.25
    #: Specular glare: (strength, x_frac, y_frac, radius_frac) or None.
    glare: Optional[tuple] = None
    seed: Optional[int] = 0
    apply_jpeg: bool = True


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def _rotation(yaw: float, pitch: float, roll: float) -> np.ndarray:
    y, p, r = np.radians([yaw, pitch, roll])
    Rz = np.array([[np.cos(r), -np.sin(r), 0], [np.sin(r), np.cos(r), 0], [0, 0, 1]])
    Ry = np.array([[np.cos(y), 0, np.sin(y)], [0, 1, 0], [-np.sin(y), 0, np.cos(y)]])
    Rx = np.array([[1, 0, 0], [0, np.cos(p), -np.sin(p)], [0, np.sin(p), np.cos(p)]])
    return Rz @ Ry @ Rx


def _project(spec: BadgeSpec, pose: Pose, out_size: tuple) -> np.ndarray:
    """Homography from badge artwork pixels to output image pixels.

    Built from an actual pinhole projection of the badge's four physical corners rather
    than a random corner jitter, so the perspective distortion is consistent with a real
    lens at a real distance - which is what makes the reprojection-error gate meaningful.
    """
    w, h = out_size
    fx = fy = pose.focal_mm * w / pose.sensor_width_mm
    cx, cy = w / 2.0, h / 2.0
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float64)

    half = spec.head_mm / 2.0
    corners_mm = np.array([[-half, -half, 0], [half, -half, 0],
                           [half, half, 0], [-half, half, 0]], dtype=np.float64)

    R = _rotation(pose.yaw_deg, pose.pitch_deg, pose.roll_deg)
    dist = pose.resolve_distance_mm(spec, out_size)
    t = np.array([pose.offset_x_mm, pose.offset_y_mm, dist])
    cam = (R @ corners_mm.T).T + t
    if np.any(cam[:, 2] <= 1.0):
        raise ValueError("badge is at or behind the camera; increase distance_mm")

    proj = (K @ cam.T).T
    dst = (proj[:, :2] / proj[:, 2:3]).astype(np.float64)

    n = spec.canonical_px
    src = np.array([[0, 0], [n, 0], [n, n], [0, n]], dtype=np.float64)
    H, _ = cv2.findHomography(src, dst, method=0)
    return H


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_scan(artwork_bgr: np.ndarray, config: RenderConfig = None,
                spec: BadgeSpec = BADGE) -> np.ndarray:
    """Render one synthetic photograph of a badge. Returns 8-bit BGR."""
    cfg = config or RenderConfig()
    rng = np.random.default_rng(cfg.seed)
    w, h = cfg.out_size

    n = spec.canonical_px
    if artwork_bgr.shape[0] != artwork_bgr.shape[1]:
        raise ValueError("badge artwork must be square")
    if artwork_bgr.shape[0] != n:
        artwork_bgr = cv2.resize(artwork_bgr, (n, n), interpolation=cv2.INTER_AREA)

    # ---- 1. geometry -----------------------------------------------------
    H = _project(spec, cfg.pose, cfg.out_size)
    bg = np.array(cfg.background_srgb, dtype=np.uint8)[::-1]     # RGB -> BGR
    scene = np.empty((h, w, 3), dtype=np.uint8)
    scene[:] = bg
    warped = cv2.warpPerspective(artwork_bgr, H, (w, h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_TRANSPARENT, dst=scene.copy())
    scene = warped

    # Everything below is linear-light physics. Decode once, here.
    rgb = srgb_to_linear(scene[:, :, ::-1].astype(np.float64), max_value=255.0)

    # ---- 2. illuminant ---------------------------------------------------
    rgb *= cfg.illuminant.linear_rgb_gain[None, None, :]

    # ---- 3. shading and glare -------------------------------------------
    if cfg.shading > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        ramp = (xx / max(w - 1, 1)) * 0.6 + (yy / max(h - 1, 1)) * 0.4
        rgb *= (1.0 - cfg.shading * ramp)[:, :, None]

    if cfg.glare:
        strength, gx, gy, grad = cfg.glare
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        d2 = ((xx - gx * w) ** 2 + (yy - gy * h) ** 2) / max((grad * min(w, h)) ** 2, 1.0)
        # Additive, not multiplicative: a specular reflection adds the light source's own
        # colour on top of the surface, it does not scale the surface reflectance.
        rgb += strength * np.exp(-d2)[:, :, None] * cfg.illuminant.linear_rgb_gain[None, None, :]

    if cfg.camera.vignette > 0:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
        rgb *= (1.0 - cfg.camera.vignette * np.clip(r, 0, 1.4) ** 2)[:, :, None]

    # ---- 4. sensor gamut + partial AWB ----------------------------------
    cam = cfg.camera
    rgb = rgb @ np.asarray(cam.gamut_matrix, dtype=np.float64).T

    # AWB estimates the cast from the scene and partially removes it. Modelled as a
    # grey-world estimate so the residual error is realistic: grey-world is biased
    # whenever the scene is not colour-neutral, and a badge on a dark background is not.
    mean = rgb.reshape(-1, 3).mean(axis=0)
    mean = np.maximum(mean, 1e-6)
    awb = mean.mean() / mean
    rgb *= (1.0 - cam.awb_strength + cam.awb_strength * awb)[None, None, :]

    # ---- 5. auto exposure ------------------------------------------------
    # Centre-weighted, not frame-average. Phone AE is centre-weighted, and the scanner UI
    # puts the badge under a reticle in the middle of the frame. Metering the whole frame
    # instead lets the dark industrial background dominate: AE then pushes gain up to
    # reach the target mean and clips the badge to pure white, which is what happened
    # before this was fixed - every synthetic scan failed the glare gate at 100% clipped.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    rr = (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    weight = np.exp(-rr / (2.0 * 0.35 ** 2))
    luma = rgb @ _LUMA
    cur = float((luma * weight).sum() / weight.sum())
    if cur > 1e-9:
        rgb *= np.clip(cfg.ae_target / cur, 0.02, 50.0)

    # ---- 6. noise --------------------------------------------------------
    # Applied in DN because that is where sensor noise is specified. Shot noise scales
    # with sqrt(signal); read noise is constant and is what destroys the low-lux case.
    dn = np.clip(rgb, 0.0, None) * 255.0
    if cam.shot_noise_k > 0:
        dn += rng.normal(0.0, 1.0, dn.shape) * cam.shot_noise_k * np.sqrt(np.maximum(dn, 0.0))
    if cam.read_noise > 0:
        dn += rng.normal(0.0, cam.read_noise, dn.shape)

    # Low light means fewer photons: scale noise up as lux falls below a nominal 500 lux.
    lux_penalty = np.sqrt(max(500.0 / max(cfg.illuminant.lux, 1.0), 1.0))
    if lux_penalty > 1.0:
        extra = (lux_penalty - 1.0) * (cam.read_noise + 0.5)
        dn += rng.normal(0.0, extra, dn.shape)

    # ---- 7. encode -------------------------------------------------------
    lin = np.clip(dn / 255.0, 0.0, 1.0)
    out_rgb = np.clip(np.round(linear_to_srgb(lin, max_value=1.0) * 255.0), 0, 255)
    out = out_rgb.astype(np.uint8)[:, :, ::-1]                  # RGB -> BGR

    if cfg.apply_jpeg and cam.jpeg_quality < 100:
        ok, buf = cv2.imencode(".jpg", out,
                               [int(cv2.IMWRITE_JPEG_QUALITY), int(cam.jpeg_quality)])
        if ok:
            out = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    return out


# ---------------------------------------------------------------------------
# Dataset generation
# ---------------------------------------------------------------------------

def render_dataset(doses, illuminant_keys=None, camera_keys=None, poses=None,
                   spec: BadgeSpec = BADGE, seed: int = 0, model=None) -> list:
    """Cartesian sweep of dose x illuminant x camera x pose.

    Returns a list of ``{"image", "dose_ppm_hr", "expected_delta_e00", "illuminant",
    "camera", "pose", ...}`` records - the input to the invariance harness.
    """
    from badge.make_badge import render_badge
    from engine.dosimetry import ReactionModel

    model = model or ReactionModel()
    illuminant_keys = illuminant_keys or ["d65", "fluorescent_4000", "hps",
                                          "incandescent_2856", "metal_halide"]
    camera_keys = camera_keys or ["reference", "midrange_a", "budget"]
    poses = poses or [
        Pose(),
        Pose(yaw_deg=18.0, pitch_deg=-12.0, roll_deg=7.0, fill_fraction=0.70),
        Pose(yaw_deg=-25.0, pitch_deg=15.0, fill_fraction=0.48, offset_x_mm=4.0),
    ]

    # Artwork is expensive relative to rendering, so cache one per dose.
    artwork = {d: render_badge(spec, dpi=spec.px_per_mm * 25.4, dose_ppm_hr=d, model=model)
               for d in doses}

    records, k = [], 0
    for dose in doses:
        for ik in illuminant_keys:
            for ck in camera_keys:
                for pi, pose in enumerate(poses):
                    cfg = RenderConfig(
                        illuminant=ILLUMINANTS[ik], camera=CAMERAS[ck], pose=pose,
                        seed=seed + k,
                        glare=None if k % 7 else (0.25, 0.62, 0.38, 0.10),
                        shading=0.18 + 0.12 * (k % 3),
                    )
                    k += 1
                    records.append({
                        "image": render_scan(artwork[dose], cfg, spec),
                        "dose_ppm_hr": float(dose),
                        "expected_delta_l_star": float(model.delta_l(dose)),
                        "expected_delta_e00": float(model.delta_e(dose)),
                        "illuminant": ik,
                        "camera": ck,
                        "pose_index": pi,
                        "config": cfg,
                    })
    return records
