"""
Colorimetry core for SIH26118 - Passive Colorimetric H2S Dosimeter.

Everything in this module is pure numpy (no scipy / skimage / colour-science) so the
engine runs on a bare `pip install numpy opencv-python` and cannot break on hackathon wifi.

Pipeline of colour spaces used by the reader:

    camera sRGB (0..255)
        -> linear sRGB            (inverse EOTF / "de-gamma")
        -> corrected linear sRGB  (colour-correction matrix from on-badge patches)
        -> CIE XYZ (D65)
        -> CIE L*a*b* (D65, 2 deg observer)
        -> CIEDE2000 dE00 vs unexposed baseline

Why not RGB distance: an 8-bit RGB Euclidean distance mixes illumination, camera white
balance and chemistry into one number. L*a*b* is device independent and perceptually
near-uniform, and CIEDE2000 additionally compensates lightness/chroma/hue non-uniformity,
which is exactly the regime PbS browning lives in (large -dL*, moderate +b*).

All functions are vectorised: inputs may be shape (3,), (N,3) or (H,W,3).

References
----------
[1] CIE 142-2001 / Sharma, Wu, Dalal (2005), "The CIEDE2000 color-difference formula:
    implementation notes, supplementary test data, and mathematical observations",
    Color Research & Application 30(1), 21-30.
[2] IEC 61966-2-1:1999 (sRGB) transfer function and primaries.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "D65_WHITE_XYZ",
    "SRGB_TO_XYZ",
    "XYZ_TO_SRGB",
    "srgb_to_linear",
    "linear_to_srgb",
    "linear_rgb_to_xyz",
    "xyz_to_linear_rgb",
    "xyz_to_lab",
    "lab_to_xyz",
    "srgb_to_lab",
    "lab_to_srgb",
    "lab_to_lch",
    "delta_e_ciede2000",
    "delta_e_76",
    "delta_l_star",
    "darkening_metrics",
    "channel_balance",
    "narrowband_check",
    "CHANNEL_BALANCE_WARN",
    "CHANNEL_BALANCE_REJECT",
    "von_kries_gain",
    "solve_ccm",
    "apply_ccm",
    "ccm_feature_matrix",
    "CCM_MODES",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# CIE 1931 2-degree standard observer, D65 illuminant, Y normalised to 100.
D65_WHITE_XYZ = np.array([95.047, 100.000, 108.883], dtype=np.float64)

# sRGB (IEC 61966-2-1) linear RGB -> CIE XYZ, D65. Rows sum to the D65 white point.
SRGB_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ],
    dtype=np.float64,
)

XYZ_TO_SRGB = np.linalg.inv(SRGB_TO_XYZ)

# CIE L*a*b* companding constants (exact rational forms, not the 0.008856/7.787
# truncations - those introduce a small discontinuity at the knee).
_LAB_EPS = 216.0 / 24389.0          # 0.008856451679...
_LAB_KAPPA = 24389.0 / 27.0         # 903.2962962...

_POW25_7 = 25.0 ** 7


# ---------------------------------------------------------------------------
# sRGB transfer function
# ---------------------------------------------------------------------------

def srgb_to_linear(rgb, max_value: float = 255.0):
    """sRGB -> linear-light RGB in 0..1.

    Parameters
    ----------
    rgb : array_like
        Encoded sRGB values in ``0..max_value``.
    max_value : float
        Full-scale encoding. Use ``255.0`` for 8-bit camera data (the default) and
        ``1.0`` for already-normalised floats.

    Notes
    -----
    ``max_value`` is explicit **on purpose**. An earlier version guessed the scale by
    testing ``max(rgb) > 1``, which silently misreads 8-bit near-black colours: the
    8-bit triplet ``(1, 0, 0)`` has a maximum of 1.0 and would be decoded as
    full-scale red, a 79 dE error. Never reintroduce that heuristic.

    The piecewise sRGB EOTF is used (not a plain 2.2 gamma) because the linear toe
    matters for the dark, fully-reacted PbS pad where L* < 30.
    """
    a = np.asarray(rgb, dtype=np.float64) / float(max_value)
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(linear, max_value: float = 1.0):
    """Linear-light RGB (0..1) -> encoded sRGB in ``0..max_value``."""
    a = np.clip(np.asarray(linear, dtype=np.float64), 0.0, 1.0)
    out = np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1.0 / 2.4) - 0.055)
    return np.clip(out, 0.0, 1.0) * float(max_value)


# ---------------------------------------------------------------------------
# XYZ <-> linear RGB
# ---------------------------------------------------------------------------

def linear_rgb_to_xyz(linear):
    """Linear sRGB (0..1) -> CIE XYZ with Y in 0..100."""
    a = np.asarray(linear, dtype=np.float64)
    return a @ SRGB_TO_XYZ.T * 100.0


def xyz_to_linear_rgb(xyz):
    """CIE XYZ (Y in 0..100) -> linear sRGB (0..1, unclipped so gamut errors stay visible)."""
    a = np.asarray(xyz, dtype=np.float64) / 100.0
    return a @ XYZ_TO_SRGB.T


# ---------------------------------------------------------------------------
# XYZ <-> L*a*b*
# ---------------------------------------------------------------------------

def xyz_to_lab(xyz, white=None):
    """CIE XYZ (Y in 0..100) -> CIE L*a*b* under ``white`` (default D65)."""
    w = D65_WHITE_XYZ if white is None else np.asarray(white, dtype=np.float64)
    r = np.asarray(xyz, dtype=np.float64) / w
    f = np.where(r > _LAB_EPS, np.cbrt(np.maximum(r, 0.0)), (_LAB_KAPPA * r + 16.0) / 116.0)
    fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
    return np.stack(
        [116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)], axis=-1
    )


def lab_to_xyz(lab, white=None):
    """CIE L*a*b* -> CIE XYZ (Y in 0..100). Inverse of :func:`xyz_to_lab`."""
    w = D65_WHITE_XYZ if white is None else np.asarray(white, dtype=np.float64)
    a = np.asarray(lab, dtype=np.float64)
    L, A, B = a[..., 0], a[..., 1], a[..., 2]
    fy = (L + 16.0) / 116.0
    fx = fy + A / 500.0
    fz = fy - B / 200.0
    def _inv(t, is_y, Lv):
        t3 = t ** 3
        if is_y:
            return np.where(Lv > _LAB_KAPPA * _LAB_EPS, t3, Lv / _LAB_KAPPA)
        return np.where(t3 > _LAB_EPS, t3, (116.0 * t - 16.0) / _LAB_KAPPA)
    xr = _inv(fx, False, L)
    yr = _inv(fy, True, L)
    zr = _inv(fz, False, L)
    return np.stack([xr, yr, zr], axis=-1) * w


def srgb_to_lab(rgb, max_value: float = 255.0):
    """Convenience: encoded sRGB -> CIE L*a*b*, D65. See :func:`srgb_to_linear`."""
    return xyz_to_lab(linear_rgb_to_xyz(srgb_to_linear(rgb, max_value=max_value)))


def lab_to_srgb(lab, max_value: float = 255.0):
    """Convenience: CIE L*a*b* -> encoded sRGB. Used by the badge renderer / simulator."""
    return linear_to_srgb(xyz_to_linear_rgb(lab_to_xyz(lab)), max_value=max_value)


def lab_to_lch(lab):
    """CIE L*a*b* -> L*, C*, h (h in degrees 0..360). Handy for diagnostics."""
    a = np.asarray(lab, dtype=np.float64)
    C = np.hypot(a[..., 1], a[..., 2])
    h = np.degrees(np.arctan2(a[..., 2], a[..., 1])) % 360.0
    return np.stack([a[..., 0], C, h], axis=-1)


# ---------------------------------------------------------------------------
# Colour difference
# ---------------------------------------------------------------------------

def delta_e_76(lab1, lab2):
    """CIE76 dEab. Kept only as a baseline to show why CIEDE2000 is needed."""
    d = np.asarray(lab1, dtype=np.float64) - np.asarray(lab2, dtype=np.float64)
    return np.sqrt(np.sum(d * d, axis=-1))


def delta_e_ciede2000(lab1, lab2, kL: float = 1.0, kC: float = 1.0, kH: float = 1.0):
    """CIEDE2000 colour difference dE00 between two L*a*b* arrays.

    Implements CIE 142-2001 exactly as specified in Sharma, Wu & Dalal (2005),
    including the three cases that naive implementations get wrong:

    1. ``h_bar'`` has FOUR branches, not two. When ``|h1'-h2'| > 180`` the mean hue
       depends on whether ``h1'+h2'`` is below or above 360 degrees; collapsing this to
       ``(h1'+h2'+360)/2`` produces errors of several dE units near the hue origin.
    2. When either chroma is zero (``C1'*C2' == 0``) both ``dh'`` and ``dH'`` are defined
       as 0 and ``h_bar' = h1'+h2'``; ``arctan2`` alone gives a spurious hue term for
       neutral patches - and the unexposed lead-acetate pad is very nearly neutral.
    3. ``G`` and hence ``a'`` use the *unprimed* mean chroma, while ``S_C``, ``S_H`` and
       ``R_C`` use the *primed* mean chroma.

    Parameters
    ----------
    lab1, lab2 : array_like
        L*a*b* triplets, broadcastable, shape (..., 3).
    kL, kC, kH : float
        Parametric weighting factors. Reference conditions (and this project) use 1.0.

    Returns
    -------
    ndarray or float
        dE00, shape ``lab1.shape[:-1]``. A 0-d result is returned as a Python float.
    """
    l1 = np.asarray(lab1, dtype=np.float64)
    l2 = np.asarray(lab2, dtype=np.float64)
    L1, a1, b1 = l1[..., 0], l1[..., 1], l1[..., 2]
    L2, a2, b2 = l2[..., 0], l2[..., 1], l2[..., 2]

    # --- chroma and the a* axis stretch G (uses UNPRIMED mean chroma) -------
    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    C_bar = 0.5 * (C1 + C2)
    C_bar7 = C_bar ** 7
    G = 0.5 * (1.0 - np.sqrt(C_bar7 / (C_bar7 + _POW25_7)))

    a1p = (1.0 + G) * a1
    a2p = (1.0 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)

    # --- hue angles; defined as 0 for neutral colours ----------------------
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360.0
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360.0
    h1p = np.where(C1p == 0.0, 0.0, h1p)
    h2p = np.where(C2p == 0.0, 0.0, h2p)

    chroma_product_zero = (C1p * C2p) == 0.0

    # --- differences -------------------------------------------------------
    dLp = L2 - L1
    dCp = C2p - C1p

    dh = h2p - h1p
    dhp = np.where(
        chroma_product_zero,
        0.0,
        np.where(np.abs(dh) <= 180.0, dh, np.where(dh > 180.0, dh - 360.0, dh + 360.0)),
    )
    dHp = 2.0 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp) / 2.0)

    # --- means -------------------------------------------------------------
    L_bar = 0.5 * (L1 + L2)
    C_barp = 0.5 * (C1p + C2p)

    h_sum = h1p + h2p
    h_absdiff = np.abs(h1p - h2p)
    h_barp = np.where(
        chroma_product_zero,
        h_sum,                                   # case 2
        np.where(
            h_absdiff <= 180.0,
            0.5 * h_sum,
            np.where(h_sum < 360.0, 0.5 * (h_sum + 360.0), 0.5 * (h_sum - 360.0)),
        ),
    )

    # --- weighting functions ----------------------------------------------
    T = (
        1.0
        - 0.17 * np.cos(np.radians(h_barp - 30.0))
        + 0.24 * np.cos(np.radians(2.0 * h_barp))
        + 0.32 * np.cos(np.radians(3.0 * h_barp + 6.0))
        - 0.20 * np.cos(np.radians(4.0 * h_barp - 63.0))
    )
    dL50 = L_bar - 50.0
    S_L = 1.0 + (0.015 * dL50 * dL50) / np.sqrt(20.0 + dL50 * dL50)
    S_C = 1.0 + 0.045 * C_barp
    S_H = 1.0 + 0.015 * C_barp * T

    # --- rotation term (blue/purple region) --------------------------------
    d_theta = 30.0 * np.exp(-(((h_barp - 275.0) / 25.0) ** 2))
    C_barp7 = C_barp ** 7
    R_C = 2.0 * np.sqrt(C_barp7 / (C_barp7 + _POW25_7))
    R_T = -np.sin(np.radians(2.0 * d_theta)) * R_C

    tL = dLp / (kL * S_L)
    tC = dCp / (kC * S_C)
    tH = dHp / (kH * S_H)

    de = np.sqrt(np.maximum(tL * tL + tC * tC + tH * tH + R_T * tC * tH, 0.0))
    return float(de) if np.ndim(de) == 0 else de


# ---------------------------------------------------------------------------
# The darkening pair: -dL* leads, dE00 accompanies
# ---------------------------------------------------------------------------

def delta_l_star(pad_lab, baseline_lab):
    """``-dL*``: how much lightness the pad has LOST against its baseline.

    Sign convention is fixed here once so nothing downstream has to remember it: the
    return is **positive when the pad has darkened**, because that is the direction the
    chemistry runs and a dose must not come out negative for a working badge.

    This is the primary darkening metric for the whole instrument. It is not a stylistic
    preference - see :func:`darkening_metrics` for the measurement that put it ahead of
    dE00, and :mod:`engine.dosimetry` for why dE00 in particular loses.
    """
    p = np.asarray(pad_lab, dtype=np.float64)
    b = np.asarray(baseline_lab, dtype=np.float64)
    d = b[..., 0] - p[..., 0]
    return float(d) if np.ndim(d) == 0 else d


def darkening_metrics(pad_lab, baseline_lab) -> dict:
    """Both darkening metrics for one pad/baseline pair, with the primary named.

    WHY TWO NUMBERS AND NOT ONE
    ---------------------------
    They are reported together because they fail in different ways, and a reading is more
    trustworthy when they agree.

    ``delta_l_star`` (**primary, drives the dose**) is the pad's loss of lightness. The
    PbS reaction path is 97% pure lightness, so this observable carries essentially all of
    the signal and none of the camera's residual chroma error.

    ``delta_e00`` (**secondary, recorded**) is CIEDE2000 against the same baseline: the
    conventional colorimetric figure, the one the printed patch tolerances are specified
    in, and the one a colour scientist on the jury will ask for. It is stored on every
    scan and shown next to the dose. It does not compute the dose.

    Measured over 40 camera x illuminant combinations at a known 8 ppm*hr, error in the
    recovered dose:

        observable        rms error    worst case
        -dL*                 4.9%        14.8%
        dE00                11.6%        40.4%

    ``ratio`` is ``-dL* / dE00``, and it is a *plausibility band only*. Measured along the
    genuine reaction path it runs 1.55 at 1 ppm*hr down to 1.22 at 120 ppm*hr. It is above
    1 rather than at it because CIEDE2000's ``S_L`` grows away from L* 50, and this pad
    lives at L* 88 down to L* 44, so dE00 divides the lightness term by roughly 1.2-1.6 and
    comes out *smaller* than the raw lightness drop.

    It is tempting to read a low ratio as "the pad moved sideways, so this is contamination",
    and that does not survive measurement: at the -dL* of a 25 ppm*hr badge (13.19), four
    simulated contaminants gave ratios of 1.20 (rust), 1.27 (mould), 1.36 (oxidised) and
    1.38 (wet membrane) against the genuine 1.46 - inside the range the genuine path itself
    covers across doses. Contamination is detected by
    :func:`engine.dosimetry.locus_chroma_residual` against a dose-scaled limit, which knows
    the locus geometry; this ratio is only good for catching a gross blunder, a swapped
    baseline, a sign error or a unit mix-up, where it leaves the 0.9-1.7 band entirely.
    NaN when dE00 is ~0, which is the right answer for an unexposed badge rather than a
    division blow-up.
    """
    dl = float(delta_l_star(pad_lab, baseline_lab))
    de = float(delta_e_ciede2000(np.asarray(baseline_lab, dtype=np.float64),
                                 np.asarray(pad_lab, dtype=np.float64)))
    return {
        "primary": "delta_l_star",
        "delta_l_star": dl,
        "delta_e00": de,
        "ratio": (dl / de) if de > 1e-6 else float("nan"),
    }


# ---------------------------------------------------------------------------
# Illuminant condition check: is there enough spectrum to read a colour at all?
# ---------------------------------------------------------------------------

#: Below this channel balance the light is losing a colour axis and the scan carries a
#: warning telling the operator to switch the phone torch on. 0.30 from measurement, and it
#: is a genuine gap rather than a tuned number - see :func:`narrowband_check`.
CHANNEL_BALANCE_WARN = 0.30

#: Rejection threshold, and it ships **disabled (0.0)** on purpose. A hard refusal on this
#: statistic was tried at 0.05 and does not survive measurement - it discards accurate
#: readings and catches nothing the structural baseline gate in
#: :func:`engine.normalize.normalize_badge` does not already catch. See the FALSIFIED
#: section of :func:`narrowband_check` for the numbers. A site whose policy is "no reading
#: at all under a sodium lamp" can set it to 0.05 explicitly; the engine will not do it
#: unasked, because refusing to measure is itself a safety cost.
CHANNEL_BALANCE_REJECT = 0.0


def channel_balance(observed_linear, eps: float = 1e-9) -> float:
    """Weakest / strongest mean colour channel over a set of observed patches, 0..1.

    A one-line measure of whether the illuminant actually contains the spectrum needed to
    do colorimetry. Computed on the *observed* linear patch values before any correction,
    which is the point: it must be able to declare the light unusable without first
    trusting a colour fit made under that light.

    1.0 means the three channels carry comparable signal. Towards 0 means one channel is
    dark - the badge is lit by something with a hole in its spectrum where that channel
    looks, and any matrix fitted here has to invent the missing axis from noise.
    """
    a = np.atleast_2d(np.asarray(observed_linear, dtype=np.float64))
    if a.size == 0:
        return float("nan")
    level = np.nanmean(a, axis=0)
    hi = float(np.nanmax(level))
    if not np.isfinite(hi) or hi <= eps:
        return 0.0
    return float(max(np.nanmin(level), 0.0) / hi)


def narrowband_check(observed_linear,
                     warn: float = CHANNEL_BALANCE_WARN,
                     reject: float = CHANNEL_BALANCE_REJECT) -> tuple:
    """Is this light broadband enough to read the badge under? Returns ``(level, balance, msg)``.

    ``level`` is ``'ok'``, ``'warn'`` or ``'reject'``; ``balance`` is
    :func:`channel_balance`; ``msg`` is written for the person holding the phone.
    ``'reject'`` is only ever returned if the caller opts in by passing ``reject > 0``, which
    the shipped configuration does not - see the FALSIFIED section below.

    THE FAILURE THIS EXISTS FOR
    ---------------------------
    Refineries are lit at night by high- and low-pressure sodium lamps. Low-pressure sodium
    is very nearly monochromatic at 589 nm: it emits essentially no blue and no green. Every
    patch on the badge then reflects the same narrow band, so all twelve report almost the
    same chromaticity no matter what ink is on them, the colour-correction regression goes
    rank-deficient, and the matrix fills the missing axes with sensor noise. The phone torch
    fixes it completely - it is a broadband white LED, and if it dominates the exposure the
    badge is being read under the torch's spectrum rather than the lamp's.

    WHY CHANNEL BALANCE AND NOT CHROMATICITY SPREAD
    ----------------------------------------------
    Spread of the patch chromaticities is the more obvious statistic - it is the rank
    deficiency measured directly - and it was tried first and does not work. Over 33 scans
    (11 illuminants x 3 cameras) the sodium cases spanned 0.370-0.490 and everything else
    0.370-0.485: complete overlap. The reason is instructive: a camera with exact sRGB
    primaries recovers the original chromaticities even under sodium, because a per-channel
    illuminant multiplication followed by an exact white balance cancels. The spread only
    collapses once the sensor's real, overlapping spectral responses smear the narrow line -
    so the statistic is measuring the *camera*, not the light.

    Channel balance separates cleanly, and by a wide margin::

        illuminant / camera             balance    dose error   required
        fluorescent_4000 / budget        0.417        +8.8%      keep  <- worst legitimate
        incandescent_2856 / budget       0.489       +11.6%      keep
        hps  (torch off) / flagship      0.215        -0.3%      warn
        lps  (torch off) / flagship      0.197       +10.0%      warn
        hps  (torch off) / budget        0.0063     +151.4%      reject
        lps  (torch off) / budget        0.0081     +119.3%      reject

    So ``warn`` sits at 0.30, the geometric midpoint of the 0.215-0.417 gap, giving 1.4x
    headroom on both sides. Note incandescent at 0.489 - a warm broadband lamp with a weak
    blue channel is *not* narrow-band and stays usable, reading to +11.6%. That distinction
    is the whole job of this function, and it is why the threshold cannot simply be "is the
    blue channel low".

    FALSIFIED: THIS MUST NOT BE A REJECTION
    ---------------------------------------
    A hard reject at 0.05 was implemented, measured, and removed. Two reasons, both from
    data.

    First, it discards accurate readings. ``hps / midrange_a`` sits at balance **0.0040** -
    the blue channel is four parts in a thousand - and reads **-2.88%** at 8 ppm*hr and
    **+0.09%** at 25. It is not lucky: the pad and its substrate baseline are photographed in
    the same frame under the same light, ``-dL*`` is a *difference* between them, and the
    lightness of both is carried by the channel that sodium light does illuminate. Rejecting
    it refuses a measurement that was, in fact, correctly performed.

    Second, the catastrophic sodium cases are not distinguished by balance at all. At the same
    ~0.004-0.008 balance, ``hps/midrange_a`` reads -2.9% while ``hps/budget`` reads **+151%**.
    What separates them is whether the substrate baseline survived: the accurate one kept
    ``onbadge:SUBSTRATE_A+SUBSTRATE_B``, the catastrophic ones fell through to the factory
    constant. That is the structural collapse gate in
    :func:`engine.normalize.normalize_badge`, it catches every catastrophic case, and it needs
    no threshold. This check adds nothing on top of it except a lost good scan.

    A third justification was attempted and also failed. It looked as though a rejection could
    be defended on integrity grounds instead of accuracy grounds - under near-monochromatic
    light the recovered a*/b* axes are noise, so a contaminated pad might pass the chroma check
    and be reported as a genuine exposure. That does happen (at ``hps/midrange_a`` an oxidised
    pad reports chroma residual 1.87 against a 3.96 limit and is called CRITICAL rather than
    SUSPECT, where under D65 the same pad gives 9.86 and is caught). But balance does not
    predict it: ``incandescent_2856/budget`` at balance **0.49** - broadband, high balance,
    nothing to warn about - catches only **1 of 3** contaminants, while ``hps/flagship`` at
    balance **0.21** catches **2 of 3**. Contamination sensitivity is limited everywhere, which
    :func:`engine.dosimetry.chroma_limit` already states plainly in its own limits section; it
    is not a function of this statistic and cannot be used to set a threshold on it.

    So this is the sixth diagnostic in this instrument measured as a candidate rejection gate
    and kept as a warning instead, for the reason that recurs throughout: the reading is
    differential, so absolute light quality is a poor predictor of its error.

    WHAT THE WARNING IS STILL FOR
    -----------------------------
    It is the one diagnostic here that names an action the operator can actually take. Under
    torch-off sodium, balance runs 0.004-0.215; switch the torch on and the same lamps give
    **0.533-0.718**, with dose errors of -2.29% to +2.70%. The warning tells the person
    holding the phone to do the single thing that moves their scan from the ragged end of the
    range to the middle of it, and it records in the audit trail whether they did.

    It says nothing about a *dim* broadband light. Twilight at low lux reads fine here
    (balance 0.81) and is handled by the exposure and noise gates instead.
    """
    b = channel_balance(observed_linear)
    if not np.isfinite(b):
        return "ok", b, ""
    if reject > 0.0 and b < reject:
        return "reject", b, (
            f"the light has essentially no signal in one colour channel (channel balance "
            f"{b:.3f}, limit {reject:.2f}) - this is a low-pressure sodium lamp or similar "
            "near-monochromatic source. Switch the phone torch on and shade the badge from "
            "the lamp with your body so the torch is the main light, then retake."
        )
    if b < warn:
        return "warn", b, (
            f"light is narrow-band (channel balance {b:.3f} < {warn:.2f}): one colour "
            "channel is very weak, most likely a sodium lamp. The reading stands, but "
            "switch the torch on - it is broadband and makes the number defensible."
        )
    return "ok", b, ""


# ---------------------------------------------------------------------------
# Illumination / camera normalisation
# ---------------------------------------------------------------------------

def von_kries_gain(observed_linear, reference_linear, eps: float = 1e-6):
    """Per-channel diagonal gain mapping ``observed`` neutrals onto ``reference``.

    This is the cheap fallback used when only the grey patches are readable
    (e.g. badge partly occluded). It removes illuminant colour cast but cannot
    correct camera cross-talk, so :func:`solve_ccm` is preferred.
    """
    obs = np.asarray(observed_linear, dtype=np.float64)
    ref = np.asarray(reference_linear, dtype=np.float64)
    if obs.ndim == 2:                      # several neutrals -> use their means
        obs = obs.mean(axis=0)
        ref = ref.mean(axis=0)
    return ref / np.maximum(obs, eps)


CCM_MODES = ("linear", "affine", "root6")


def ccm_feature_matrix(linear_rgb, mode: str = "root6"):
    """Expand linear RGB into the regression features for a given CCM ``mode``.

    ``linear``  : [R, G, B]                          -> plain 3x3 matrix
    ``affine``  : [R, G, B, 1]                       -> 3x3 plus offset (handles veiling glare)
    ``root6``   : [R, G, B, sqrt(RG), sqrt(GB), sqrt(RB)]

    ``root6`` is Finlayson's root-polynomial expansion. Every term is homogeneous of
    degree 1, so the fit is **exposure invariant**: doubling scene brightness scales all
    features equally and the same matrix still applies. That property is the reason it is
    the default here - a worker holding the badge closer to a lamp changes exposure, and a
    plain polynomial expansion (R^2, RG, ...) would silently mis-correct.
    """
    a = np.atleast_2d(np.asarray(linear_rgb, dtype=np.float64))
    R, G, B = a[:, 0], a[:, 1], a[:, 2]
    if mode == "linear":
        return a
    if mode == "affine":
        return np.column_stack([R, G, B, np.ones_like(R)])
    if mode == "root6":
        return np.column_stack(
            [R, G, B, np.sqrt(np.maximum(R * G, 0.0)),
             np.sqrt(np.maximum(G * B, 0.0)), np.sqrt(np.maximum(R * B, 0.0))]
        )
    raise ValueError(f"unknown CCM mode {mode!r}; expected one of {CCM_MODES}")


def solve_ccm(observed_linear, reference_linear, mode: str = "root6", ridge: float = 1e-4):
    """Least-squares colour-correction matrix mapping observed -> reference linear RGB.

    Solved as ridge-regularised normal equations ``M = (F'F + lam*I)^-1 F' Y`` where ``F``
    is the feature expansion of the *observed* on-badge patches and ``Y`` the
    manufacturer-known reference values. Ridge is not cosmetic: the printed patch set is
    small (12) and under a narrow-band illuminant such as a 2200 K sodium lamp the feature
    matrix becomes ill-conditioned, at which point an unregularised fit will happily
    amplify sensor noise into a 5 dE error on the pad.

    Returns
    -------
    M : ndarray, shape (n_features, 3)
        Apply with :func:`apply_ccm`.
    """
    F = ccm_feature_matrix(observed_linear, mode)
    Y = np.atleast_2d(np.asarray(reference_linear, dtype=np.float64))
    if F.shape[0] != Y.shape[0]:
        raise ValueError(f"patch count mismatch: {F.shape[0]} observed vs {Y.shape[0]} reference")
    if F.shape[0] < F.shape[1]:
        raise ValueError(
            f"CCM mode {mode!r} needs >= {F.shape[1]} patches, got {F.shape[0]}"
        )
    A = F.T @ F + ridge * np.eye(F.shape[1])
    return np.linalg.solve(A, F.T @ Y)


def apply_ccm(linear_rgb, M, mode: str = "root6"):
    """Apply a matrix from :func:`solve_ccm`. Preserves input shape."""
    a = np.asarray(linear_rgb, dtype=np.float64)
    flat = a.reshape(-1, 3)
    out = ccm_feature_matrix(flat, mode) @ M
    return out.reshape(a.shape)
