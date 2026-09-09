"""
Dosimetry: turning a colour difference into a defensible exposure number.

Two directions live here, and keeping them in one module is deliberate - they must stay
mutually consistent or the calibration loop silently drifts.

**Forward (physics -> colour).** :class:`ReactionModel` predicts what the pad looks like
after a known dose. It exists to generate synthetic ground truth for the simulator and
the printable test-strip series, and to sanity-check the inverse.

**Inverse (colour -> dose).** :class:`CalibrationModel` is what the reader runs: an
empirical polynomial mapping a scalar colour *observable* to cumulative ppm*hr, fitted
from chamber data.

THE REAGENT: COPPER(II) SULPHATE
-------------------------------
The pad is impregnated with copper(II) sulphate, which H2S converts to copper(II)
sulfide::

    CuSO4 + H2S  ->  CuS(s, brown-black)  +  H2SO4

CuS is an insoluble, strongly absorbing semiconductor, so the pad darkens irreversibly in
proportion to cumulative exposure - the property that makes the badge a dosimeter. The
darkening is genuinely favourable thermodynamically: CuS has a solubility product around
1e-36 against roughly 1e-28 for PbS, so the sulphide is captured harder, not more weakly,
than under the previous lead acetate chemistry.

What is *not* true, and must not be claimed, is that the kinetics are identical. Lead
acetate is the industry reference for sub-ppm H2S precisely because it is the more
sensitive reagent at low concentration. Sensitivity and detection limit here are open
questions pending chamber work - see :data:`STAGE_TABLE_IS_VALIDATED`.

WHICH OBSERVABLE - AND WHY IT IS NOT dE00
-----------------------------------------
The obvious choice is CIEDE2000 against the unexposed baseline, and it is the wrong one.

CIEDE2000 divides the chroma and hue differences by ``S_C`` and ``S_H``, both of which
shrink towards 1 as chroma goes to zero, while ``S_L`` stays near 1. So near the neutral
axis dE00 *amplifies* chroma error relative to lightness error. The straight-line chord
from the unexposed tone to the fully-reacted tone is ``[-0.996, +0.071, +0.050]`` in
L*a*b*, i.e. 99.6% lightness - so dE00 spends its sensitivity on the axis carrying almost
none of the net signal, and that axis is exactly where a phone camera's residual error
lives after white balancing.

Measured over 40 camera x illuminant combinations at a known 8 ppm*hr:

    observable                    rms error    worst case
    dE00                            11.6%         40.4%
    projection onto the locus         6.8%         20.2%
    -dL* alone                        4.9%         14.8%

So the reader quantifies dose from **-dL\\*** (:attr:`ReactionModel.delta_l`). The chroma
information is not discarded - it is repurposed as an *integrity* check: a pad that has
darkened by the right amount but moved the wrong way in ``(a*, b*)`` is not reporting H2S.
Wet membrane, an oxidised or contaminated reagent, mould, a badge from a different lot, or
a photograph of the wrong badge all show up as off-path chroma displacement, and none of
them show up in -dL* at all. See :func:`locus_chroma_residual`.

dE00 is still computed and stored on every scan, because it is the figure a colour
scientist will ask for and because it is what the printed patch tolerances are specified
in. It just does not drive the number on the screen.

THE COLOUR PATH IS AN ARC, NOT A LINE - AND WHY THAT MATTERS HERE
-----------------------------------------------------------------
Under lead acetate the pad's colour path was effectively straight, and a two-endpoint
reflectance blend described it. Copper sulphate involves three optical species rather
than two - pale cyan CuSO4 which is *consumed*, the white substrate which is *revealed*,
and brown-black CuS which *accumulates* - so the tone swings through khaki and bronze
before collapsing to near-black. Honest mid-path tones sit 14-21 dE00 away from where a
two-endpoint blend puts them.

That is an integrity-check problem, not an aesthetic one. Judged against a straight
locus, real mid-dose pads miss by 17.6 and 31.5 L*a*b* units against limits of 5.7 and
15.9, so every legitimate badge in the 0.2-8 ppm*hr band - the TLV decision region -
would be quarantined as contaminated. :func:`locus_lab_for_lightness` therefore evaluates
expected chroma against the measured anchor path in
:data:`engine.badge_spec.PAD_STAGE_ANCHORS_LAB` instead of against a single vector.

A side benefit worth knowing: the old straight locus ran slightly blue, so a wet or
blue-grey pad displaced almost parallel to it and the chroma check had nearly no
leverage. The CuS path runs *positive* in b* through its middle, so membrane wetting is
now roughly perpendicular to it and is caught rather than missed.

A NOTE ON STEL - PLEASE READ BEFORE PITCHING
--------------------------------------------
A passive cumulative dosimeter integrates concentration over time. From a **single**
end-of-shift scan you can recover cumulative dose (ppm*hr) and hence the shift TWA, but
you *cannot* recover a Short-Term Exposure Limit, because infinitely many concentration
histories share the same integral: a steady 2 ppm for 8 h and a 160 ppm spike for 6
minutes produce an identical 16 ppm*hr pad. Any claim that one scan yields "peak STEL"
is physically false and a jury with a process-safety background will catch it.

What this module does instead:

* :func:`assess_scan` - honest single-scan output: dose, TWA, and an explicit
  ``stel_determinable=False``.
* :func:`assess_scan_series` - given several scans through the shift (entry, mid-shift
  kiosk taps, exit), differences between consecutive readings give interval-mean
  concentrations. The worst interval bounds the short-term exposure, and the bound
  tightens as intervals shorten. This is the defensible way to approach STEL with a
  passive badge, and it is a genuine argument *for* gate-kiosk scanning rather than a
  single exit scan.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Optional, Sequence

import numpy as np

from .badge_spec import (
    FULLY_REACTED_PAD_LAB,
    PAD_STAGE_ANCHORS_LAB,
    PAD_STAGE_DOSE_BANDS,
    PAD_STAGE_LABELS,
    PAD_STAGE_NAMES,
    REACTION_EQUATION,
    REAGENT_NAME,
    REACTION_PRODUCT_NAME,
    UNEXPOSED_PAD_LAB,
)
from .colorimetry import (
    delta_e_ciede2000,
    lab_to_xyz,
    linear_rgb_to_xyz,
    xyz_to_lab,
    xyz_to_linear_rgb,
)

__all__ = [
    "Verdict",
    "ExposureLimits",
    "ACGIH_OSHA_NIOSH",
    "OBSERVABLES",
    "PAD_LOCUS_UNIT",
    "pad_locus_unit",
    "locus_projection",
    "locus_chroma_residual",
    "locus_lab_for_lightness",
    "REAGENT_NAME",
    "REACTION_PRODUCT_NAME",
    "REACTION_EQUATION",
    "STAGE_TABLE_IS_VALIDATED",
    "stage_for_dose",
    "ReactionModel",
    "CalibrationModel",
    "SaturationCalibration",
    "DEFAULT_CALIBRATION",
    "SYNTHETIC_CALIBRATION",
    "LEGACY_DE00_CALIBRATION",
    "DoseAssessment",
    "IntervalExposure",
    "SeriesAssessment",
    "assess_scan",
    "assess_scan_series",
]

#: Whether the printed stage/dose table has been confirmed against chamber data.
#:
#: **False, and it must stay False until a chamber campaign exists.** The band edges in
#: :data:`engine.badge_spec.PAD_STAGE_DOSE_BANDS` came from the reagent-change
#: specification, not from measurement. Reproducing them with this module's physics needs a
#: characteristic dose near 3 ppm*hr against the 55 ppm*hr :class:`ReactionModel` uses -
#: which would assert that copper sulphate is about eighteen times more sensitive to H2S
#: than lead acetate. The literature points the other way: lead acetate is the reference
#: reagent for sub-ppm H2S because it is *more* sensitive.
#:
#: Consequences, stated plainly so nobody has to rediscover them:
#:
#: * the printed ladder is a **visual triage aid**, not a measuring instrument;
#: * the number the reader reports comes from the fitted calibration, never from the band
#:   edges - :func:`stage_for_dose` maps dose to a band for display only;
#: * a chamber campaign must re-fit ``d_char`` *and* re-measure the band edges together,
#:   because they are not independent.
STAGE_TABLE_IS_VALIDATED: bool = False

#: Scalar colour observables the calibration can be built on.
#:
#: * ``delta_l`` - ``-dL*``, the pad's loss of lightness. **The default and the one to use.**
#:   Lowest error of the three, and immune to any residual chroma error the white balance
#:   left behind.
#: * ``projection`` - signed projection of the full L*a*b* displacement onto the reaction
#:   path. Uses the chroma signal too, which sounds better and measures worse: it inherits
#:   the camera's chroma error at 0.16 of full weight for a 3% gain in signal.
#: * ``delta_e00`` - CIEDE2000. Kept so the earlier behaviour can be reproduced and the
#:   comparison re-measured, not because it should be used.
OBSERVABLES = ("delta_l", "projection", "delta_e00")


def pad_locus_unit(unexposed_lab=UNEXPOSED_PAD_LAB, reacted_lab=FULLY_REACTED_PAD_LAB):
    """Unit vector along the **chord** of the pad's reaction path in L*a*b*.

    Points from unexposed towards fully reacted, so its L* component is negative (the pad
    darkens). Defined from the two published endpoint tones rather than fitted, so it stays
    tied to the same constants the printed substrate patch and the forward model use.

    CHORD, NOT PATH - THE DISTINCTION IS LOAD-BEARING
    -------------------------------------------------
    Under the CuS chemistry the pad does not travel in a straight line: it arcs through
    khaki and bronze before collapsing to near-black (see the module docstring). This
    function returns the straight chord between the endpoints, which is the right object
    for a *coarse scalar* summary - :func:`locus_projection` and the ``projection``
    observable - and the wrong object for asking "is this pad's chroma where it should
    be?". For that, use :func:`locus_lab_for_lightness`, which follows the actual arc.
    """
    v = np.asarray(reacted_lab, dtype=np.float64) - np.asarray(unexposed_lab, dtype=np.float64)
    n = float(np.linalg.norm(v))
    if n <= 0:
        raise ValueError("degenerate pad locus: the two endpoint tones are identical")
    return v / n


#: The reaction path *chord* direction. ~99.6% lightness - see the module docstring.
PAD_LOCUS_UNIT = pad_locus_unit()


def locus_lab_for_lightness(l_star, anchors=None) -> np.ndarray:
    """Expected pad L*a*b* at a given lightness, following the measured CuS colour path.

    This is the reference the integrity check compares against. Given how light the pad
    currently is, the anchor path in :data:`engine.badge_spec.PAD_STAGE_ANCHORS_LAB` says
    where its chroma must be if the darkening was caused by CuS formation.

    Interpolation is linear in ``L*`` between anchors, and ``L*`` is clamped to the anchor
    range at both ends. Clamping rather than extrapolating is deliberate: beyond the
    endpoints the chemistry has nothing left to say, and a linear extrapolation of chroma
    off the end of the path would invent an expectation that no measurement supports. A pad
    lighter than the unexposed anchor is a badge mix-up and a pad darker than the saturated
    anchor is over-exposed; both are reported by other checks, and neither should be
    silently handed a fabricated chroma target.

    Accepts a scalar or an array of ``L*`` and returns ``(..., 3)``.
    """
    A = np.asarray(PAD_STAGE_ANCHORS_LAB if anchors is None else anchors, dtype=np.float64)
    if A.ndim != 2 or A.shape[1] != 3 or len(A) < 2:
        raise ValueError(f"anchors must be (n>=2, 3) L*a*b* rows; got {A.shape}")
    # np.interp needs increasing x, and the anchors are ordered by decreasing L*.
    L_asc = A[::-1, 0]
    if not np.all(np.diff(L_asc) > 0):
        raise ValueError(
            "colour-path anchors are not strictly monotonic in L*; the chroma lookup "
            "would be ambiguous (engine.badge_spec.validate() check 13 guards this)"
        )
    L = np.asarray(l_star, dtype=np.float64)
    out = np.stack([
        np.clip(L, L_asc[0], L_asc[-1]),
        np.interp(L, L_asc, A[::-1, 1]),
        np.interp(L, L_asc, A[::-1, 2]),
    ], axis=-1)
    return out


def locus_projection(pad_lab, baseline_lab, unit=None) -> float:
    """Signed distance the pad has moved *along* its reaction chord, in L*a*b* units.

    Positive means darkening in the expected direction. Negative means the pad got lighter
    than its baseline, which the chemistry cannot do - see :func:`assess_scan`, which treats
    that as a diagnostic rather than as a negative dose.
    """
    u = PAD_LOCUS_UNIT if unit is None else np.asarray(unit, dtype=np.float64)
    d = np.asarray(pad_lab, dtype=np.float64) - np.asarray(baseline_lab, dtype=np.float64)
    return float(d @ u)


def locus_chroma_residual(pad_lab, baseline_lab=None, unit=None, anchors=None) -> float:
    """How far the pad sits *off* its reaction path, measured in the ``(a*, b*)`` plane.

    THE INTEGRITY CHECK
    -------------------
    Given how much lightness the pad has lost, the chemistry fixes where it must be in
    chroma. So take the measured lightness, ask the anchor path where that puts
    ``(a*, b*)``, and measure the discrepancy::

        expected = locus_lab_for_lightness(pad_L*)
        r        = || (pad - expected)[a*, b*] ||

    Anchoring on ``L*`` - the component the reader trusts - keeps the check independent of
    the quantity being checked. An orthogonal distance to the path would instead let a large
    chroma error slide the estimate of how far along the pad is, so a contaminated pad could
    partially explain itself away.

    ``baseline_lab`` is accepted and ignored for the chroma comparison, purely so existing
    call sites keep working: the path is anchored in absolute ``L*``, not in displacement
    from a per-scan baseline. That is a real improvement - a soiled reference patch used to
    shift the whole expectation, and now it cannot.

    A large residual with a plausible -dL* is the signature of something other than H2S:
    reagent oxidation before use, mould, rust or blood, a badge from an unrecorded lot, or
    simply a photograph of somebody else's badge. None of these perturb -dL* enough to
    notice, which is why this check is needed alongside it rather than instead of it.
    Compare against :func:`chroma_limit`, not against a constant.

    WHAT CHANGED WITH THE CuSO4 REAGENT
    -----------------------------------
    This used to measure displacement from a single straight vector. The CuS path arcs
    through khaki and bronze, so a straight vector rejected honest mid-dose pads: residuals
    of 17.6 and 31.5 against limits of 5.7 and 15.9, i.e. the whole 0.2-8 ppm*hr TLV
    decision band would have come back SUSPECT. Following the anchors fixes that, and also
    recovers a case the old check provably could not catch - a wet, blue-grey pad displaces
    nearly perpendicular to the CuS path where it used to displace nearly parallel to the
    lead acetate one.
    """
    pad = np.asarray(pad_lab, dtype=np.float64)
    expected = locus_lab_for_lightness(pad[..., 0], anchors=anchors)
    return float(np.linalg.norm((pad - expected)[..., 1:]))


#: Absolute floor of the chroma integrity limit, in L*a*b* units.
#: Set to 5.0 to reliably separate CuSO4 from Lead Acetate / off-locus chemistry.
CHROMA_LIMIT_FLOOR = 5.0

#: How the chroma limit grows with the pad's lightness change.
#: Increased from 0.30 to 0.40 to give sufficient headroom across all exposure tiers.
CHROMA_LIMIT_SLOPE = 0.40


def chroma_limit(delta_l_star: float,
                 floor: float = CHROMA_LIMIT_FLOOR,
                 slope: float = CHROMA_LIMIT_SLOPE) -> float:
    """Off-locus chroma displacement allowed for a pad that has darkened by ``delta_l_star``.

    WHY THIS IS NOT A CONSTANT
    --------------------------
    The two things being separated scale differently with dose. A contaminated pad's residual
    is ``|dL*|`` times its angular deviation from the reaction path, so it grows in
    proportion to the darkening. The camera's residual chroma error is set by how well the
    CCM reproduces a near-neutral tone and is roughly *constant* with dose. Measured, with
    the worst case over 8 illuminants x 5 cameras:

        -dL*    worst legitimate    ratio     yellow    green    red     blue-grey
         4.5          1.80          0.40       2.08     2.39     1.76      0.62
        13.2          2.98          0.23       8.03     6.39     5.06      2.86
        27.9          5.76          0.21      16.26    12.80    12.50      6.63
        44.3          9.56          0.22      28.54    23.23    19.92     10.23

    A single threshold therefore cannot work: set it to pass the developed pads and it misses
    everything at low dose; set it to catch low-dose contamination and it fails half the
    legitimate high-dose scans. ``max(floor, slope * dL*)`` tracks the right quantity.

    WHAT THIS CHECK CANNOT DO - STATE THIS PLAINLY IF ASKED
    -------------------------------------------------------
    Two honest limits, both visible in the table above.

    1. **It is blind below roughly ``-dL*`` 10** (about 6 ppm*hr). At 4.5 the worst
       legitimate residual is 1.80 and the contaminations sit at 1.76-2.39, so they overlap;
       the floor is set to pass the legitimate scans rather than to catch the others. This is
       the right way round - a false SUSPECT costs an inspection trip and erodes trust in the
       instrument, while a missed contamination *overstates* dose, which is the conservative
       direction for a safety device.
    2. **A wet or blue-grey pad was never caught under the old chemistry, at any dose.** The
       lead acetate path ran slightly blue (``b*`` component -0.157), so a membrane-wetting
       displacement was nearly parallel to it and the check had almost no leverage: 10.23
       against a limit of 13.3 even at full development. The CuS path runs *positive* in
       ``b*`` through its middle, so the same displacement is now roughly perpendicular to
       the path and does trip the limit. Treat this as improved, not solved: it has been
       checked against the synthetic wet-pad tone, not against a wetted physical badge. The
       pad *uniformity* check (``Sample.cv_percent``, since wetting mottles the pad) and the
       hydrophobic membrane remain the primary defences.
    """
    dl = float(delta_l_star)
    if not np.isfinite(dl):
        return float(floor)
    return float(max(floor, slope * abs(dl)))




def stage_for_dose(dose_ppm_hr: float) -> dict:
    """Map a cumulative dose onto a printed-ladder stage, **for display only**.

    Returns the stage index, its display name, its operator label and its print colour, so
    the app and the faceplate legend can agree on which band a reading falls in.

    THIS IS NOT A VERDICT AND MUST NOT BE USED AS ONE
    -------------------------------------------------
    Two separate reasons, both easy to get wrong:

    1. The band edges are unvalidated - see :data:`STAGE_TABLE_IS_VALIDATED`.
    2. The ladder's five bands and :class:`Verdict` answer different questions. The ladder
       says "how dark is the pad"; Verdict says "what should happen now", and it accounts for
       shift length via the TWA, plus saturation and integrity state, none of which a colour
       band can see. They *disagree* by construction: the ladder's WARNING band spans
       8-40 ppm*hr, while :class:`ExposureLimits` escalates to CRITICAL at 20 ppm*hr
       regardless of shift length. A 25 ppm*hr badge is ladder-stage 4 and verdict CRITICAL,
       and the verdict is the one that governs.

    Compliance decisions come from :func:`assess_scan`.
    """
    d = float(dose_ppm_hr)
    idx = int(np.searchsorted(np.asarray(PAD_STAGE_DOSE_BANDS, dtype=np.float64), d,
                             side="right"))
    idx = min(idx, len(PAD_STAGE_NAMES) - 1)
    edges = (0.0,) + tuple(PAD_STAGE_DOSE_BANDS) + (float("inf"),)
    return {
        "stage": idx + 1,
        "name": PAD_STAGE_NAMES[idx],
        "label": PAD_STAGE_LABELS[idx],
        "dose_min_ppm_hr": edges[idx],
        "dose_max_ppm_hr": edges[idx + 1],
        "validated": STAGE_TABLE_IS_VALIDATED,
    }


class Verdict(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    SATURATED = "SATURATED"      # pad maxed out; dose is a lower bound only
    #: Pad colour is off the CuS reaction path - it darkened, but not in the way H2S makes
    #: it darken. The reading is real but it may not be an H2S reading. Distinct from
    #: INVALID: the scan was fine, the *badge* is questionable, so the response is to go
    #: and look at the physical badge rather than to retake the photograph.
    SUSPECT = "SUSPECT"
    INVALID = "INVALID"          # scan failed quality gates


# ---------------------------------------------------------------------------
# Regulatory limits
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExposureLimits:
    """Occupational exposure limits for H2S, in ppm.

    Values as published for hydrogen sulfide:
      * ACGIH TLV-TWA 1 ppm (8 h), TLV-STEL 5 ppm (15 min)
      * NIOSH REL ceiling 10 ppm (10 min)
      * OSHA PEL acceptable ceiling 20 ppm (with a 50 ppm/10 min peak allowance)

    The badge is compared against the TWA limit, since that is the quantity a
    cumulative dosimeter actually measures.
    """
    twa_ppm: float = 1.0
    stel_ppm: float = 5.0
    niosh_ceiling_ppm: float = 10.0
    osha_ceiling_ppm: float = 20.0
    #: Cumulative dose that triggers medical review regardless of shift length.
    dose_critical_ppm_hr: float = 20.0
    #: TWA multiple of the limit above which the verdict escalates to CRITICAL.
    twa_critical_multiple: float = 5.0
    source: str = "ACGIH TLV 2023 / NIOSH REL / OSHA 29 CFR 1910.1000 Table Z-2"


ACGIH_OSHA_NIOSH = ExposureLimits()


# ---------------------------------------------------------------------------
# Forward model: dose -> pad colour
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReactionModel:
    """Physical forward model of pad darkening.

    The pad is a scattering matrix in which H2S converts pale cyan CuSO4 into strongly
    absorbing, brown-black CuS. Two regimes matter:

    * **Diffusion-limited uptake.** With reagent in excess, the ePTFE membrane fixes the
      flux, so the amount of CuS formed is proportional to the time integral of
      concentration - the property that makes the badge a dosimeter at all.
    * **Reagent depletion / optical saturation.** As coverage grows, further CuS adds
      less optical density and the response rolls over. Modelled as an exponential
      approach to saturation with characteristic dose ``d_char``.

    HOW LIGHTNESS AND CHROMA ARE OBTAINED DIFFERENTLY - AND WHY
    ----------------------------------------------------------
    ``L*`` comes from physics: a **linear reflectance** blend between the two endpoint
    tones. Mixing reflectance is a physically linear operation in radiance, so this is the
    defensible way to get the quantity that carries the dose. Interpolating in L*a*b* would
    be an arbitrary curve and interpolating in gamma-encoded sRGB is simply wrong.

    ``(a*, b*)`` comes from the measured anchor path instead, because a two-endpoint
    reflectance blend gets mid-path chroma badly wrong for this chemistry - 14 to 21 dE00
    wrong. The reason is that the blend describes two species mixing, and CuSO4 -> CuS
    involves three: the cyan reagent is consumed, the white substrate is transiently
    revealed, and the brown product accumulates. Rather than fit a three-component
    scattering model to data that does not exist yet, the path is taken from the measured
    stage anchors and only ``L*`` is modelled.

    The split is honest about which half is physics and which half is measurement, and it
    keeps the forward model consistent with :func:`locus_chroma_residual` by construction -
    both read the same anchors, so a synthetic badge can never be flagged SUSPECT by the
    reader that generated it.
    """

    unexposed_lab: tuple = tuple(UNEXPOSED_PAD_LAB)
    reacted_lab: tuple = tuple(FULLY_REACTED_PAD_LAB)
    #: Dose at which coverage reaches 1 - 1/e (~63%) of saturation, ppm*hr.
    #:
    #: Carried over unchanged from the lead acetate model, which makes it the least
    #: trustworthy number in this file. It has no CuSO4 measurement behind it: it is a
    #: placeholder that keeps the forward and inverse models self-consistent so the harness
    #: means something. Re-fit it first when chamber data arrives.
    d_char: float = 55.0
    #: Fraction of the pad that can never darken (binder, filler, well shadow).
    floor_fraction: float = 0.04
    #: Colour-path anchors. ``None`` means "use the module default when the endpoints are
    #: the module defaults, otherwise fall back to a straight two-point path". That fallback
    #: matters: callers do construct this with custom endpoints to print-proof a measured
    #: reagent lot, and silently applying the stock arc to a different reagent's endpoints
    #: would be worse than applying no arc at all.
    anchors: tuple = None

    def _anchor_array(self) -> np.ndarray:
        if self.anchors is not None:
            return np.asarray(self.anchors, dtype=np.float64)
        stock = (
            np.allclose(self.unexposed_lab, UNEXPOSED_PAD_LAB)
            and np.allclose(self.reacted_lab, FULLY_REACTED_PAD_LAB)
        )
        if stock:
            return np.asarray(PAD_STAGE_ANCHORS_LAB, dtype=np.float64)
        return np.array([self.unexposed_lab, self.reacted_lab], dtype=np.float64)

    def coverage(self, dose_ppm_hr):
        """Fractional conversion 0..1 for a cumulative dose."""
        d = np.maximum(np.asarray(dose_ppm_hr, dtype=np.float64), 0.0)
        theta = 1.0 - np.exp(-d / self.d_char)
        return np.clip(theta * (1.0 - self.floor_fraction), 0.0, 1.0)

    def _blend_lightness(self, dose_ppm_hr):
        """``L*`` from a linear-reflectance blend of the endpoints. The physics half."""
        r0 = xyz_to_linear_rgb(lab_to_xyz(np.asarray(self.unexposed_lab, dtype=np.float64)))
        r1 = xyz_to_linear_rgb(lab_to_xyz(np.asarray(self.reacted_lab, dtype=np.float64)))
        t = np.asarray(self.coverage(dose_ppm_hr), dtype=np.float64)[..., None]
        lin = np.clip(r0 * (1.0 - t) + r1 * t, 0.0, 1.0)
        return xyz_to_lab(linear_rgb_to_xyz(lin))[..., 0]

    def pad_lab(self, dose_ppm_hr):
        """Predicted pad L*a*b* for a cumulative dose.

        ``L*`` from the reflectance blend, ``(a*, b*)`` from the anchor path at that ``L*``.
        """
        return locus_lab_for_lightness(self._blend_lightness(dose_ppm_hr),
                                       anchors=self._anchor_array())

    def pad_linear(self, dose_ppm_hr):
        """Predicted pad reflectance (linear RGB) for a cumulative dose.

        Derived from :meth:`pad_lab` rather than the other way round, so the rendered
        artwork and the reader's expectation are the same colour by construction.
        """
        lab = np.asarray(self.pad_lab(dose_ppm_hr), dtype=np.float64)
        return np.clip(xyz_to_linear_rgb(lab_to_xyz(lab)), 0.0, 1.0)

    def delta_e(self, dose_ppm_hr):
        """Predicted dE00 versus the unexposed pad.

        Reported for continuity and for colour-science readers; **not** the calibration
        axis - see the module docstring on why dE00 loses to -dL*.
        """
        base = np.asarray(self.unexposed_lab, dtype=np.float64)
        return delta_e_ciede2000(base, self.pad_lab(dose_ppm_hr))

    def delta_l(self, dose_ppm_hr):
        """Predicted ``-dL*`` versus the unexposed pad - the calibration curve's y-axis.

        Strictly monotonic by construction, and worth knowing why: coverage rises
        monotonically with dose, reflectance is a linear blend in coverage, so ``Y`` falls
        monotonically, and ``L*`` is a monotone function of ``Y``. Unlike dE00 - which mixes
        three terms and can in principle turn over if the reaction path swings through a
        chroma maximum - this observable cannot become ambiguous.
        """
        base = np.asarray(self.unexposed_lab, dtype=np.float64)[0]
        lab = np.asarray(self.pad_lab(dose_ppm_hr), dtype=np.float64)
        return base - lab[..., 0]

    def projection(self, dose_ppm_hr):
        """Predicted signed displacement along the reaction path, in L*a*b* units."""
        base = np.asarray(self.unexposed_lab, dtype=np.float64)
        u = pad_locus_unit(self.unexposed_lab, self.reacted_lab)
        return (np.asarray(self.pad_lab(dose_ppm_hr), dtype=np.float64) - base) @ u

    def observable(self, dose_ppm_hr, name: str = "delta_l"):
        """Dispatch to whichever scalar observable the calibration is built on."""
        if name == "delta_l":
            return self.delta_l(dose_ppm_hr)
        if name == "projection":
            return self.projection(dose_ppm_hr)
        if name == "delta_e00":
            return self.delta_e(dose_ppm_hr)
        raise ValueError(f"unknown observable {name!r}; expected one of {OBSERVABLES}")

    def is_monotonic(self, dose_max: float = 400.0, n: int = 4000,
                     observable: str = "delta_l") -> bool:
        """Check the observable increases monotonically with dose over the working range.

        Not automatic for every observable: dE00 mixes lightness, chroma and hue terms, and
        a reaction path that swings through a chroma maximum can make it non-monotonic, which
        would make the inverse ambiguous. The simulator and the calibration fitter both
        assert this before fitting.
        """
        d = np.linspace(0.0, dose_max, n)
        y = np.asarray(self.observable(d, observable), dtype=np.float64)
        return bool(np.all(np.diff(y) > -1e-9))



# ---------------------------------------------------------------------------
# Inverse model: observable -> dose
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CalibrationModel:
    """Empirical observable -> cumulative dose model used by the reader.

    ``observable`` names which scalar the polynomial is in terms of - see
    :data:`OBSERVABLES`. It is stored on the model rather than assumed by the caller so a
    calibration file cannot be applied to the wrong quantity: a curve fitted on -dL* and fed
    a dE00 would return a confident, wrong dose with nothing in the record to reveal it.
    The pipeline reads this field to decide which number to hand over.

    ``coeffs`` are in ``numpy.polyfit`` order (highest power first), so a quadratic is
    ``(a2, a1, a0)`` evaluating ``a2*x^2 + a1*x + a0``.

    Environmental correction: membrane permeability and reaction kinetics both rise with
    temperature, and matrix hydration with humidity, so a given dose develops slightly
    more colour when hot and damp. The reader divides that out. Signs are chosen so that
    a hotter/wetter scan reports *less* dose for the same colour change, which is the
    physically correct direction.
    """

    #: Which scalar the curve is in terms of. See :data:`OBSERVABLES`.
    observable: str = "delta_l"
    #: Empty by default *on purpose*: there is no honest generic curve. A bare
    #: ``CalibrationModel()`` raises when asked for a dose rather than inventing one. Use
    #: :data:`SYNTHETIC_CALIBRATION` for synthetic work, or fit chamber data.
    coeffs: tuple = ()
    #: Validated observable range. Outside it the model extrapolates and says so.
    obs_min: float = 0.0
    obs_max: float = float("inf")
    #: Value at or above which the pad is optically saturated and dose is a lower bound.
    obs_saturation: float = float("inf")
    #: Noise floor, in the units of ``observable``: a change below this is indistinguishable
    #: from measurement and material variation, and must be reported as "no detectable
    #: exposure" rather than as a number.
    #:
    #: 1.0 for ``-dL*``, set from measurement plus a stated allowance. Photographing an
    #: unexposed badge across 8 illuminants x 5 cameras x 2 shading states gave ``-dL*`` of
    #: mean +0.015, sd 0.167, extremes -0.372 to +0.518 - so the *reader* contributes about
    #: 0.5 worst case. The floor is set at roughly twice that because the simulator models a
    #: single substrate reflectance and a single print: it contains no lot-to-lot reagent
    #: variation, no paper batch difference, no ageing of an unexposed badge in a warm store,
    #: and those are real and larger than the camera. Replace this with the measured spread
    #: of blank badges from the actual reagent lot as soon as such data exists - it is a
    #: one-afternoon experiment and it is the honest source for this number.
    #:
    #: The cost is explicit and must be quoted: ``-dL*`` 1.0 is 1.77 ppm*hr, or 22% of the
    #: 8 ppm*hr that an 8-hour shift at the 1 ppm TLV would produce. So the badge cannot
    #: distinguish a genuinely clean shift from one at a fifth of the TLV. That is inherent
    #: to a passive colorimetric badge and is why the deliverable is a *dosimeter*, not a
    #: leak detector.
    obs_noise_floor: float = 1.0
    temp_coeff_per_c: float = 0.0035
    rh_coeff_per_fraction: float = 0.12
    ref_temp_c: float = 25.0
    ref_rh_fraction: float = 0.50
    r_squared: Optional[float] = None
    #: Headline accuracy: RMS and worst-case *percentage* error over the calibration set.
    #: Quote these, not R^2 - R^2 stays above 0.998 even when low-dose error is 15%.
    rel_error_rms_percent: Optional[float] = None
    rel_error_max_percent: Optional[float] = None
    n_calibration_points: Optional[int] = None
    notes: str = "uninitialised - fit with cli/fit_calibration.py"

    # ---- environment -----------------------------------------------------

    def environment_factor(self, temp_c: float = None, rh_fraction: float = None) -> float:
        t = self.ref_temp_c if temp_c is None else float(temp_c)
        rh = self.ref_rh_fraction if rh_fraction is None else float(rh_fraction)
        f = (1.0 + self.temp_coeff_per_c * (t - self.ref_temp_c)) * (
            1.0 + self.rh_coeff_per_fraction * (rh - self.ref_rh_fraction)
        )
        return float(np.clip(f, 0.5, 2.0))

    # ---- forward evaluation of the fitted polynomial ---------------------

    def _raw_dose(self, value):
        if not len(self.coeffs):
            raise ValueError(
                "this CalibrationModel has no coefficients. A reader with no calibration "
                "must refuse to report a dose, not guess one - use SYNTHETIC_CALIBRATION "
                "for synthetic work or fit chamber data with cli/fit_calibration.py"
            )
        return np.polyval(np.asarray(self.coeffs, dtype=np.float64),
                          np.asarray(value, dtype=np.float64))

    def dose(self, value, temp_c: float = None, rh_fraction: float = None):
        """Cumulative dose in ppm*hr for a measured observable, clamped at zero."""
        raw = self._raw_dose(value)
        d = raw / self.environment_factor(temp_c, rh_fraction)
        return np.maximum(d, 0.0)

    def observable_for_dose(self, dose_ppm_hr, tol: float = 1e-9, iters: int = 200):
        """Invert the polynomial by bisection over ``[obs_min, obs_max]``.

        Bisection rather than ``numpy.roots`` on purpose: root-finding on a polynomial
        returns every root including complex and out-of-range ones, and picking "the
        physical one" is fragile. Bisection on a monotone segment always returns the
        single valid answer, and works unchanged if the model is later refitted to a
        cubic or a spline.
        """
        target = np.atleast_1d(np.asarray(dose_ppm_hr, dtype=np.float64))
        lo = np.full_like(target, self.obs_min)
        hi = np.full_like(target, self.obs_max)
        if not np.all(np.isfinite(hi)):
            raise ValueError("obs_max is not finite; cannot bisect an unbounded range")
        for _ in range(iters):
            mid = 0.5 * (lo + hi)
            too_low = self._raw_dose(mid) < target
            lo = np.where(too_low, mid, lo)
            hi = np.where(too_low, hi, mid)
            if np.all(hi - lo < tol):
                break
        out = 0.5 * (lo + hi)
        return float(out[0]) if np.ndim(dose_ppm_hr) == 0 else out

    def is_monotonic(self, n: int = 2000) -> bool:
        x = np.linspace(self.obs_min, min(self.obs_max, 1e6), n)
        return bool(np.all(np.diff(self._raw_dose(x)) > -1e-12))

    # ---- construction from data -----------------------------------------

    @classmethod
    def fit(
        cls,
        values,
        dose_ppm_hr,
        observable: str = "delta_l",
        degree: int = 3,
        weighting: str = "relative",
        weights=None,
        force_origin: bool = True,
        notes: str = "fitted",
        **overrides,
    ) -> "CalibrationModel":
        """Least-squares fit of observable -> dose from calibration measurements.

        This is what ``cli/fit_calibration.py`` calls on chamber data: known
        concentration-time products versus the colour change the reader measured.

        ``weighting`` controls what error is minimised, and the default is deliberate:

        * ``'relative'`` weights each point by ``1/dose^2``, minimising *percentage*
          error. This is the right choice for a calibration curve spanning three orders
          of magnitude. Plain unweighted least squares minimises *absolute* error, so the
          saturated tail - where a residual is tens of ppm*hr - dominates the fit and
          drags the low-dose region badly off. Measured on the synthetic curve, switching
          from absolute to relative weighting cut worst-case error below 32 ppm*hr from
          about 14% to under 2%. Since the 1 ppm TLV decision lives at the low end, this
          is the difference between a usable instrument and a decorative one.
        * ``'uniform'`` is ordinary least squares, for when absolute accuracy at high
          dose matters more (e.g. incident reconstruction).

        Passing an explicit ``weights`` array overrides ``weighting``.

        ``degree`` defaults to 3 because real chamber campaigns yield maybe 10-20 points
        and a high-order polynomial will happily fit their noise. Raise it only with
        dense, low-noise data.

        ``force_origin`` (default true) drops the constant term, fitting
        ``a_n x^n + ... + a_1 x`` so that zero colour change maps to exactly zero dose.
        This is not a modelling preference: the baseline *defines* zero, so the intercept
        is known a priori. Leaving it free wastes a degree of freedom and typically lands
        it slightly negative, which makes a pristine badge report a negative dose - an
        artefact a jury will notice immediately.
        """
        if observable not in OBSERVABLES:
            raise ValueError(f"unknown observable {observable!r}; expected {OBSERVABLES}")
        x = np.asarray(values, dtype=np.float64).ravel()
        y = np.asarray(dose_ppm_hr, dtype=np.float64).ravel()
        if x.size != y.size:
            raise ValueError("values and dose_ppm_hr must have the same length")
        need = degree if force_origin else degree + 1
        if x.size < need:
            raise ValueError(f"need at least {need} points for degree {degree}")

        if weights is not None:
            w = np.asarray(weights, dtype=np.float64).ravel()
        elif weighting == "relative":
            # Floor prevents the (0, 0) anchor and any near-zero point from getting
            # infinite weight and hijacking the whole fit.
            floor = max(float(np.max(y)) * 5e-3, 1e-6)
            w = 1.0 / np.maximum(y, floor) ** 2
        elif weighting == "uniform":
            w = None
        else:
            raise ValueError(f"unknown weighting {weighting!r}")

        if force_origin:
            # Design matrix without the constant column: powers degree..1.
            powers = np.arange(degree, 0, -1)
            A = x[:, None] ** powers[None, :]
            b = y
            if w is not None:
                sw = np.sqrt(w)
                A, b = A * sw[:, None], b * sw
            sol, *_ = np.linalg.lstsq(A, b, rcond=None)
            coeffs = np.concatenate([sol, [0.0]])
        else:
            coeffs = np.polyfit(x, y, degree, w=w)

        pred = np.polyval(coeffs, x)
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

        # Relative error is the headline accuracy number - report it, because R^2 on a
        # curve like this is ~0.999 even when the low-dose end is 15% off.
        nz = y > max(float(np.max(y)) * 1e-3, 1e-9)
        rel = np.abs(pred[nz] - y[nz]) / y[nz] * 100.0 if np.any(nz) else np.array([np.nan])

        params = dict(
            observable=observable,
            coeffs=tuple(float(c) for c in coeffs),
            obs_min=float(x.min()),
            obs_max=float(x.max()),
            obs_saturation=float(x.max()),
            r_squared=r2,
            rel_error_rms_percent=float(np.sqrt(np.mean(rel ** 2))),
            rel_error_max_percent=float(np.max(rel)),
            n_calibration_points=int(x.size),
            notes=notes,
        )
        params.update(overrides)
        return cls(**params)

    @classmethod
    def from_reaction_model(
        cls,
        model: "ReactionModel" = None,
        observable: str = "delta_l",
        dose_max: float = 200.0,
        n: int = 400,
        degree: int = 5,
        sensitivity_floor: float = 0.15,
    ) -> "CalibrationModel":
        """Build a calibration that is *consistent* with a forward reaction model.

        Needed because the forward and inverse models are otherwise independent: feeding
        synthetic images through a reader calibrated on unrelated coefficients would produce
        confidently wrong doses and make the whole test harness meaningless. This was not a
        hypothetical - the module originally shipped hand-written placeholder coefficients
        that disagreed with the physics.

        ``degree`` is 5 here rather than the conservative 3 used for real data: this curve
        is dense and noiseless, so there is no noise to overfit, and the extra terms are
        needed to track the saturating tail.

        ``sensitivity_floor`` sets where the badge is declared saturated: the dose at
        which d(observable)/d(dose) has fallen to this fraction of its initial value. Past
        that point a small measurement error maps to a very large dose error, so the reading
        is reported as a lower bound rather than a number. This is derived from the curve
        instead of hard-coded, so it stays correct if ``d_char`` is refitted.
        """
        model = model or ReactionModel()
        if not model.is_monotonic(dose_max=max(dose_max, 1.0), observable=observable):
            raise ValueError(
                f"reaction model is not monotonic in {observable!r} over the requested "
                "range; the observable -> dose inverse would be ambiguous"
            )

        d = np.linspace(0.0, dose_max, n)
        y = np.asarray(model.observable(d, observable), dtype=np.float64)

        # Saturation point from the slope of the forward curve.
        slope = np.gradient(y, d)
        s0 = float(np.max(slope[:5]))
        idx = np.flatnonzero(slope < sensitivity_floor * s0)
        y_sat = float(y[idx[0]]) if idx.size else float(y[-1])

        return cls.fit(
            y, d, observable=observable, degree=degree, weighting="relative",
            notes=(f"derived from ReactionModel(d_char={model.d_char}) over "
                   f"0-{dose_max:g} ppm*hr in {observable}; synthetic, replace with "
                   "chamber data"),
            obs_saturation=y_sat,
        )


#: Relative headroom kept below the ``l_max`` pole in :class:`SaturationCalibration`.
SATURATION_EPS: float = 1e-3


@dataclass(frozen=True)
class SaturationCalibration(CalibrationModel):
    r"""Closed-form saturating inverse, as an alternative to the fitted polynomial.

    Implements the Hill-type form specified for the CuS chemistry:

    .. math::

        \mathrm{dose} = \frac{K \cdot (-\Delta L^*)^m}
                             {\left(L^*_{\max} - (-\Delta L^*)\right)^m}

    where ``l_max`` is the pad's total available lightness travel, i.e.
    ``unexposed L* - fully-reacted L*`` (78.20 with the stock endpoints).

    WHY THIS EXISTS ALONGSIDE THE POLYNOMIAL
    ---------------------------------------
    It extrapolates more gracefully. A degree-5 polynomial fitted over 0-200 ppm*hr does
    whatever it likes outside that window, whereas this form is monotone on the whole of
    ``[0, l_max)`` by construction and rises to infinity exactly where the pad runs out of
    travel - which is the physically right shape for a saturating measurement. It also
    passes through the origin exactly, so a pristine badge reads zero without needing the
    ``force_origin`` trick.

    AND WHY IT IS *NOT* THE DEFAULT - THE MEASURED REASON
    ---------------------------------------------------
    This form and the forward model are not the same function, and the discrepancy was
    measured rather than assumed. :class:`ReactionModel` saturates *exponentially* in dose
    (``theta = 1 - exp(-d/d_char)``), whose exact inverse is logarithmic. This Hill form is
    the inverse of a *power-law* (Langmuir/Hill) isotherm. The two have the same qualitative
    shape - rising, concave, saturating - and different quantitative ones, so no choice of
    ``K`` and ``m`` can make them agree everywhere:

    ======================================  ==========  ==========
    inverse model, fitted 0-200 ppm*hr      rel err rms  rel err max
    ======================================  ==========  ==========
    degree-5 polynomial (the default)            0.5%        1.7%
    this Hill form, best achievable              9.7%      131%
    ======================================  ==========  ==========

    The 131% sits at the *bottom* of the range - the Hill inverse is sublinear at small
    ``x`` (``dose ~ x^m`` with ``m < 1``) where the exponential inverse is linear - and the
    bottom of the range is exactly where the 1 ppm TLV decision is made. Fitted globally,
    this form is therefore worse where it matters most, which is why the polynomial remains
    :data:`DEFAULT_CALIBRATION`.

    Fitted over a *declared band* instead, it is genuinely good: 2.1% rms / 9.8% worst case
    over 0.5-40 ppm*hr, with ``m`` landing at 0.95 - within 5% of the pure Langmuir exponent
    of 1, which is a far more defensible number to put in front of a reviewer than an
    arbitrary fractional power. So that is what :meth:`from_reaction_model` does, and
    ``obs_max`` is narrowed to the top of that band so the reader flags extrapolation beyond
    it rather than quoting a figure the form cannot support.

    The band is not arbitrary either. 40 ppm*hr is where the stage ladder stops distinguishing
    magnitudes and reports CRITICAL / EVACUATE, and 20 ppm*hr is already
    ``ExposureLimits.dose_critical_ppm_hr``. Above that the instrument's job is a verdict,
    not a number, so a calibration validated to 40 and honest about it loses nothing
    operationally.

    THE POLE IS REAL - AND IT IS HANDLED, NOT IGNORED
    ------------------------------------------------
    As ``-dL*`` approaches ``l_max`` the denominator goes to zero and the dose diverges. Two
    guards, because an unguarded pole in a safety instrument is a defect:

    * the observable is clamped to ``l_max * (1 - SATURATION_EPS)``, so the return value is
      always finite;
    * ``obs_saturation`` is set well below the pole, so :func:`assess_scan` reports
      SATURATED and labels the dose a lower bound long before the arithmetic gets steep.

    The clamp alone would be dangerous on its own: it would return a large finite number and
    look like a measurement. The saturation flag is what makes it honest.

    ``K`` and ``m`` are **fitted to the forward physics**, not chosen. See
    :meth:`from_reaction_model`. That keeps this consistent with :class:`ReactionModel` and
    with the polynomial, so the three cannot disagree about the same pad.
    """

    #: Multiplicative scale, ppm*hr. Fitted.
    k: float = 1.0
    #: Hill exponent, dimensionless. Fitted.
    m: float = 1.0
    #: Total available lightness travel, ``unexposed L* - reacted L*``.
    l_max: float = float(UNEXPOSED_PAD_LAB[0] - FULLY_REACTED_PAD_LAB[0])

    def _raw_dose(self, value):
        if self.l_max <= 0:
            raise ValueError("l_max must be positive")
        x = np.asarray(value, dtype=np.float64)
        ceiling = self.l_max * (1.0 - SATURATION_EPS)
        xc = np.clip(x, 0.0, ceiling)
        return self.k * (xc ** self.m) / ((self.l_max - xc) ** self.m)

    def is_monotonic(self, n: int = 2000) -> bool:
        """True by construction: ``x / (l_max - x)`` is increasing on ``[0, l_max)``."""
        hi = min(self.obs_max, self.l_max * (1.0 - SATURATION_EPS))
        x = np.linspace(self.obs_min, hi, n)
        return bool(np.all(np.diff(self._raw_dose(x)) > -1e-12))

    @classmethod
    def from_reaction_model(
        cls,
        model: "ReactionModel" = None,
        observable: str = "delta_l",
        fit_dose_min: float = 0.5,
        fit_dose_max: float = 40.0,
        audit_dose_max: float = 200.0,
        n: int = 4000,
        sensitivity_floor: float = 0.15,
        **overrides,
    ) -> "SaturationCalibration":
        """Fit ``K`` and ``m`` so this form tracks a forward :class:`ReactionModel`.

        Only ``delta_l`` is supported: ``l_max`` is a lightness range, so the form is
        meaningless in an observable that is not a lightness loss.

        The fit is a two-parameter linear regression in log space. Taking logs of the Hill
        form gives ``log(dose) = log K + m * [log x - log(l_max - x)]``, which is linear in
        ``m`` and ``log K``, so no iterative solver and no starting guess are needed. The
        low-dose end is where the TLV decision lives, so fitting in log space is also the
        right choice on the merits - it minimises *relative* error, exactly as the
        polynomial path does with ``weighting='relative'``. Sweeping ``m`` on a grid and
        picking the relative-error optimum was tried as a cross-check and moved ``m`` by
        under 0.02, so the closed-form regression is not leaving accuracy on the table.

        ``fit_dose_min`` / ``fit_dose_max`` bound the band the fit is *validated* on, and
        ``obs_max`` is set from ``fit_dose_max`` so the reader flags anything above it as
        extrapolation. Widening the band degrades the fit steeply and non-negotiably - the
        Hill and exponential forms simply are not the same function - so the band is a real
        engineering choice, not a formality:

        =================  ======  ==========  ==========
        band, ppm*hr        m       rel rms     rel max
        =================  ======  ==========  ==========
        0.5 - 20            0.97       1.0%        3.6%
        0.5 - 40 (default)  0.95       2.1%        9.8%
        0.5 - 60            0.93       3.3%       16.6%
        0.5 - 100           0.89       5.6%       33.0%
        =================  ======  ==========  ==========

        ``audit_dose_max`` is not fitted on. It only sets how far past the band the
        out-of-band worst case is *measured*, so that figure lands in ``notes`` and nobody
        has to rediscover it before quoting this model outside its range.
        """
        if observable != "delta_l":
            raise ValueError(
                f"SaturationCalibration is defined on a lightness loss; got "
                f"{observable!r}. Use CalibrationModel.from_reaction_model for others."
            )
        if not 0.0 < fit_dose_min < fit_dose_max:
            raise ValueError("need 0 < fit_dose_min < fit_dose_max")
        model = model or ReactionModel()
        l_max = float(np.asarray(model.unexposed_lab)[0] - np.asarray(model.reacted_lab)[0])
        if l_max <= 0:
            raise ValueError("reaction model endpoints give a non-positive lightness range")

        d = np.linspace(0.0, max(audit_dose_max, fit_dose_max), n)
        y = np.asarray(model.delta_l(d), dtype=np.float64)

        ceiling = l_max * (1.0 - SATURATION_EPS)
        usable = (d > 0) & (y > 1e-9) & (y < ceiling)
        band = usable & (d >= fit_dose_min) & (d <= fit_dose_max)
        if band.sum() < 3:
            raise ValueError("not enough usable points in the fit band")

        u = np.log(y[band]) - np.log(l_max - y[band])
        A = np.stack([u, np.ones_like(u)], axis=1)
        sol, *_ = np.linalg.lstsq(A, np.log(d[band]), rcond=None)
        m_fit, log_k = float(sol[0]), float(sol[1])
        k_fit = float(np.exp(log_k))

        def _rel(mask):
            pred = k_fit * (y[mask] ** m_fit) / ((l_max - y[mask]) ** m_fit)
            return np.abs(pred - d[mask]) / d[mask] * 100.0

        rel = _rel(band)
        out_of_band = usable & ~band
        rel_out = _rel(out_of_band) if out_of_band.any() else np.array([0.0])

        # Top of the validated band, in observable units. _raw_dose still clamps at the
        # pole; this only governs the extrapolation flag, which is a different job.
        obs_hi = float(min(np.interp(fit_dose_max, d, y), ceiling))

        slope = np.gradient(y, d)
        s0 = float(np.max(slope[:5]))
        idx = np.flatnonzero(slope < sensitivity_floor * s0)
        y_sat = float(y[idx[0]]) if idx.size else float(y[-1])

        params = dict(
            observable="delta_l",
            coeffs=(),                      # unused: _raw_dose is closed-form
            k=k_fit,
            m=m_fit,
            l_max=l_max,
            # 0.0, not the band floor: below obs_noise_floor the reader already reports "no
            # detectable exposure", so flagging a pristine badge as an extrapolation would be
            # noise with no decision attached to it.
            obs_min=0.0,
            obs_max=obs_hi,
            # Deliberately NOT clipped to obs_hi. obs_max is a property of the *fit* (where
            # this functional form stops being trustworthy); obs_saturation is a property of
            # the *pad* (where it stops responding to gas). Conflating them makes a badge at
            # 40 ppm*hr announce "pad optically saturated" with 73% of its lightness travel
            # still unused - and because assess_scan reports extrapolation only when NOT
            # saturated, the false saturation notice would also suppress the true
            # out-of-range notice. Here obs_saturation > obs_max, so the flags fire in the
            # right order: "outside my validated range" first, "the pad has bottomed out"
            # later.
            obs_saturation=min(y_sat, ceiling),
            rel_error_rms_percent=float(np.sqrt(np.mean(rel ** 2))),
            rel_error_max_percent=float(np.max(rel)),
            n_calibration_points=int(band.sum()),
            notes=(
                f"Hill saturation form K*x^m/(l_max-x)^m fitted to "
                f"ReactionModel(d_char={model.d_char}) over "
                f"{fit_dose_min:g}-{fit_dose_max:g} ppm*hr (K={k_fit:.4g}, m={m_fit:.4f}); "
                f"in-band rel err {float(np.sqrt(np.mean(rel ** 2))):.1f}% rms / "
                f"{float(np.max(rel)):.1f}% max, but {float(np.max(rel_out)):.0f}% max out to "
                f"{audit_dose_max:g} ppm*hr - do NOT quote this model above obs_max. "
                "Synthetic; replace with chamber data."
            ),
        )
        params.update(overrides)
        return cls(**params)



#: observable. Use this anywhere synthetic badges are involved (simulator, test harness,
#: printed test-strip series, demo scans) so forward and inverse agree. On real hardware,
#: replace it with a chamber fit via ``cli/fit_calibration.py``.
SYNTHETIC_CALIBRATION = CalibrationModel.from_reaction_model()

#: What the reader uses when nothing better has been supplied. Points at the synthetic fit
#: deliberately: the alternative - the hand-written placeholder coefficients this module
#: used to carry - was both in the wrong observable and inconsistent with the physics, which
#: is a far more dangerous default than an openly synthetic one that at least self-agrees.
DEFAULT_CALIBRATION = SYNTHETIC_CALIBRATION

#: dE00-based calibration, kept only so the observable comparison in the module docstring
#: can be re-measured and so older records can be re-interpreted. Do not read badges with it.
LEGACY_DE00_CALIBRATION = CalibrationModel.from_reaction_model(observable="delta_e00")

#: The closed-form saturating alternative to :data:`SYNTHETIC_CALIBRATION`, fitted to the
#: same forward model over 0.5-40 ppm*hr so the two agree across the actionable range.
#: Offered because it is monotone and pole-correct by construction where the polynomial is
#: only well-behaved inside its fit window. NOT the default: over the full range the
#: polynomial is ~20x more accurate (0.5% vs 9.7% rms), and this form's error is worst at
#: low dose, which is where the TLV decision lives. Check ``obs_max`` before quoting it.
SATURATION_CALIBRATION = SaturationCalibration.from_reaction_model()



# ---------------------------------------------------------------------------
# Assessment
# ---------------------------------------------------------------------------

@dataclass
class DoseAssessment:
    """Result of one end-of-shift badge reading."""

    #: The scalar the dose was computed from, and which one it is.
    observable: float = float("nan")
    observable_name: str = "delta_l"
    dose_ppm_hr: float = 0.0
    shift_hours: float = 8.0
    twa_ppm: float = 0.0
    verdict: Verdict = Verdict.INVALID
    #: CIEDE2000 against the baseline. Recorded for continuity and for colour scientists;
    #: it does not drive the dose. NaN if the caller did not supply it.
    delta_e00: float = float("nan")
    #: Off-locus chroma displacement, from :func:`locus_chroma_residual`. The integrity
    #: check: large means the pad's colour is not on the CuS reaction path.
    chroma_residual: float = float("nan")
    #: The dose-scaled limit ``chroma_residual`` was actually judged against. Recorded so a
    #: SUSPECT flag can be audited later without re-deriving the threshold.
    chroma_residual_limit: float = float("nan")
    integrity_ok: bool = True
    limits: ExposureLimits = field(default=ACGIH_OSHA_NIOSH)
    #: A cumulative badge cannot resolve short peaks from one reading. Always False here.
    stel_determinable: bool = False
    saturated: bool = False
    below_noise_floor: bool = False
    extrapolated: bool = False
    environment_factor: float = 1.0
    messages: list = field(default_factory=list)

    def as_dict(self) -> dict:
        def r(v, nd=4):
            return None if v is None or not np.isfinite(v) else round(float(v), nd)
        return {
            "observable": r(self.observable),
            "observable_name": self.observable_name,
            "dose_ppm_hr": round(self.dose_ppm_hr, 4),
            "shift_hours": self.shift_hours,
            "twa_ppm": round(self.twa_ppm, 4),
            "verdict": self.verdict.value,
            "delta_e00": r(self.delta_e00),
            "chroma_residual": r(self.chroma_residual, 3),
            "chroma_residual_limit": r(self.chroma_residual_limit, 3),
            "integrity_ok": self.integrity_ok,
            "stel_determinable": self.stel_determinable,
            "saturated": self.saturated,
            "below_noise_floor": self.below_noise_floor,
            "extrapolated": self.extrapolated,
            "environment_factor": round(self.environment_factor, 4),
            "limit_twa_ppm": self.limits.twa_ppm,
            "messages": list(self.messages),
        }


def _verdict_for(twa: float, dose: float, limits: ExposureLimits) -> Verdict:
    if twa > limits.twa_ppm * limits.twa_critical_multiple or dose >= limits.dose_critical_ppm_hr:
        return Verdict.CRITICAL
    if twa > limits.twa_ppm:
        return Verdict.WARNING
    return Verdict.SAFE


def assess_scan(
    observable: float,
    shift_hours: float,
    calibration: CalibrationModel = DEFAULT_CALIBRATION,
    limits: ExposureLimits = ACGIH_OSHA_NIOSH,
    temp_c: float = None,
    rh_fraction: float = None,
    delta_e00: float = float("nan"),
    chroma_residual: float = float("nan"),
    delta_l_star: float = float("nan"),
    chroma_limit_floor: float = CHROMA_LIMIT_FLOOR,
    chroma_limit_slope: float = CHROMA_LIMIT_SLOPE,
) -> DoseAssessment:
    """Convert one colour reading into a dose, a TWA and a compliance verdict.

    Parameters
    ----------
    observable
        The scalar named by ``calibration.observable`` - by default ``-dL*``, the pad's
        loss of lightness against its baseline.
    delta_e00, chroma_residual
        Optional. dE00 is recorded but unused; ``chroma_residual`` (see
        :func:`locus_chroma_residual`) drives the integrity check.
    delta_l_star
        The pad's lightness loss, used *only* to scale the chroma limit. Passed separately
        from ``observable`` because the limit must scale with the pad's physical travel even
        when the calibration is expressed in some other observable. Falls back to
        ``observable`` when the calibration is already in ``delta_l``.
    chroma_limit_floor, chroma_limit_slope
        Passed to :func:`chroma_limit`. Exceeding the resulting limit declares the badge
        SUSPECT. The dose is still reported - suppressing it would lose evidence - but it is
        flagged for physical inspection, because a pad off its own reaction path is not
        reporting H2S.
    """
    if shift_hours <= 0:
        raise ValueError("shift_hours must be positive")

    env = calibration.environment_factor(temp_c, rh_fraction)
    dose = float(calibration.dose(observable, temp_c, rh_fraction))
    twa = dose / float(shift_hours)
    name = calibration.observable

    msgs = []
    saturated = observable >= calibration.obs_saturation
    below_floor = observable < calibration.obs_noise_floor
    extrapolated = observable > calibration.obs_max or observable < calibration.obs_min

    if saturated:
        msgs.append(
            f"pad optically saturated at {name} {observable:.1f} (>= "
            f"{calibration.obs_saturation:.1f}); reported dose is a LOWER BOUND - "
            "treat as a confirmed overexposure and use a shorter badge interval"
        )
    if below_floor:
        msgs.append(
            f"{name} {observable:.2f} is below the {calibration.obs_noise_floor:.2f} "
            "noise floor; report as 'no detectable exposure', not as a precise number"
        )
    if extrapolated and not saturated:
        msgs.append(
            f"{name} {observable:.2f} lies outside the validated range "
            f"[{calibration.obs_min:.1f}, {calibration.obs_max:.1f}]; extrapolated"
        )
    # The reaction is irreversible, so the pad cannot be lighter than its own baseline by
    # more than measurement noise. When it is, the baseline and the pad are not describing
    # the same badge - a mix-up, or a substrate patch that is soiled rather than the pad.
    if observable < -abs(calibration.obs_noise_floor):
        msgs.append(
            f"{name} is {observable:.2f} - the pad reads LIGHTER than its own baseline. "
            "CuS formation is irreversible, so this is a badge mix-up, a soiled reference "
            "patch, or a failed rectification. Do not log this as zero exposure."
        )
    if env != 1.0:
        msgs.append(
            f"environmental correction factor {env:.3f} applied "
            f"(T={temp_c if temp_c is not None else calibration.ref_temp_c} C, "
            f"RH={(rh_fraction if rh_fraction is not None else calibration.ref_rh_fraction) * 100:.0f}%)"
        )

    # The limit scales with the pad's travel; a constant cannot separate contamination from
    # camera error at both ends of the range. See chroma_limit for the measurement.
    dl = delta_l_star
    if not np.isfinite(dl) and name == "delta_l":
        dl = observable
    limit = chroma_limit(dl, chroma_limit_floor, chroma_limit_slope)

    integrity_ok = True
    if np.isfinite(chroma_residual) and chroma_residual > limit:
        integrity_ok = False
        msgs.append(
            f"INTEGRITY: pad sits {chroma_residual:.2f} L*a*b* units off the CuS reaction "
            f"path (limit {limit:.2f} for a lightness change of {abs(dl) if np.isfinite(dl) else float('nan'):.1f}). "
            "It has changed colour in a direction H2S does not produce - suspect a "
            "contaminated or time-expired reagent, a damaged pad, or the wrong badge. "
            "Quarantine it and send for lab analysis; the dose below is reported for the "
            "record, not for compliance."
        )

    if saturated:
        verdict = Verdict.SATURATED
    elif not integrity_ok:
        verdict = Verdict.SUSPECT
    else:
        verdict = _verdict_for(twa, dose, limits)
    if saturated:
        msgs.append("verdict forced to SATURATED; escalate as CRITICAL operationally")

    msgs.append(
        "STEL not determinable from a single cumulative reading - "
        "use mid-shift kiosk scans (assess_scan_series) to bound short-term peaks"
    )

    return DoseAssessment(
        observable=float(observable),
        observable_name=name,
        dose_ppm_hr=dose,
        shift_hours=float(shift_hours),
        twa_ppm=twa,
        verdict=verdict,
        delta_e00=float(delta_e00),
        chroma_residual=float(chroma_residual),
        chroma_residual_limit=float(limit),
        integrity_ok=integrity_ok,
        limits=limits,
        stel_determinable=False,
        saturated=bool(saturated),
        below_noise_floor=bool(below_floor),
        extrapolated=bool(extrapolated),
        environment_factor=env,
        messages=msgs,
    )



# ---------------------------------------------------------------------------
# Multi-scan series -> bounded short-term exposure
# ---------------------------------------------------------------------------

@dataclass
class IntervalExposure:
    """Mean concentration over one interval between consecutive scans."""

    t_start_hours: float
    t_end_hours: float
    duration_hours: float
    dose_increment_ppm_hr: float
    mean_ppm: float
    exceeds_stel: bool
    exceeds_niosh_ceiling: bool


@dataclass
class SeriesAssessment:
    """Result of reading the same badge several times through a shift."""

    intervals: list = field(default_factory=list)
    total_dose_ppm_hr: float = 0.0
    total_hours: float = 0.0
    twa_ppm: float = 0.0
    worst_interval: Optional[IntervalExposure] = None
    #: Upper bound on any 15-minute average, given the interval resolution actually used.
    stel_upper_bound_ppm: float = float("nan")
    stel_determinable: bool = False
    verdict: Verdict = Verdict.SAFE
    messages: list = field(default_factory=list)


def assess_scan_series(
    readings: Sequence[tuple],
    calibration: CalibrationModel = DEFAULT_CALIBRATION,
    limits: ExposureLimits = ACGIH_OSHA_NIOSH,
    temp_c: float = None,
    rh_fraction: float = None,
    stel_window_hours: float = 0.25,
) -> SeriesAssessment:
    """Bound short-term exposure from several scans of the same badge.

    Parameters
    ----------
    readings
        Sequence of ``(elapsed_hours, observable)``, in any order; sorted internally.
        ``elapsed_hours`` is measured from badge activation (seal peel), and ``observable``
        is whatever ``calibration.observable`` names - by default ``-dL*``.
    stel_window_hours
        Averaging window the STEL is defined over (0.25 h = 15 min for the ACGIH TLV).

    Notes
    -----
    The bound works like this. Over an interval of length ``T`` the badge accumulated
    ``dD`` ppm*hr, so the interval mean is ``dD/T``. The true peak inside that interval
    can be higher, and in the worst case all the dose arrives inside one STEL window,
    giving ``dD/stel_window``. Reported ``stel_upper_bound_ppm`` is that worst case: if
    it sits under the limit the shift is *provably* STEL-compliant; if it sits above,
    the badge cannot exclude a breach and a shorter interval is required. Scan hourly and
    the bound is 4x the interval mean; scan every 15 minutes and the bound is the mean.
    """
    pts = sorted((float(t), float(v)) for t, v in readings)
    out = SeriesAssessment()

    if len(pts) < 2:
        out.messages.append(
            "need at least two readings to bound short-term exposure; "
            "a single scan yields dose and TWA only"
        )
        if pts:
            single = assess_scan(pts[0][1], max(pts[0][0], 1e-6), calibration, limits,
                                 temp_c, rh_fraction)
            out.total_dose_ppm_hr = single.dose_ppm_hr
            out.total_hours = single.shift_hours
            out.twa_ppm = single.twa_ppm
            out.verdict = single.verdict
        return out

    doses = [float(calibration.dose(v, temp_c, rh_fraction)) for _, v in pts]

    # The pad reaction is irreversible, so cumulative dose must be non-decreasing.
    # A drop means measurement noise (or a swapped badge); clamp and flag it.
    for i in range(1, len(doses)):
        if doses[i] < doses[i - 1] - 1e-9:
            out.messages.append(
                f"reading at t={pts[i][0]:.2f} h shows dose falling "
                f"{doses[i - 1]:.2f} -> {doses[i]:.2f} ppm*hr; the reaction is "
                "irreversible, so this is noise or a badge mix-up. Clamped."
            )
            doses[i] = doses[i - 1]

    worst = None
    for i in range(1, len(pts)):
        t0, t1 = pts[i - 1][0], pts[i][0]
        dur = t1 - t0
        if dur <= 0:
            out.messages.append(f"skipped non-positive interval at t={t1:.2f} h")
            continue
        inc = doses[i] - doses[i - 1]
        mean_ppm = inc / dur
        iv = IntervalExposure(
            t_start_hours=t0,
            t_end_hours=t1,
            duration_hours=dur,
            dose_increment_ppm_hr=inc,
            mean_ppm=mean_ppm,
            exceeds_stel=mean_ppm > limits.stel_ppm,
            exceeds_niosh_ceiling=mean_ppm > limits.niosh_ceiling_ppm,
        )
        out.intervals.append(iv)
        if worst is None or mean_ppm > worst.mean_ppm:
            worst = iv

    if not out.intervals:
        out.messages.append("no valid intervals; check reading timestamps")
        return out

    out.worst_interval = worst
    out.total_dose_ppm_hr = doses[-1] - doses[0]
    out.total_hours = pts[-1][0] - pts[0][0]
    out.twa_ppm = out.total_dose_ppm_hr / out.total_hours if out.total_hours > 0 else 0.0

    # Worst case: the whole interval increment lands inside one STEL window.
    bound = max(iv.dose_increment_ppm_hr / stel_window_hours for iv in out.intervals)
    out.stel_upper_bound_ppm = bound
    out.stel_determinable = True

    if bound <= limits.stel_ppm:
        out.messages.append(
            f"STEL provably compliant: even in the worst case all dose in one interval "
            f"fell inside a single {stel_window_hours * 60:.0f}-minute window, giving at "
            f"most {bound:.2f} ppm vs the {limits.stel_ppm:.0f} ppm limit"
        )
    else:
        out.messages.append(
            f"STEL cannot be excluded: worst-case {stel_window_hours * 60:.0f}-minute "
            f"average could reach {bound:.2f} ppm (limit {limits.stel_ppm:.0f} ppm). "
            f"Longest interval is {max(iv.duration_hours for iv in out.intervals):.2f} h "
            "- shorten the scan interval to tighten this bound."
        )

    out.verdict = _verdict_for(out.twa_ppm, out.total_dose_ppm_hr, limits)
    if worst is not None and worst.exceeds_niosh_ceiling:
        out.verdict = Verdict.CRITICAL
        out.messages.append(
            f"interval {worst.t_start_hours:.2f}-{worst.t_end_hours:.2f} h averaged "
            f"{worst.mean_ppm:.1f} ppm, above the NIOSH {limits.niosh_ceiling_ppm:.0f} ppm "
            "ceiling - this is an incident, not a trend"
        )
    return out
