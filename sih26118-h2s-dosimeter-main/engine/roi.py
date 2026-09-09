"""
Region-of-interest masking and robust colour sampling on the rectified badge.

Two correctness points that dominate accuracy here:

**1. Average in linear light, never in gamma-encoded sRGB.**
The sRGB encoding is a ~1/2.4 power law, so the mean of encoded values is not the
encoding of the mean radiance. Averaging encoded pixels over a pad that carries any
shading gradient biases the result *brighter*, which reads as a lower dose - the
dangerous direction for a safety instrument. Every mean in this module is therefore
computed on linearised values.

**2. Trim by luminance, not per channel.**
Rejecting the top/bottom percentiles of each channel independently pulls R, G and B
from different pixel populations and shifts the sampled chromaticity. Here the trim
is decided once from luminance and the surviving pixel *set* is averaged, so the
colour relationship between channels is preserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from .badge_spec import BADGE, BadgeSpec, PATCHES, PATCH_NAMES, NEUTRAL_INDICES
from .colorimetry import srgb_to_linear, linear_rgb_to_xyz, xyz_to_lab

__all__ = [
    "Sample",
    "BadgeSamples",
    "disc_mask",
    "sample_region",
    "sample_badge",
    "draw_roi_overlay",
]

# Rec.709 luminance weights, applied to LINEAR RGB (correct for photometric ordering).
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)


@dataclass
class Sample:
    """Colour statistics for one region, all in linear light unless stated."""

    name: str
    mean_linear: np.ndarray                  # (3,) linear RGB 0..1
    median_linear: np.ndarray                # (3,)
    std_linear: np.ndarray                   # (3,) spatial spread, a uniformity proxy
    n_pixels: int = 0                        # pixels surviving the trim
    n_total: int = 0                         # pixels in the mask
    clip_fraction: float = 0.0               # fraction at/near 8-bit ceiling (glare)
    black_fraction: float = 0.0              # fraction at/near 0 (crushed shadow)

    @property
    def luminance(self) -> float:
        return float(self.mean_linear @ _LUMA)

    @property
    def lab(self) -> np.ndarray:
        return xyz_to_lab(linear_rgb_to_xyz(self.mean_linear))

    @property
    def cv_percent(self) -> float:
        """Coefficient of variation, % - spatial non-uniformity of the region."""
        m = self.luminance
        if m <= 1e-9:
            return float("inf")
        return float(100.0 * (self.std_linear @ _LUMA) / m)


@dataclass
class BadgeSamples:
    """All regions sampled from one rectified badge image."""

    pad: Sample = None
    patches: list = field(default_factory=list)      # 12 Samples, P0..P11 order
    white_field: list = field(default_factory=list)  # Samples on bare substrate, W0..Wn
    white_field_xy: list = field(default_factory=list)   # matching (x_mm, y_mm)
    warnings: list = field(default_factory=list)
    ok: bool = True

    @property
    def patch_means_linear(self) -> np.ndarray:
        """(12, 3) linear RGB of the reference patches, ready for the CCM solve."""
        return np.array([p.mean_linear for p in self.patches], dtype=np.float64)

    @property
    def white_field_linear(self) -> np.ndarray:
        """(n, 3) linear RGB of the bare-substrate probes, for the flat-field fit."""
        if not self.white_field:
            return np.zeros((0, 3), dtype=np.float64)
        return np.array([w.mean_linear for w in self.white_field], dtype=np.float64)

    @property
    def white_field_positions_mm(self) -> np.ndarray:
        """(n, 2) probe centres in mm, same order as :attr:`white_field`."""
        if not self.white_field_xy:
            return np.zeros((0, 2), dtype=np.float64)
        return np.array(self.white_field_xy, dtype=np.float64)

    def patch(self, name: str) -> Sample:
        return self.patches[PATCH_NAMES.index(name)]


# ---------------------------------------------------------------------------
# Masks
# ---------------------------------------------------------------------------

def disc_mask(size: int, centre_px, radius_px: float) -> np.ndarray:
    """Filled circular uint8 mask. Anti-aliasing is deliberately avoided.

    A soft edge would blend well-wall pixels into the pad average at partial weight,
    which is exactly the contamination the sample fraction exists to prevent.
    """
    m = np.zeros((size, size), dtype=np.uint8)
    cv2.circle(m, (int(round(centre_px[0])), int(round(centre_px[1]))),
               max(1, int(round(radius_px))), 255, -1)
    return m


def _square_mask(size: int, centre_px, side_px: float) -> np.ndarray:
    m = np.zeros((size, size), dtype=np.uint8)
    h = side_px / 2.0
    x0, y0 = int(round(centre_px[0] - h)), int(round(centre_px[1] - h))
    x1, y1 = int(round(centre_px[0] + h)), int(round(centre_px[1] + h))
    cv2.rectangle(m, (x0, y0), (x1, y1), 255, -1)
    return m


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def sample_region(
    bgr: np.ndarray,
    mask: np.ndarray,
    name: str = "",
    trim: float = 0.20,
    clip_threshold: int = 254,
    black_threshold: int = 2,
) -> Sample:
    """Robustly sample one masked region of an 8-bit BGR image.

    ``trim`` discards that fraction from each end of the luminance distribution
    (0.20 -> keep the central 60%). This is what makes an oblique flashlight or a
    hand shadow across part of the pad survivable: the specular highlight lands in the
    top tail, the shadow in the bottom tail, and both are dropped before averaging.
    """
    px = bgr[mask == 255]
    n_total = int(px.shape[0])
    if n_total == 0:
        z = np.zeros(3, dtype=np.float64)
        return Sample(name, z, z.copy(), z.copy(), 0, 0, 0.0, 0.0)

    rgb8 = px[:, ::-1].astype(np.float64)                    # BGR -> RGB
    clip_fraction = float(np.mean(np.any(rgb8 >= clip_threshold, axis=1)))
    black_fraction = float(np.mean(np.all(rgb8 <= black_threshold, axis=1)))

    linear = srgb_to_linear(rgb8, max_value=255.0)           # (N, 3) linear light
    luma = linear @ _LUMA

    if 0.0 < trim < 0.5 and n_total >= 20:
        lo, hi = np.quantile(luma, [trim, 1.0 - trim])
        keep = (luma >= lo) & (luma <= hi)
        if keep.sum() < 5:                                   # degenerate: keep all
            keep = np.ones_like(luma, dtype=bool)
    else:
        keep = np.ones_like(luma, dtype=bool)

    sel = linear[keep]
    return Sample(
        name=name,
        mean_linear=sel.mean(axis=0),
        median_linear=np.median(sel, axis=0),
        std_linear=sel.std(axis=0),
        n_pixels=int(sel.shape[0]),
        n_total=n_total,
        clip_fraction=clip_fraction,
        black_fraction=black_fraction,
    )


def sample_badge(
    warped_bgr: np.ndarray,
    spec: BadgeSpec = BADGE,
    trim: float = 0.20,
    max_clip_fraction: float = 0.15,
    max_pad_cv_percent: float = 25.0,
) -> BadgeSamples:
    """Sample the reactive pad, the 12 reference patches and the white-field probes.

    Quality gates raised as warnings (the caller decides whether to hard-fail):

    * pad or patch glare above ``max_clip_fraction`` - clipped pixels carry no colour
      information, so the CCM would be fitted on saturated garbage;
    * pad non-uniformity above ``max_pad_cv_percent`` - indicates a partial shadow,
      a fingerprint, a lifted membrane or non-uniform reagent wetting;
    * a non-monotonic printed grey ramp - the neutrals must come out in the same
      brightness order they were printed in. If they do not, the warp is wrong or the
      badge is damaged, and no amount of colour maths downstream will save the reading.
      This is the cheapest end-to-end integrity check available. The expected order is
      derived from the spec, not written down here, so renaming or reordering a neutral
      cannot silently break it.

    The white-field probes are not colour references and are never fed to the CCM. They
    all carry the same substrate white, sampled at three different radii, and exist only
    so the spatial illumination profile can be measured - a single ring of patches cannot
    distinguish a radial vignette from a flat field.
    """
    n = spec.canonical_px
    if warped_bgr.shape[0] != n or warped_bgr.shape[1] != n:
        raise ValueError(
            f"expected a {n}x{n} rectified image, got {warped_bgr.shape[:2]}"
        )

    out = BadgeSamples()
    centre_px = spec.mm_to_px(np.array(spec.centre_mm))
    pad_r_px = spec.mm_to_px(spec.pad_diameter_mm / 2.0) * spec.pad_sample_fraction
    out.pad = sample_region(warped_bgr, disc_mask(n, centre_px, pad_r_px),
                            "PAD", trim=trim)

    patch_side = spec.mm_to_px(spec.patch_mm) * spec.patch_sample_fraction
    for name, c_mm in zip(PATCH_NAMES, spec.patch_centres_mm()):
        m = _square_mask(n, spec.mm_to_px(c_mm), patch_side)
        out.patches.append(sample_region(warped_bgr, m, name, trim=trim))

    # ---- white-field probes on the bare substrate ------------------------
    # These carry no colour information worth having - they are all the same white - and
    # exist purely so the illumination can be measured at three different radii. See
    # BadgeSpec.white_field_probes_mm for why one radius is not enough.
    #
    # A heavier trim (0.30) than the patches get: these probes are small and sit close to
    # printed edges, so a single bled pixel is a larger fraction of the sample.
    for i, (x_mm, y_mm, d_mm) in enumerate(spec.white_field_probes_mm()):
        r_px = spec.mm_to_px(d_mm / 2.0) * 0.85
        m = disc_mask(n, spec.mm_to_px(np.array([x_mm, y_mm])), r_px)
        out.white_field.append(sample_region(warped_bgr, m, f"W{i}", trim=0.30))
        out.white_field_xy.append((float(x_mm), float(y_mm)))

    # ---- quality gates ---------------------------------------------------
    if out.pad.clip_fraction > max_clip_fraction:
        out.warnings.append(
            f"pad glare: {out.pad.clip_fraction * 100:.1f}% of pixels clipped "
            f"(limit {max_clip_fraction * 100:.0f}%) - tilt away from the light source"
        )
    if out.pad.black_fraction > 0.5:
        out.warnings.append(
            f"pad underexposed: {out.pad.black_fraction * 100:.0f}% of pixels crushed to black"
        )
    if out.pad.cv_percent > max_pad_cv_percent:
        out.warnings.append(
            f"pad non-uniform: CV {out.pad.cv_percent:.1f}% "
            f"(limit {max_pad_cv_percent:.0f}%) - shadow, smear or lifted membrane"
        )

    bad_patches = [p.name for p in out.patches if p.clip_fraction > max_clip_fraction]
    if bad_patches:
        out.warnings.append(
            f"reference patches clipped: {', '.join(bad_patches)} - "
            "colour correction will be unreliable"
        )

    # Sanity check the neutral ramp: the printed greys must come out in the same brightness
    # order they were printed in. This is the cheapest possible detector for a gross
    # rectification failure - if the homography is wrong, the sampler is reading the wrong
    # squares, and scrambled greys reveal that instantly even though every individual
    # colour still looks perfectly plausible on its own.
    #
    # Derived from the spec rather than hardcoded, because it was hardcoded once and a patch
    # rename turned this check into a crash.
    ramp = sorted(
        (i for i in NEUTRAL_INDICES),
        key=lambda i: -float(np.dot(srgb_to_linear(
            np.array(PATCHES[i].srgb, dtype=np.float64), max_value=255.0), _LUMA)),
    )
    names = [PATCHES[i].name for i in ramp]
    lum = [out.patches[i].luminance for i in ramp]
    if len(lum) >= 3 and not all(lum[i] >= lum[i + 1] - 0.015 for i in range(len(lum) - 1)):
        out.warnings.append(
            "printed grey ramp is not monotonic ("
            + ", ".join(f"{k}={v:.4f}" for k, v in zip(names, lum))
            + ") - possible rectification noise"
        )
        if lum[0] < lum[-1]:
            out.ok = False

    return out


# ---------------------------------------------------------------------------
# Debug overlay
# ---------------------------------------------------------------------------

def draw_roi_overlay(warped_bgr: np.ndarray, spec: BadgeSpec = BADGE) -> np.ndarray:
    """Draw the sampling regions on the rectified badge for visual verification."""
    vis = warped_bgr.copy()
    centre_px = spec.mm_to_px(np.array(spec.centre_mm))
    pad_r = spec.mm_to_px(spec.pad_diameter_mm / 2.0)

    cv2.circle(vis, tuple(centre_px.astype(int)), int(pad_r), (0, 140, 255), 1)
    cv2.circle(vis, tuple(centre_px.astype(int)),
               int(pad_r * spec.pad_sample_fraction), (0, 255, 0), 2)
    cv2.circle(vis, tuple(centre_px.astype(int)),
               int(spec.mm_to_px(spec.well_diameter_mm / 2.0)), (255, 120, 0), 1)

    side = spec.mm_to_px(spec.patch_mm)
    for i, c_mm in enumerate(spec.patch_centres_mm()):
        c = spec.mm_to_px(c_mm)
        h = side / 2.0
        cv2.rectangle(vis, (int(c[0] - h), int(c[1] - h)),
                      (int(c[0] + h), int(c[1] + h)), (0, 140, 255), 1)
        hs = side * spec.patch_sample_fraction / 2.0
        cv2.rectangle(vis, (int(c[0] - hs), int(c[1] - hs)),
                      (int(c[0] + hs), int(c[1] + hs)), (0, 255, 0), 1)
        cv2.putText(vis, f"P{i}", (int(c[0] - h), int(c[1] - h) - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.32, (255, 255, 255), 1)

    for (x_mm, y_mm, d_mm) in spec.white_field_probes_mm():
        c = spec.mm_to_px(np.array([x_mm, y_mm]))
        cv2.circle(vis, tuple(c.astype(int)),
                   max(1, int(round(spec.mm_to_px(d_mm / 2.0) * 0.85))),
                   (255, 0, 255), 1)
    return vis
