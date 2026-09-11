"""
Illumination and camera normalisation using the on-badge reference patches.

This is the module that makes the whole concept work. A passive colorimetric badge is
only as good as the reader's ability to separate *chemistry* (the pad darkening) from
*optics* (illuminant colour, camera white balance, exposure, sensor cross-talk). The
printed patch ring provides 12 known colours photographed in the same frame under the
same light as the pad, which turns that separation into a small regression problem.

Two corrections are applied, and they fix genuinely different errors:

1. **Flat field** - a *spatial* correction. Illumination is never uniform across a 30 mm
   badge: an oblique lamp, the operator's own shadow, the phone body blocking the sky, and
   - always - the lens's own vignetting. The patches sit on a ring while the pad sits at
   the centre, so any brightness variation makes them disagree with the pad about how
   bright the light is. A colour-correction matrix cannot fix this, because a single matrix
   applies one correction everywhere. Measured on synthetic scans, a 25% ramp across the
   frame inflated the reading by 21%, and lens vignetting alone walked it from +5.8% to
   -9.7%.

   The correction is fitted from whichever reference is richer:

       white-field probes (quadratic, needs >= 9 clean probes)   linear ramp + radial term
       patch ring (plane, needs >= 5 clean patches)              linear ramp only

   The white-field route is strongly preferred and is not a refinement - it is the only one
   that can see vignetting at all. Every patch sits at the same radius, and on a circle
   ``x^2 + y^2`` is constant, so from the ring alone a radially symmetric falloff is
   algebraically indistinguishable from the overall brightness. The bare substrate is
   sampled at two radii plus the pad centre, which makes the radial term identifiable.
2. **Colour correction** - a *colorimetric* correction, for illuminant colour, white
   balance and sensor cross-talk. This is the CCM, fitted after flat fielding so the
   regression sees patches under one consistent light level.

Fallback ladder for the CCM, most to least capable:

    root6 CCM (6 features, needs >= 6 clean patches)   exposure-invariant, best accuracy
    affine CCM (4 features, needs >= 4)                handles veiling glare offset
    linear CCM (3 features, needs >= 3)                classic 3x3
    von Kries grey balance (needs >= 1 neutral)        colour cast only, last resort

Quality is reported as a **leave-one-out** residual, not a training residual. Fitting
12 patches with 6 features and then scoring those same 12 patches flatters the model;
LOO refits without each patch and predicts it, which is an honest estimate of how well
the pad - a colour the model never saw - will be corrected.

The number that *gates* the scan is the **locus-weighted** LOO: the same residuals, but
weighted by how near each reference patch lies to the pad's own colour path. A plain mean
over all 12 patches answers "how good is this fit everywhere in colour space", and that is
not the question. The pad is a near-neutral warm ramp from L* 88 to L* 22; whether the
matrix reproduces a saturated blue has no bearing on reading it. Measured across lighting
and camera sweeps, the unweighted mean did not correlate with the actual dE00 error at all
and rejected almost every non-D65 condition despite errors of only 10-17%. A separate
catastrophe ceiling on the unweighted mean is kept, so a genuinely broken fit - sodium light
with the torch off, where the mean runs to 30 dE00 - still fails.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .badge_spec import (
    BADGE,
    BadgeSpec,
    FULLY_REACTED_PAD_LAB,
    NEUTRAL_INDICES,
    PATCH_NAMES,
    REFERENCE_SRGB,
    SUBSTRATE_PATCH_INDICES,
    UNEXPOSED_PAD_LAB,
)
from .colorimetry import (
    CHANNEL_BALANCE_REJECT,
    CHANNEL_BALANCE_WARN,
    apply_ccm,
    ccm_feature_matrix,
    delta_e_ciede2000,
    linear_rgb_to_xyz,
    narrowband_check,
    solve_ccm,
    srgb_to_linear,
    von_kries_gain,
    xyz_to_lab,
)
from .dosimetry import locus_chroma_residual, locus_projection
from .roi import BadgeSamples

__all__ = ["NormalizationResult", "normalize_badge", "reference_linear", "FLAT_FIELD_MODES"]

_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float64)

#: Spatial illumination models. ``luma`` is the default: it estimates one achromatic
#: brightness ramp, which is what an oblique lamp or a shadow actually produces, and it is
#: the most robust because 12 patches constrain 3 parameters. ``rgb`` fits an independent
#: ramp per channel, for genuinely mixed lighting (a sodium lamp on one side, daylight
#: through a window on the other) at the cost of 9 parameters. ``none`` disables the
#: correction, which exists so the test harness can measure what it is worth.
FLAT_FIELD_MODES = ("luma", "rgb", "none")


def reference_linear(reference_srgb: np.ndarray = None) -> np.ndarray:
    """(12, 3) reference patch values in linear light, the CCM regression target."""
    src = REFERENCE_SRGB if reference_srgb is None else np.asarray(reference_srgb)
    return srgb_to_linear(src, max_value=255.0)


@dataclass
class NormalizationResult:
    """Outcome of colour-correcting one badge scan."""

    mode: str = "none"
    matrix: np.ndarray = None
    pad_linear: np.ndarray = None            # corrected pad, linear RGB
    pad_lab: np.ndarray = None               # corrected pad, CIE L*a*b*
    baseline_lab: np.ndarray = None          # unexposed reference used for the difference
    baseline_source: str = ""

    # ---- the dose observables -------------------------------------------
    #: ``-dL*``: how much lightness the pad has lost against its baseline. **This is the
    #: quantity the dose is computed from** - see :mod:`engine.dosimetry` for the measurement
    #: showing it beats dE00 by better than 2x in rms error.
    delta_l_star: float = float("nan")
    #: Signed displacement along the PbS reaction path. Reported as a cross-check: it should
    #: track ``delta_l_star / 0.987``, and a disagreement means the pad moved sideways.
    locus_projection: float = float("nan")
    #: Off-locus chroma displacement - the integrity check. See
    #: :func:`engine.dosimetry.locus_chroma_residual`.
    chroma_residual: float = float("nan")
    #: CIEDE2000 against the baseline. Computed and stored on every scan because it is the
    #: conventional colorimetric figure and the print tolerances are specified in it, but it
    #: does **not** drive the dose.
    delta_e00: float = float("nan")

    #: Honest leave-one-out residual over the reference patches, in dE00 units. Only the
    #: *collapse* ceiling is enforced on this - see ``max_loo_residual``.
    loo_residual_mean: float = float("nan")
    loo_residual_max: float = float("nan")
    #: The same residuals weighted towards the pad's own colour path. Reported as a warning
    #: only; measured not to predict dose error. See :func:`_locus_weights` and
    #: ``warn_locus_residual``.
    locus_residual: float = float("nan")
    #: Locus-weighted **signed L\*** leave-one-out bias, in L* units. Constructed as the
    #: diagnostic *matched* to the reading - since dose comes from ``-dL*``, this is the
    #: error that ought to propagate into it, and its sign says which way. Positive means the
    #: CCM renders near-locus patches lighter than they are, which would make the pad look
    #: lighter and the dose look smaller.
    #:
    #: **It does not work, and this field is diagnostic only.** Over 160 cases (2 doses x 8
    #: illuminants x 5 cameras x 2 shading states) it correlates with the signed ``-dL*``
    #: error at pearson -0.009, spearman +0.001. Subtracting ``0.5 x`` it appears to help
    #: (rms 3.68% -> 3.24%) but that is entirely mean-removal: the per-scan standard
    #: deviation *rises*, 3.13% -> 3.22%. Kept because it is cheap, because it is the right
    #: number to inspect when a specific scan is disputed, and because deleting it would
    #: invite someone to reinvent it. Do not gate or correct on it.
    locus_l_bias: float = float("nan")
    #: Training residual, kept only to expose the optimism gap.
    fit_residual_mean: float = float("nan")
    #: Condition number of the regression - large values mean the illuminant did not
    #: excite the colour axes independently (narrow-band sodium light does this).
    condition_number: float = float("nan")
    patch_residuals: dict = field(default_factory=dict)
    #: Per-patch ``(weight, dE00 distance to the pad's colour path)``, so a rejection can be
    #: explained rather than merely asserted.
    locus_weights: dict = field(default_factory=dict)

    used_patches: tuple = ()
    warnings: list = field(default_factory=list)
    ok: bool = False
    reason: str = ""

    # ---- spatial illumination -------------------------------------------
    #: Which flat-field model was actually applied.
    flat_field_mode: str = "none"
    #: Where the model was fitted from: ``whitefield`` (quadratic, sees vignetting),
    #: ``patches`` (plane only) or ``none``.
    flat_field_source: str = "none"
    #: Peak-to-peak of the fitted illumination profile across the measured region of the
    #: badge, in percent. This is a directly useful operator diagnostic: a large value
    #: means "your shadow is on it".
    gradient_percent: float = 0.0

    # ---- illuminant condition -------------------------------------------
    #: Weakest / strongest mean colour channel over the observed patches, measured on the
    #: raw sample before any correction. See :func:`engine.colorimetry.channel_balance`.
    channel_balance: float = float("nan")
    #: ``ok`` / ``warn`` / ``reject`` from :func:`engine.colorimetry.narrowband_check`.
    light_quality: str = "ok"


def _usable_patch_mask(samples: BadgeSamples, max_clip: float = 0.02) -> np.ndarray:
    """Boolean mask of patches trustworthy enough to fit on."""
    mask = []
    for p in samples.patches:
        good = (
            p.n_pixels >= 5
            and p.clip_fraction <= max_clip
            and p.black_fraction <= 0.5
            and np.all(np.isfinite(p.mean_linear))
        )
        mask.append(bool(good))
    return np.array(mask, dtype=bool)


def _usable_probe_mask(samples: BadgeSamples, max_clip: float = 0.02) -> np.ndarray:
    """Boolean mask of white-field probes trustworthy enough to fit on.

    Stricter on clipping than the patches are, and deliberately so: the bare substrate is
    the brightest thing on the badge, so it is the first region to saturate. A clipped probe
    does not merely add noise, it reports a *ceiling* instead of a brightness, which would
    flatten the fitted profile in exactly the region where the light is strongest and
    manufacture a falloff that is not there.
    """
    n = len(samples.white_field)
    if n == 0:
        return np.zeros(0, dtype=bool)
    mask = []
    for w in samples.white_field:
        good = (
            w.n_pixels >= 5
            and w.clip_fraction <= max_clip
            and w.black_fraction <= 0.02
            and np.all(np.isfinite(w.mean_linear))
            and float(w.mean_linear @ _LUMA) > 1e-4
        )
        mask.append(bool(good))
    return np.array(mask, dtype=bool)


def _norm_xy(spec: BadgeSpec, pts_mm: np.ndarray) -> np.ndarray:
    """Badge millimetres -> normalised coordinates with the pad centre at exactly (0, 0).

    Scaled to roughly [-1, 1] over the badge head so the design matrix is well conditioned
    regardless of physical size, and - the part that matters - so evaluating any fitted
    model at the origin gives the value at the pad.
    """
    pts = np.atleast_2d(np.asarray(pts_mm, dtype=np.float64))
    cx, cy = spec.centre_mm
    half = spec.head_mm / 2.0
    return np.column_stack([(pts[:, 0] - cx) / half, (pts[:, 1] - cy) / half])


def _patch_xy(spec: BadgeSpec) -> np.ndarray:
    """(12, 2) patch centres in badge-normalised coordinates."""
    return _norm_xy(spec, spec.patch_centres_mm())


def _probe_xy(spec: BadgeSpec) -> np.ndarray:
    """(n, 2) white-field probe centres in badge-normalised coordinates."""
    return _norm_xy(spec, spec.white_field_probes_mm()[:, :2])


def _design(xy: np.ndarray, kind: str) -> np.ndarray:
    """Design matrix for the spatial illumination model. Column 0 is always the intercept."""
    xy = np.atleast_2d(np.asarray(xy, dtype=np.float64))
    x, y = xy[:, 0], xy[:, 1]
    if kind == "quad":
        return np.column_stack([np.ones_like(x), x, y, x * x, y * y, x * y])
    return np.column_stack([np.ones_like(x), x, y])


def _flat_field_gains(model, xy: np.ndarray) -> np.ndarray:
    """Evaluate a fitted illumination model at arbitrary badge positions.

    ``model`` is ``(kind, slopes)`` as returned by the fitters, or ``None`` for no
    correction. The intercept is *not* part of ``slopes``, which is what makes the gain at
    the pad centre exactly 1.0 - see the fitters for why that is the whole trick.

    Kept separate from the fits so a model can be estimated on the trustworthy references
    only and then applied everywhere, including at positions that were excluded.
    """
    xy = np.atleast_2d(np.asarray(xy, dtype=np.float64))
    if model is None:
        return np.ones((xy.shape[0], 1))
    kind, slopes = model
    g = np.exp(_design(xy, kind)[:, 1:] @ slopes)
    return g[:, None] if g.ndim == 1 else g


def _gradient_percent(model, xy_eval: np.ndarray) -> float:
    """Peak-to-peak of the fitted profile over the region that was actually measured.

    Evaluated on the probe and patch positions plus the pad centre, never on the badge
    corners. A plane extrapolated to the corners overstates the ramp, and a *quadratic*
    extrapolated there is meaningless - the corners sit at radius 1.41 in normalised units
    while the outermost probe is at 0.88, so anything reported out there is invention.
    """
    g = _flat_field_gains(model, xy_eval)
    lum = g.mean(axis=1) if g.shape[1] == 3 else g[:, 0]
    return float(100.0 * (lum.max() - lum.min()) / max(lum.mean(), 1e-9))


def _starved(obs: np.ndarray, floor: float = 0.02) -> bool:
    """True if one colour channel carries essentially no signal (narrow-band light).

    Under sodium light the observed blue is a couple of DN of pure noise, so any per-channel
    model fitted on it fits the noise. Left unguarded this was catastrophic rather than
    merely inaccurate: a fitted gradient of 1117% and a NaN reading.
    """
    level = np.median(np.atleast_2d(obs), axis=0)
    return float(level.max()) <= 0 or float(level.min() / max(level.max(), 1e-12)) < floor


def _robust_lstsq(A: np.ndarray, L: np.ndarray, min_keep: int) -> tuple:
    """Least squares with one median-absolute-deviation reweighting pass.

    A single contaminated reference - a fingerprint, a scuff, a dust mote, a printed edge
    bleeding into a probe - would otherwise tilt the surface and push that error onto every
    other position, turning one bad sample into twelve. MAD is used rather than the standard
    deviation precisely because it does not itself get inflated by the outlier it is meant
    to find.

    Returns ``(coef, n_excluded)``.
    """
    coef, *_ = np.linalg.lstsq(A, L, rcond=None)
    resid = np.ravel(np.abs(L - A @ coef).max(axis=1))
    med = float(np.median(resid))
    mad = float(np.median(np.abs(resid - med))) * 1.4826
    if mad > 1e-9:
        keep = resid <= med + 3.0 * mad
        n_keep = int(keep.sum())
        if min_keep <= n_keep < A.shape[0]:
            coef, *_ = np.linalg.lstsq(A[keep], L[keep], rcond=None)
            return coef, A.shape[0] - n_keep
    return coef, 0


def _fit_white_field(obs: np.ndarray, xy: np.ndarray, mode: str = "luma") -> tuple:
    """Fit the spatial illumination profile from the bare-substrate probes.

    This is the correction that can see lens vignetting, and it is worth being precise about
    why it works when the patch ring cannot.

    Model: ``observed = w * g(x, y)`` where ``w`` is the substrate's own reflectance and
    ``g`` the spatial gain. Taking logs, ``log(obs) = log w + quadratic(x, y)``. Because
    every probe lands on the *same* white, ``log w`` is a genuine constant and falls
    entirely into the intercept - so the fit needs no reference values at all, only the
    knowledge that the surface is uniform. That is a much weaker assumption than knowing its
    reflectance, and unlike a printed patch it survives paper stock changes, yellowing and
    lot-to-lot variation untouched.

    The surface fitted is the full quadratic ``[1, x, y, x^2, y^2, xy]``. The linear terms
    take the oblique-lamp ramp, ``x^2 + y^2`` takes vignetting, and the cross term takes an
    off-centre falloff, which is the realistic case - the badge is rarely dead centre in the
    frame. Six parameters against 12 probes.

    Identifiability is the whole point of the probe layout: eight probes sit at normalised
    radius 0.45 and four at 0.88. Two radii plus the implicit constraint at the origin is
    enough to separate the isotropic term from the intercept, which one ring never can.

    As with the plane fit, only the *slope* terms are kept and the intercept is discarded,
    so the correction evaluated at the pad centre is exactly 1.0 and the pad is never
    scaled. The operation is "bring every reference to the light level the pad is sitting
    in", which is precisely the comparison the dE00 needs.

    Returns ``(model, note)`` with ``model = ("quad", slopes)`` or ``(None, note)``.
    """
    n = obs.shape[0]
    note = ""
    if n < 9:                     # 6 parameters, so demand real spare degrees of freedom
        return None, ""

    if mode == "rgb" and _starved(obs):
        mode = "luma"
        note = ("white-field fell back to achromatic: one colour channel is starved "
                "(narrow-band light), so a per-channel profile cannot be estimated")

    if mode == "rgb":
        num = obs
    else:
        num = (obs @ _LUMA)[:, None]
    L = np.log(np.maximum(num, 1e-6))

    A = _design(xy, "quad")
    if np.linalg.cond(A) > 1e6:
        return None, "white-field probe layout is degenerate; using the patch-ring plane"

    coef, n_excluded = _robust_lstsq(A, L, min_keep=8)
    if n_excluded:
        note = "; ".join(filter(None, [
            note, f"white-field fit excluded {n_excluded} probe(s) as outliers"]))
    return ("quad", coef[1:]), note


def _fit_patch_plane(obs: np.ndarray, ref: np.ndarray, xy: np.ndarray,
                     mode: str = "luma") -> tuple:
    """Fallback: estimate a linear illumination ramp from the achromatic reference patches.

    Used when the white-field probes are unusable - clipped by a specular streak, or the
    badge is scuffed. Model: ``observed = k * g(x, y) * reference``, so
    ``log(obs/ref) = log k + a*x + b*y``, an ordinary plane fit whose intercept absorbs
    exposure and colour cast without contaminating the slopes. That separation is what lets
    it run before the CCM is known.

    WHY ONLY THE ACHROMATIC PATCHES
    ------------------------------
    ``obs/ref`` is not a pure measurement of illumination. It also contains every reason the
    camera failed to reproduce that patch's colour - the sensor's gamut, its white balance,
    the printer's own error against the nominal sRGB. A saturated red recorded by a phone
    with an aggressive saturation curve is off by percent-level for reasons that have nothing
    to do with where it sits on the badge, and the plane will happily attribute that to
    position. Measured: fitting all 12 patches produced a 3.2% error in the recovered gain
    where doing nothing at all cost 1.9% - the correction was worse than the disease.
    Restricting the fit to the neutrals and substrates, whose reproduction error is small
    and whose luminance ratio really is dominated by illumination, removes the confound.

    Its remaining limit is structural, not a matter of precision: all patches sit at one
    radius, so a radially symmetric falloff is confounded with the constant and is invisible
    here. That is the entire reason :func:`_fit_white_field` exists, and why this function is
    a fallback rather than the main path.

    Returns ``(model, note)`` with ``model = ("plane", slopes)``.
    """
    n = obs.shape[0]
    note = ""
    if n < 5:
        return None, ""

    if mode == "rgb" and _starved(obs):
        mode = "luma"
        note = ("flat-field fell back to achromatic: one colour channel is starved "
                "(narrow-band light), so a per-channel gradient cannot be estimated")

    if mode == "rgb":
        num, den = obs, np.maximum(ref, 1e-6)
    else:
        num = (obs @ _LUMA)[:, None]
        den = np.maximum((ref @ _LUMA)[:, None], 1e-6)
    L = np.log(np.maximum(num, 1e-6) / den)

    coef, n_excluded = _robust_lstsq(_design(xy, "plane"), L, min_keep=4)
    if n_excluded:
        note = "; ".join(filter(None, [
            note, f"flat-field fit excluded {n_excluded} patch(es) as spatial outliers"]))
    return ("plane", coef[1:]), note


#: How finely the pad's colour path is discretised when measuring distance to it. The path
#: is short and near-straight, so 33 points resolves it to well under 1 dE00.
_LOCUS_SAMPLES = 33

#: Width of the locus weighting, in dE00. A patch this far from the pad's colour path keeps
#: about 61% of its weight; at twice this distance, 13%. Chosen so the neutrals and
#: substrates - which sit on or beside the path - dominate, while the chroma patches still
#: contribute enough to catch a matrix that has gone wrong in a way that would eventually
#: reach the path. Setting it to infinity recovers the old unweighted mean.
_LOCUS_SIGMA = 18.0


def _pad_locus_lab(n: int = _LOCUS_SAMPLES) -> np.ndarray:
    """(n, 3) sampling of the colour path the pad travels as it reacts, in L*a*b*.

    A straight segment from the unexposed tone to the fully-reacted tone. The real path
    bows slightly - lead sulphide is not a neutral density filter - but the bow is small
    next to the weighting width, and using the two published endpoints keeps this tied to
    the same constants the dosimetry and the printed substrate patch are derived from.
    """
    t = np.linspace(0.0, 1.0, int(n))[:, None]
    a = np.asarray(UNEXPOSED_PAD_LAB, dtype=np.float64)
    b = np.asarray(FULLY_REACTED_PAD_LAB, dtype=np.float64)
    return a + t * (b - a)


def _locus_weights(ref_lab: np.ndarray, sigma: float = _LOCUS_SIGMA) -> tuple:
    """Weight each reference patch by how near it lies to the pad's colour path.

    WHY THE UNWEIGHTED MEAN IS THE WRONG GATE
    -----------------------------------------
    A mean leave-one-out residual over all 12 patches answers "how faithful is this colour
    correction across colour space". That is a fine question and not the one that matters.
    The only colour this instrument has to get right is the pad's, and the pad is a
    near-neutral warm ramp from L* 88 down to L* 22. How well the matrix reproduces a
    saturated blue is irrelevant - and under warm light it is worse than irrelevant, because
    an incandescent lamp puts almost no energy into the blue patch, so its residual is large,
    uninformative, and drags the mean past the limit. Measured: the unweighted mean rejected
    fluorescent, metal halide, incandescent, twilight and both torch-assisted sodium
    conditions - every non-D65 case - while the actual dose error in those scans was 10-17%.
    Across a vignette and shading sweep it showed no correlation with the true error at all:
    the best-scoring scan (2.26) was less accurate than one that scored 4.75.

    Distance is measured with CIEDE2000 to the nearest point on the discretised path rather
    than as a Euclidean L*a*b* distance, so the weighting uses the same perceptual metric as
    the residuals it is weighting.

    Returns ``(weights, distances)``, both (n,).
    """
    locus = _pad_locus_lab()
    ref_lab = np.atleast_2d(np.asarray(ref_lab, dtype=np.float64))
    dist = np.array(
        [min(float(delta_e_ciede2000(lab, p)) for p in locus) for lab in ref_lab]
    )
    if not np.isfinite(sigma) or sigma <= 0:
        return np.ones_like(dist), dist
    return np.exp(-0.5 * (dist / float(sigma)) ** 2), dist


def _loo_residuals(obs: np.ndarray, ref: np.ndarray, mode: str, ridge: float) -> tuple:
    """Leave-one-out residual for each patch, in dE00 **and** in signed L* error.

    Refits the CCM with patch *i* held out, then predicts patch *i*. Requires at least
    one spare patch beyond the feature count, otherwise the held-out fit is degenerate
    and NaN is returned for that patch.

    Both metrics are returned because they answer different questions and the reader depends
    on the second one. dE00 is the conventional figure. The *lightness* error is what
    propagates into the dose, since the dose is computed from ``-dL*`` - a matrix that gets
    every patch's hue right and its lightness wrong is useless here and dE00 would not say
    so loudly enough. Signed rather than absolute, because a CCM that darkens every patch
    is biasing the reading in a known direction, and averaging absolute values would hide
    exactly that.

    Returns ``(de00, dl_signed)``, both (n,).
    """
    n = obs.shape[0]
    n_feat = ccm_feature_matrix(obs[:1], mode).shape[1]
    res = np.full(n, np.nan)
    res_l = np.full(n, np.nan)
    if n - 1 < n_feat + 1:
        return res, res_l
    for i in range(n):
        keep = np.ones(n, dtype=bool)
        keep[i] = False
        try:
            M = solve_ccm(obs[keep], ref[keep], mode=mode, ridge=ridge)
        except (ValueError, np.linalg.LinAlgError):
            continue
        pred = apply_ccm(obs[i], M, mode=mode)
        lab_pred = xyz_to_lab(linear_rgb_to_xyz(pred))
        lab_ref = xyz_to_lab(linear_rgb_to_xyz(ref[i]))
        res[i] = delta_e_ciede2000(lab_pred, lab_ref)
        res_l[i] = float(lab_pred[0] - lab_ref[0])
    return res, res_l


def normalize_badge(
    samples: BadgeSamples,
    spec: BadgeSpec = BADGE,
    reference_srgb: np.ndarray = None,
    mode: str = "root6",
    ridge: float = 1e-4,
    baseline_mode: str = "onbadge",
    warn_loo_residual: float = 8.0,
    flat_field: str = "luma",
    max_gradient_percent: float = 35.0,
    warn_locus_residual: float = 2.0,
    warn_channel_balance: float = CHANNEL_BALANCE_WARN,
    reject_channel_balance: float = CHANNEL_BALANCE_REJECT,
) -> NormalizationResult:
    """Colour-correct a badge scan and measure the pad against its unexposed baseline.

    Produces three numbers from one L*a*b* displacement: ``delta_l_star`` (the dose
    observable), ``chroma_residual`` (the integrity check) and ``delta_e00`` (the record).
    See :mod:`engine.dosimetry` for why the dose is not taken from dE00.

    Parameters
    ----------
    samples
        Output of :func:`engine.roi.sample_badge`.
    reference_srgb
        Optional measured patch values from
        :func:`engine.badge_spec.load_measured_patches`. Strongly recommended once you
        have printed real badges - nominal print values carry several dE of error.
    mode
        Preferred CCM mode; automatically degrades if too few patches are usable.
    baseline_mode
        ``'onbadge'`` (default) averages the printed SUBSTRATE patches photographed in the
        same frame, so any residual illumination error largely cancels in the
        difference. ``'constant'`` uses the factory ``UNEXPOSED_PAD_LAB`` constant,
        which is simpler but does not cancel residual error. Note the trade-off:
        the printed patch does not age with the reagent, so for badges stored a long
        time a per-lot constant measured from that lot is the more faithful reference.
    warn_locus_residual
        Threshold for a *warning* on the leave-one-out residual weighted towards the pad's
        own colour path, in dE00. Attach it to the record; do not reject on it.

        This was a rejection gate at 2.0 dE00 and has been demoted, because measurement
        says it costs accuracy rather than buying it. Over 40 scans at 8 ppm*hr spanning 8
        illuminants and 5 cameras, sweeping the threshold from 1.5 to infinity left the
        worst *kept* ``-dL*`` error at 14.78% for every single value - the gate never once
        removed the scan that was actually wrong. Meanwhile at 1.5 it discarded 18 of 40
        scans whose mean error was 3.80%, better than the 5.17% rms of the scans it kept. It
        also rejects one of the five simulated phone cameras under plain D65 daylight
        (locus residual above 2.0 at unweighted 4.39), so as a gate it bans a class of
        *handset* rather than a class of *lighting* - and the operator has no way to act on
        that. The properly matched replacement, ``locus_l_bias``, does not predict either
        (see that field). Fit quality near the pad's tone is real information about the
        photograph and is worth recording; it is simply not a usable predictor of dose error,
        and pretending otherwise silently discards good measurements.
    warn_loo_residual
        Threshold for a *warning* on the unweighted mean leave-one-out residual, in dE00.
        Also not a rejection, and this one had to be demoted too.

        It was a "catastrophe ceiling" at 8.0, on the reasoning that a *collapsed* colour fit
        - as opposed to a merely degraded one - cannot be salvaged. Measurement over 55 scans
        including torch-off sodium says no threshold on it works, because it orders the cases
        backwards::

            incandescent_2856 / budget    LOO 18.4   dose error   +3.0%   must KEEP
            hps (torch off)   / flagship  LOO 21.1   dose error   -0.8%   must KEEP
            hps (torch off)   / budget    LOO 12.6   dose error +151.4%   must REJECT

        A ceiling low enough to catch the third rejects the first two. The same is true of the
        locus-weighted residual (13.6 bad vs 12.9 good) and of the condition number, which is
        inverted outright (7846 bad vs 27233 good). The reason is the one that recurs through
        this module: the reading is a difference between two regions of one frame, so absolute
        colour accuracy is largely irrelevant to it. What did separate the cases was whether
        the *baseline* survived at all - see the collapse gate further down, which replaced
        this ceiling and needs no threshold.
    flat_field
        Spatial illumination model, see :data:`FLAT_FIELD_MODES`.
    max_gradient_percent
        Reject the scan if the fitted illumination profile varies by more than this across
        the measured region of the badge. Beyond roughly a third the variation is no longer
        smooth - it is a hard shadow edge or a specular streak - and a low-order surface is
        the wrong model, so extrapolating it to the pad would do more harm than leaving it
        alone.
    warn_channel_balance, reject_channel_balance
        Narrow-band illuminant limits on
        :func:`engine.colorimetry.channel_balance`, checked before any fitting. ``warn`` at
        0.30 is "one colour channel is weak, most likely a sodium lamp, switch the torch on"
        and is the only tier that fires by default. ``reject`` ships at 0.0, i.e. **off**: a
        hard refusal at 0.05 was measured and removed because it discarded accurate readings
        (``hps/midrange_a`` reads -2.9% at balance 0.004) and caught nothing the collapse gate
        below does not already catch. A site whose policy is "no reading at all under sodium"
        can pass 0.05 explicitly.

    Returns
    -------
    NormalizationResult
    """
    out = NormalizationResult()
    if flat_field not in FLAT_FIELD_MODES:
        out.reason = f"unknown flat_field mode {flat_field!r}; expected {FLAT_FIELD_MODES}"
        return out

    ref_all = reference_linear(reference_srgb)
    obs_raw = samples.patch_means_linear

    if obs_raw.shape[0] != ref_all.shape[0]:
        out.reason = (
            f"patch count mismatch: sampled {obs_raw.shape[0]}, reference {ref_all.shape[0]}"
        )
        return out

    # ---- illuminant condition, before anything is fitted --------------------
    # Deliberately first, and deliberately on the raw patch means over ALL 12 patches
    # (which is how the thresholds were measured). The question it answers - "does this
    # light contain enough spectrum to do colorimetry at all?" - must not be answered using
    # a colour fit made under that same light, and a near-monochromatic source is a property
    # of the scene that no amount of downstream correction can undo.
    level, balance, message = narrowband_check(
        obs_raw, warn=warn_channel_balance, reject=reject_channel_balance
    )
    out.channel_balance = balance
    out.light_quality = level
    if level == "reject":
        out.reason = message
        return out
    if level == "warn":
        out.warnings.append(message)

    usable = _usable_patch_mask(samples)
    n_usable = int(usable.sum())
    if n_usable < obs_raw.shape[0]:
        dropped = [PATCH_NAMES[i] for i in np.flatnonzero(~usable)]
        out.warnings.append(f"dropped unusable patches: {', '.join(dropped)}")

    # ---- spatial flat field -------------------------------------------------
    # Fitted on trustworthy references only but evaluated at all 12 patch positions, so an
    # unusable reference cannot corrupt the surface yet is still corrected if it is needed
    # downstream. Two sources, tried in order of what they can actually see.
    xy = _patch_xy(spec)
    model, note = None, ""
    if flat_field != "none":
        probe_xy = _probe_xy(spec)
        probes = samples.white_field_linear
        pmask = _usable_probe_mask(samples)

        if probes.shape[0] == probe_xy.shape[0] and int(pmask.sum()) >= 9:
            model, note = _fit_white_field(probes[pmask], probe_xy[pmask], flat_field)
            if model is not None:
                out.flat_field_source = "whitefield"

        if model is None:
            # Say *why* the good route was unavailable, not just that the reading is
            # degraded. "Probes clipped" tells the operator to tilt away from the glare;
            # a bare "vignetting uncorrected" tells them nothing they can act on.
            if probes.shape[0] != probe_xy.shape[0]:
                out.warnings.append(
                    "white-field probes were not sampled (stale BadgeSamples?); "
                    "falling back to the patch-ring plane, which cannot see vignetting"
                )
            elif int(pmask.sum()) < 9:
                out.warnings.append(
                    f"only {int(pmask.sum())} of {probes.shape[0]} white-field probes usable "
                    "(clipped or shadowed); falling back to the patch-ring plane, which "
                    "cannot see lens vignetting - the reading may understate the dose"
                )
            elif note:
                out.warnings.append(note)
                note = ""
            if n_usable >= 5:
                # Achromatic references only - see _fit_patch_plane for why chroma patches
                # poison this fit. NEUTRAL_INDICES plus the substrates gives 6.
                achrom = np.array(
                    [i for i in sorted(set(NEUTRAL_INDICES) | set(SUBSTRATE_PATCH_INDICES))
                     if usable[i]], dtype=int
                )
                if achrom.size >= 5:
                    model, plane_note = _fit_patch_plane(
                        obs_raw[achrom], ref_all[achrom], xy[achrom], flat_field
                    )
                    note = "; ".join(filter(None, [note, plane_note]))
                    if model is not None:
                        out.flat_field_source = "patches"
                else:
                    note = "; ".join(filter(None, [
                        note,
                        f"only {achrom.size} usable achromatic patches (needs 5); no "
                        "spatial correction is possible from the ring either",
                    ]))

        if note:
            out.warnings.append(note)

        if model is None:
            out.warnings.append(
                f"only {n_usable} usable patches and no usable white field; skipped the "
                "flat-field correction entirely - any illumination gradient or vignetting "
                "will bias the reading"
            )
        else:
            out.flat_field_mode = flat_field
            xy_eval = np.vstack([np.zeros((1, 2)), xy, probe_xy])
            out.gradient_percent = _gradient_percent(model, xy_eval)
            if out.gradient_percent > max_gradient_percent:
                out.reason = (
                    f"illumination varies {out.gradient_percent:.0f}% across the badge "
                    f"(limit {max_gradient_percent:.0f}%) - that is a shadow edge or a "
                    "specular streak, not a smooth gradient. Move out of the hard light "
                    "and retake."
                )
                return out

    obs_all = obs_raw / np.maximum(_flat_field_gains(model, xy), 1e-6)

    obs = obs_all[usable]
    ref = ref_all[usable]

    # ---- pick the richest CCM the surviving patches can support --------------
    ladder = {"root6": 6, "affine": 4, "linear": 3}
    order = [m for m in ("root6", "affine", "linear")
             if ladder[m] <= ladder.get(mode, 6)] or ["linear"]
    chosen = None
    for cand in order:
        # need at least one spare patch so the fit is not exactly determined
        if n_usable >= ladder[cand] + 1:
            chosen = cand
            break

    pad_linear_raw = samples.pad.mean_linear

    if chosen is not None:
        M = solve_ccm(obs, ref, mode=chosen, ridge=ridge)
        F = ccm_feature_matrix(obs, chosen)
        out.condition_number = float(np.linalg.cond(F.T @ F + ridge * np.eye(F.shape[1])))
        out.mode, out.matrix = chosen, M

        pred = apply_ccm(obs, M, mode=chosen)
        fit_res = delta_e_ciede2000(
            xyz_to_lab(linear_rgb_to_xyz(pred)), xyz_to_lab(linear_rgb_to_xyz(ref))
        )
        out.fit_residual_mean = float(np.mean(fit_res))

        loo, loo_l = _loo_residuals(obs, ref, chosen, ridge)
        if np.all(np.isnan(loo)):
            out.warnings.append(
                "too few patches for leave-one-out validation; "
                "reporting training residual instead"
            )
            loo = np.atleast_1d(np.asarray(fit_res, dtype=np.float64)).copy()
            loo_l = np.full_like(loo, np.nan)
            out.loo_residual_mean = out.fit_residual_mean
            out.loo_residual_max = float(np.max(fit_res))
        else:
            out.loo_residual_mean = float(np.nanmean(loo))
            out.loo_residual_max = float(np.nanmax(loo))

        # Locus-weighted residuals: the same numbers, asked the useful question. Weights come
        # from the *reference* colours, never from the observed ones, so a bad scan cannot
        # reweight its way to a good score.
        ref_lab = np.array([xyz_to_lab(linear_rgb_to_xyz(v)) for v in ref])
        weights, locus_dist = _locus_weights(ref_lab)
        w = np.where(np.isfinite(loo), weights, 0.0)
        if w.sum() > 1e-9:
            out.locus_residual = float(
                np.sum(w * np.nan_to_num(loo)) / w.sum()
            )
        # The lightness bias is the one matched to the reading: signed, so systematic
        # darkening or lightening of the near-locus patches shows up as a bias with a
        # direction rather than being averaged away.
        wl = np.where(np.isfinite(loo_l), weights, 0.0)
        if wl.sum() > 1e-9:
            out.locus_l_bias = float(np.sum(wl * np.nan_to_num(loo_l)) / wl.sum())

        names = [PATCH_NAMES[i] for i in np.flatnonzero(usable)]
        out.used_patches = tuple(names)
        out.patch_residuals = {
            nm: (float(f), float(l)) for nm, f, l in zip(names, np.atleast_1d(fit_res), loo)
        }
        out.locus_weights = {
            nm: (round(float(wt), 4), round(float(d), 2))
            for nm, wt, d in zip(names, weights, locus_dist)
        }
        pad_corrected = apply_ccm(pad_linear_raw, M, mode=chosen)
        patches_corrected = apply_ccm(obs_all, M, mode=chosen)

    else:
        # ---- last resort: diagonal grey balance -----------------------------
        neutrals = [i for i in NEUTRAL_INDICES if usable[i]]
        if not neutrals:
            out.reason = (
                f"only {n_usable} usable reference patches and no readable neutral - "
                "cannot correct illumination; reject scan"
            )
            return out
        gain = von_kries_gain(obs_all[neutrals], ref_all[neutrals])
        out.mode, out.matrix = "vonkries", gain
        out.warnings.append(
            f"degraded to von Kries grey balance on {len(neutrals)} neutral patch(es); "
            "colour cast removed but sensor cross-talk uncorrected"
        )
        pad_corrected = pad_linear_raw * gain
        patches_corrected = obs_all * gain
        out.used_patches = tuple(PATCH_NAMES[i] for i in neutrals)

    # ---- pad and baseline in L*a*b* -----------------------------------------
    out.pad_linear = np.asarray(pad_corrected, dtype=np.float64)
    out.pad_lab = xyz_to_lab(linear_rgb_to_xyz(out.pad_linear))

    # The baseline is the MEAN of the two diametrically-opposite substrate patches, and the
    # mean is taken in **linear light**, not in L*a*b*. Two reasons, and both are the same
    # reason really: radiance is what adds, so the average of two linear samples is the
    # radiance at their midpoint - which is the pad centre. Averaging L* values instead
    # would average through a cube root and land somewhere slightly darker than the true
    # midpoint, reintroducing a fraction of the very bias this pairing exists to remove.
    subs = [i for i in SUBSTRATE_PATCH_INDICES if usable[i]]
    if baseline_mode == "onbadge" and subs:
        out.baseline_lab = xyz_to_lab(
            linear_rgb_to_xyz(np.mean(patches_corrected[subs], axis=0))
        )
        names = "+".join(PATCH_NAMES[i] for i in subs)
        out.baseline_source = f"onbadge:{names}"
        if len(subs) < len(SUBSTRATE_PATCH_INDICES):
            out.warnings.append(
                f"only {len(subs)} of {len(SUBSTRATE_PATCH_INDICES)} substrate patches "
                "usable; the opposite-pair cancellation of illumination gradients is lost, "
                "so the reading carries whatever ramp the flat field did not remove"
            )
    else:
        out.baseline_lab = np.asarray(UNEXPOSED_PAD_LAB, dtype=np.float64)
        out.baseline_source = "constant:UNEXPOSED_PAD_LAB"
        if baseline_mode == "onbadge":
            # THE COLLAPSE GATE. This is a rejection and not a warning, and it is the only
            # colour rejection in this function, because it is the only condition measured to
            # separate a scan that reads correctly from one that reads by a factor of two.
            #
            # The dose is a *difference* between the pad and the substrate patches in the same
            # frame under the same light. That differencing is why a scan whose absolute
            # colour fit is 18 dE00 wrong still reads to +3.0%: almost all of the error is
            # common to both terms and cancels. Lose the on-badge baseline - here because
            # monochromatic light clipped both substrate patches - and the pad is being
            # compared against a constant that was never photographed under this illuminant.
            # The cancellation is gone and nothing bounds the error.
            #
            # Measured over 110 scans (2 doses x 11 illuminants x 5 cameras): the 104 that
            # kept the on-badge baseline had |error| rms 3.38% and worst 14.62%. The 6 that
            # fell through to here had rms 90.53% and worst 151.43% - and ranged from +1.6%
            # to +151%, which is the point. The failure is not graded, so no threshold on any
            # error-correlated diagnostic can find it; it is structural, so a boolean does.
            # For the diagnostics that were tried and rejected see ``warn_loo_residual``.
            out.reason = (
                "the reference patches the reading is measured against are unusable, so the "
                "pad has nothing in this photograph to be compared with. Almost always "
                "blown-out highlights: move out of the direct glare, or step away from the "
                "sodium lamp and use the torch as the main light. Passing "
                "baseline_mode='constant' explicitly will read it anyway, but the result is "
                "not defensible as an exposure record."
            )
            return out

    # ---- the observables ----------------------------------------------------
    # Three numbers from one displacement vector, each answering a different question:
    #   delta_l_star     how much has it darkened          -> the dose
    #   chroma_residual  did it darken the RIGHT WAY        -> is this H2S at all
    #   delta_e00        total perceptual difference        -> the record
    out.delta_l_star = float(out.baseline_lab[0] - out.pad_lab[0])
    out.locus_projection = locus_projection(out.pad_lab, out.baseline_lab)
    out.chroma_residual = locus_chroma_residual(out.pad_lab, out.baseline_lab)
    out.delta_e00 = float(delta_e_ciede2000(out.baseline_lab, out.pad_lab))

    # ---- gate ---------------------------------------------------------------
    if not np.isfinite(out.delta_l_star):
        out.reason = "the pad's lightness change is not finite; corrupt sample"
        return out
    if np.isfinite(out.loo_residual_mean) and out.loo_residual_mean > warn_loo_residual:
        out.warnings.append(
            f"colour correction is poor: mean leave-one-out residual "
            f"{out.loo_residual_mean:.1f} dE00 > {warn_loo_residual:.0f}. The light is "
            "narrow-band or strongly tinted. The reading stands - it is a difference against "
            "patches in the same frame, so most of this error cancels - but switch the torch "
            "on if you want a defensible number."
        )

    # Deliberately a warning and not a rejection - see warn_locus_residual in the docstring
    # for the measurement. A poor fit near the pad's tone is worth recording against the
    # scan, but rejecting on it discarded better-than-average scans without ever removing
    # the worst one.
    if np.isfinite(out.locus_residual) and out.locus_residual > warn_locus_residual:
        out.warnings.append(
            f"colour correction is weak near the pad's own tone: locus-weighted residual "
            f"{out.locus_residual:.2f} dE00 > {warn_locus_residual:.1f}. The reading stands, "
            "but even light or a rescan would make it more defensible."
        )

    out.ok = True
    out.reason = "ok"
    return out
