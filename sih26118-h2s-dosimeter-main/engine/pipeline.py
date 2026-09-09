"""
End-to-end scan pipeline: photograph in, exposure verdict out.

Chains the four stages, each of which can veto:

    rectify   (engine.detect)     find fiducials, warp to the canonical plane
    sample    (engine.roi)        average pad and reference patches in linear light
    normalize (engine.normalize)  fit a CCM from the patches, correct the pad, measure it
    assess    (engine.dosimetry)  -dL* -> dose -> TWA -> verdict

Design rule for the whole module: **fail loudly, never guess.** A safety instrument that
returns a plausible-looking number from a bad photograph is worse than one that says
"retake". Every stage therefore returns a machine-readable failure reason and an operator
instruction phrased as an action ("move closer", "tilt away from the light"), and
:class:`ScanResult.ok` is only true when all four stages passed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional

import cv2
import numpy as np

from .badge_spec import BADGE, BadgeSpec
from .detect import DetectionResult, draw_detection_overlay, rectify
from .colorimetry import CHANNEL_BALANCE_REJECT, CHANNEL_BALANCE_WARN
from .dosimetry import (
    ACGIH_OSHA_NIOSH,
    CHROMA_LIMIT_FLOOR,
    CHROMA_LIMIT_SLOPE,
    CalibrationModel,
    DoseAssessment,
    ExposureLimits,
    SYNTHETIC_CALIBRATION,
    Verdict,
    assess_scan,
)
from .normalize import NormalizationResult, normalize_badge
from .roi import BadgeSamples, draw_roi_overlay, sample_badge

__all__ = ["ScanResult", "scan_image", "scan_file", "ScanConfig"]


@dataclass
class ScanConfig:
    """Everything tunable about one scan, in one object.

    Bundled deliberately: these knobs must match between the calibration run, the test
    harness and the field reader, and passing eight loose keyword arguments through four
    call sites is how they silently diverge.
    """

    spec: BadgeSpec = BADGE
    calibration: CalibrationModel = SYNTHETIC_CALIBRATION
    limits: ExposureLimits = ACGIH_OSHA_NIOSH

    # geometry
    min_markers: int = 2
    max_reproj_mm: float = 0.35

    # sampling
    trim: float = 0.20
    max_clip_fraction: float = 0.15
    max_pad_cv_percent: float = 25.0

    # colour correction
    ccm_mode: str = "root6"
    ridge: float = 1e-4
    baseline_mode: str = "onbadge"
    #: Locus-weighted leave-one-out residual, in dE00, above which the scan carries a
    #: *warning*. Not a rejection: measured to discard better-than-average scans without ever
    #: catching the worst one. See ``warn_locus_residual`` in :func:`engine.normalize.normalize_badge`.
    warn_locus_residual: float = 2.0
    #: Unweighted mean residual, in dE00, above which the scan carries a *warning*. Also not
    #: a rejection - it orders the failure cases backwards, see ``warn_loo_residual``. The
    #: only colour rejection left is structural: the on-badge baseline must survive.
    warn_loo_residual: float = 8.0
    reference_srgb: Optional[np.ndarray] = None

    #: Integrity check on the *badge*, in L*a*b* units: how far off the PbS reaction path the
    #: pad may sit before it is flagged SUSPECT. Not a photograph-quality gate. The limit
    #: scales with how far the pad has darkened, because a contaminated pad's off-path
    #: displacement grows with dose while the camera's chroma error does not - see
    #: :func:`engine.dosimetry.chroma_limit`, which also documents what this check cannot
    #: catch.
    chroma_limit_floor: float = CHROMA_LIMIT_FLOOR
    chroma_limit_slope: float = CHROMA_LIMIT_SLOPE

    #: Spatial illumination model. See :data:`engine.normalize.FLAT_FIELD_MODES`. Switch to
    #: ``'rgb'`` where lighting is genuinely mixed (sodium lamp plus daylight), ``'none'``
    #: only to measure what the correction is worth.
    flat_field: str = "luma"
    max_gradient_percent: float = 35.0

    #: Narrow-band illuminant limits, checked on the raw patch means before any fitting.
    #: A refinery at night is lit by sodium lamps; low-pressure sodium is near
    #: monochromatic. ``warn`` fires at 0.30 and tells the operator to switch the torch on;
    #: the rejection tier ships off, because measurement says balance does not predict dose
    #: error. See :func:`engine.colorimetry.narrowband_check`.
    warn_channel_balance: float = CHANNEL_BALANCE_WARN
    reject_channel_balance: float = CHANNEL_BALANCE_REJECT

    # dosimetry
    shift_hours: float = 8.0
    temp_c: Optional[float] = None
    rh_fraction: Optional[float] = None

    #: Longest image dimension the pipeline will work at. Full 12 MP phone frames are
    #: downscaled first: ArUco detection cost scales with pixel count, and detection
    #: accuracy does not improve past the point where a 4.5 mm marker spans ~60 px.
    max_side_px: int = 2000


@dataclass
class ScanResult:
    """Complete, auditable record of one scan."""

    ok: bool = False
    stage_failed: str = ""
    reason: str = ""
    operator_hint: str = ""

    detection: Optional[DetectionResult] = None
    samples: Optional[BadgeSamples] = None
    normalization: Optional[NormalizationResult] = None
    assessment: Optional[DoseAssessment] = None

    warnings: list = field(default_factory=list)
    timings_ms: dict = field(default_factory=dict)
    scale_applied: float = 1.0

    # ---- convenience accessors used by the API and the UI ----------------

    @property
    def verdict(self) -> Verdict:
        return self.assessment.verdict if self.assessment else Verdict.INVALID

    @property
    def delta_l_star(self) -> float:
        """The dose observable: how much lightness the pad lost against its baseline."""
        return self.normalization.delta_l_star if self.normalization else float("nan")

    @property
    def delta_e00(self) -> float:
        """Conventional colorimetric difference. Recorded, not used for the dose."""
        return self.normalization.delta_e00 if self.normalization else float("nan")

    @property
    def chroma_residual(self) -> float:
        """Off-locus chroma displacement - the badge-integrity figure."""
        return self.normalization.chroma_residual if self.normalization else float("nan")

    @property
    def dose_ppm_hr(self) -> float:
        return self.assessment.dose_ppm_hr if self.assessment else float("nan")

    @property
    def twa_ppm(self) -> float:
        return self.assessment.twa_ppm if self.assessment else float("nan")

    def summary(self) -> str:
        if not self.ok:
            return f"INVALID [{self.stage_failed}] {self.reason}"
        a = self.assessment
        return (
            f"{a.verdict.value}: -dL* {self.delta_l_star:.2f} (dE00 {self.delta_e00:.2f}) -> "
            f"{a.dose_ppm_hr:.2f} ppm*hr -> TWA {a.twa_ppm:.3f} ppm "
            f"over {a.shift_hours:g} h "
            f"[{self.normalization.mode}, loo {self.normalization.loo_residual_mean:.2f} dE, "
            f"chroma {self.chroma_residual:.2f}/{a.chroma_residual_limit:.2f}, "
            f"balance {self.normalization.channel_balance:.2f}, "
            f"geom {self.detection.reproj_rmse_mm:.3f} mm]"
        )

    def as_dict(self) -> dict:
        """JSON-serialisable record - what the scanner uploads and the DB stores.

        Deliberately includes the *quality* fields (reprojection error, LOO residual,
        CCM mode, warnings) alongside the dose. An HSE record that stores only the number
        cannot be audited later, and an occupational-exposure figure that cannot be
        audited is not defensible in front of a regulator.
        """
        out = {
            "ok": self.ok,
            "stage_failed": self.stage_failed,
            "reason": self.reason,
            "operator_hint": self.operator_hint,
            "warnings": list(self.warnings),
            "timings_ms": {k: round(v, 2) for k, v in self.timings_ms.items()},
            "scale_applied": round(self.scale_applied, 4),
        }
        if self.detection is not None:
            out["geometry"] = {
                "found_ids": list(self.detection.found_ids),
                "n_markers": self.detection.n_markers,
                "reproj_rmse_mm": (None if not np.isfinite(self.detection.reproj_rmse_mm)
                                   else round(self.detection.reproj_rmse_mm, 4)),
            }
        if self.normalization is not None:
            n = self.normalization
            def r(v, nd=4):
                return None if v is None or not np.isfinite(v) else round(float(v), nd)
            out["colour"] = {
                "ccm_mode": n.mode,
                "delta_l_star": r(n.delta_l_star),
                "locus_projection": r(n.locus_projection),
                "chroma_residual": r(n.chroma_residual, 3),
                "delta_e00": r(n.delta_e00),
                "baseline_source": n.baseline_source,
                "loo_residual_mean": r(n.loo_residual_mean),
                "loo_residual_max": r(n.loo_residual_max),
                "locus_residual": r(n.locus_residual),
                "locus_l_bias": r(n.locus_l_bias),
                "fit_residual_mean": r(n.fit_residual_mean),
                "condition_number": r(n.condition_number, 2),
                "flat_field_mode": n.flat_field_mode,
                "flat_field_source": n.flat_field_source,
                "gradient_percent": round(n.gradient_percent, 2),
                "channel_balance": r(n.channel_balance, 4),
                "light_quality": n.light_quality,
                "n_patches_used": len(n.used_patches),
                "pad_lab": (None if n.pad_lab is None
                            else [round(float(v), 3) for v in np.ravel(n.pad_lab)]),
                "baseline_lab": (None if n.baseline_lab is None
                                 else [round(float(v), 3) for v in np.ravel(n.baseline_lab)]),
            }
        if self.samples is not None and self.samples.pad is not None:
            out["pad_quality"] = {
                "clip_fraction": round(self.samples.pad.clip_fraction, 4),
                "black_fraction": round(self.samples.pad.black_fraction, 4),
                "cv_percent": (None if not np.isfinite(self.samples.pad.cv_percent)
                               else round(self.samples.pad.cv_percent, 2)),
                "n_pixels": self.samples.pad.n_pixels,
            }
        if self.assessment is not None:
            out["exposure"] = self.assessment.as_dict()
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _downscale(image: np.ndarray, max_side: int):
    """Shrink the frame to ``max_side`` on its long edge, returning (image, scale).

    ``INTER_AREA`` because it is a proper box filter: it averages the pixels being
    merged, which is the photometrically correct thing to do when reducing. Nearest or
    linear resampling would alias the printed patch edges into the patch interiors and
    shift the sampled colours.
    """
    h, w = image.shape[:2]
    long_side = max(h, w)
    if long_side <= max_side:
        return image, 1.0
    s = max_side / float(long_side)
    return cv2.resize(image, (int(round(w * s)), int(round(h * s))),
                      interpolation=cv2.INTER_AREA), s


_HINTS = {
    "detect": "Fill the frame with the badge, wipe the window clean, and add light.",
    "sample": "Rectification looks wrong - hold the badge flat and square to the camera.",
    "normalize": "Light is too uneven or too coloured - step out of direct glare and retake.",
    "assess": "Reading is outside the calibrated range - log the badge for lab analysis.",
}

#: More specific hints, keyed by a substring of the stage's reason. A generic "retake" is
#: useless under a sodium lamp, where the operator's real options are the torch and their own
#: shadow; the reason strings already know which failure occurred, so use them.
_HINT_OVERRIDES = (
    ("no signal in one colour channel",
     "This light is a sodium lamp - it has only one colour in it. Switch the torch on and "
     "put your body between the badge and the lamp so the torch is what lights it."),
    ("reference patches the reading is measured against are unusable",
     "The reference patches are blown out. Shade the badge from the lamp with your body and "
     "let the torch light it, then retake."),
    ("too narrow-band",
     "Switch the torch on - under a sodium lamp it has to be the main light source."),
)

#: Which field of :class:`~engine.normalize.NormalizationResult` supplies each calibration
#: observable. The mapping is explicit rather than a name-mangling convention so that a
#: calibration naming an observable this pipeline cannot produce fails loudly at the call
#: site instead of quietly reading the wrong attribute.
_OBSERVABLE_FIELDS = {
    "delta_l": "delta_l_star",
    "projection": "locus_projection",
    "delta_e00": "delta_e00",
}


def _observable_value(norm, name: str) -> float:
    return float(getattr(norm, _OBSERVABLE_FIELDS[name]))


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def scan_image(image: np.ndarray, config: ScanConfig = None) -> ScanResult:
    """Run the full pipeline on one BGR frame.

    Parameters
    ----------
    image
        8-bit BGR, as returned by ``cv2.imread`` / a camera capture. Must be 8-bit:
        the colorimetry decodes with ``max_value=255``, so handing it a float or 16-bit
        array would silently misread every colour.
    config
        See :class:`ScanConfig`.
    """
    cfg = config or ScanConfig()
    res = ScanResult()

    if image is None or image.size == 0:
        res.stage_failed, res.reason = "input", "empty image"
        return res
    if image.dtype != np.uint8:
        res.stage_failed = "input"
        res.reason = (
            f"expected 8-bit image, got {image.dtype} - the colorimetry assumes a "
            "0..255 sRGB encoding and would misread any other range"
        )
        return res
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        res.warnings.append(
            "input was grayscale; colour correction is meaningless on a mono frame"
        )

    work, res.scale_applied = _downscale(image, cfg.max_side_px)

    # ---- 1. geometry -----------------------------------------------------
    t0 = time.perf_counter()
    det = rectify(work, cfg.spec, cfg.min_markers, cfg.max_reproj_mm)
    res.timings_ms["rectify"] = (time.perf_counter() - t0) * 1e3
    res.detection = det
    if not det.ok:
        res.stage_failed, res.reason = "detect", det.reason
        res.operator_hint = _HINTS["detect"]
        return res

    # ---- 2. sampling -----------------------------------------------------
    t0 = time.perf_counter()
    samples = sample_badge(det.warped, cfg.spec, cfg.trim,
                           cfg.max_clip_fraction, cfg.max_pad_cv_percent)
    res.timings_ms["sample"] = (time.perf_counter() - t0) * 1e3
    res.samples = samples
    res.warnings.extend(samples.warnings)
    if not samples.ok:
        res.stage_failed = "sample"
        res.reason = "; ".join(samples.warnings) or "sampling integrity check failed"
        res.operator_hint = _HINTS["sample"]
        return res

    # ---- 3. colour normalisation ----------------------------------------
    t0 = time.perf_counter()
    norm = normalize_badge(
        samples, cfg.spec, cfg.reference_srgb, cfg.ccm_mode,
        cfg.ridge, cfg.baseline_mode, cfg.warn_loo_residual,
        cfg.flat_field, cfg.max_gradient_percent, cfg.warn_locus_residual,
        cfg.warn_channel_balance, cfg.reject_channel_balance,
    )
    res.timings_ms["normalize"] = (time.perf_counter() - t0) * 1e3
    res.normalization = norm
    res.warnings.extend(norm.warnings)
    if not norm.ok:
        res.stage_failed, res.reason = "normalize", norm.reason
        res.operator_hint = _HINTS["normalize"]
        for needle, hint in _HINT_OVERRIDES:
            if needle in norm.reason:
                res.operator_hint = hint
                break
        return res

    # ---- 4. dosimetry ----------------------------------------------------
    t0 = time.perf_counter()
    try:
        value = _observable_value(norm, cfg.calibration.observable)
    except KeyError:
        res.stage_failed = "assess"
        res.reason = (
            f"calibration is in terms of {cfg.calibration.observable!r}, which this "
            f"pipeline cannot supply; expected one of {sorted(_OBSERVABLE_FIELDS)}"
        )
        return res
    assessment = assess_scan(
        value, cfg.shift_hours, cfg.calibration,
        cfg.limits, cfg.temp_c, cfg.rh_fraction,
        delta_e00=norm.delta_e00,
        chroma_residual=norm.chroma_residual,
        delta_l_star=norm.delta_l_star,
        chroma_limit_floor=cfg.chroma_limit_floor,
        chroma_limit_slope=cfg.chroma_limit_slope,
    )
    res.timings_ms["assess"] = (time.perf_counter() - t0) * 1e3
    res.assessment = assessment

    # Hard-refuse scans that fail chemical locus integrity (e.g. Lead Acetate badges or contaminated substrates)
    if assessment.verdict == Verdict.SUSPECT or not assessment.integrity_ok:
        res.stage_failed = "assess"
        res.reason = "; ".join(assessment.messages[:1]) if assessment.messages else "Chemical signature does not match CuSO4 reaction path"
        res.operator_hint = "Badge rejected: Observed color trajectory does not match CuSO4 reagent (possible Lead Acetate or invalid badge)."
        return res

    if assessment.extrapolated and not assessment.saturated:
        if value > cfg.calibration.obs_max or value < -abs(cfg.calibration.obs_noise_floor * 2.5):
            res.stage_failed = "assess"
            res.reason = "; ".join(assessment.messages[:1])
            res.operator_hint = _HINTS["assess"]
            return res

    res.timings_ms["total"] = sum(
        v for k, v in res.timings_ms.items() if k != "total"
    )
    res.ok = True
    res.reason = "ok"
    return res


def scan_file(path, config: ScanConfig = None) -> ScanResult:
    """Convenience wrapper: read an image file and scan it."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        r = ScanResult()
        r.stage_failed, r.reason = "input", f"could not read image: {path}"
        return r
    return scan_image(img, config)


def debug_montage(image: np.ndarray, res: ScanResult,
                  spec: BadgeSpec = BADGE) -> Optional[np.ndarray]:
    """Side-by-side annotated source and rectified badge, for visual verification.

    This exists because colorimetric bugs are nearly invisible in numbers but obvious in
    pictures - a half-millimetre ROI offset that clips the well wall shows up instantly
    here and not at all in a dE00 value.
    """
    if res.detection is None:
        return None
    left = draw_detection_overlay(image, res.detection, spec)
    if res.detection.warped is None:
        return left

    right = draw_roi_overlay(res.detection.warped, spec)
    h = max(left.shape[0], right.shape[0])
    def pad_to(img):
        out = np.zeros((h, img.shape[1], 3), dtype=np.uint8)
        out[:img.shape[0]] = img
        return out
    montage = np.hstack([pad_to(left), pad_to(right)])

    txt = res.summary()
    colour = (0, 200, 0) if res.ok else (0, 0, 255)
    cv2.putText(montage, txt[:110], (10, h - 14), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, colour, 1, cv2.LINE_AA)
    return montage
