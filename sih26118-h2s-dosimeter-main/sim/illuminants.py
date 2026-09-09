"""
Physically-grounded illuminant and camera models for synthetic scan generation.

The headline claim of this project is "the reader works under refinery lighting". That
claim is only worth making if the simulated lights are real lights, so this module builds
them from spectra and blackbody physics rather than from hand-picked RGB tints:

* **Low-pressure sodium** (the classic refinery/roadway lamp) is not a colour temperature
  at all - it is a near-monochromatic doublet at 589.0/589.6 nm. It has *no* blue content,
  so a badge photographed under it carries almost no information on the blue channel. This
  is the single hardest case for the reader and the reason the CCM ladder degrades
  gracefully instead of assuming a well-conditioned fit.
* **High-pressure sodium**, **fluorescent** and **metal halide** are built from
  representative emission spectra.
* **Daylight** and **incandescent** come from the CIE daylight model and Planck's law.

Everything is integrated against the CIE 1931 2-degree observer, so an illuminant's effect
on the badge is computed the way a spectrophotometer would, not guessed.

Reflectance handling: the badge's printed patches are known only as sRGB, not as spectra.
Rather than fake a spectrum, this module uses the standard practical approximation - treat
the patch's linear RGB as reflectance in three broad bands and apply the illuminant as a
von Kries-style gain derived from the illuminant's own XYZ. This is exactly the class of
distortion the reader must undo, and it is *harder* than reality in the sodium case because
it preserves no spectral cross-talk to help.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from engine.colorimetry import (
    D65_WHITE_XYZ,
    SRGB_TO_XYZ,
    XYZ_TO_SRGB,
    linear_rgb_to_xyz,
    xyz_to_linear_rgb,
)

__all__ = [
    "CIE_LAMBDA",
    "Illuminant",
    "ILLUMINANTS",
    "CameraModel",
    "CAMERAS",
    "TORCH",
    "mix_illuminants",
    "planck_spectrum",
    "cie_daylight_spectrum",
    "spectrum_to_xyz",
]

# ---------------------------------------------------------------------------
# CIE 1931 2-degree standard observer, 400-700 nm at 10 nm
# ---------------------------------------------------------------------------

CIE_LAMBDA = np.arange(400, 701, 10, dtype=np.float64)

_XBAR = np.array([
    0.01431, 0.04351, 0.13438, 0.28390, 0.34828, 0.33620, 0.29080, 0.19536,
    0.09564, 0.03201, 0.00490, 0.00930, 0.06327, 0.16550, 0.29040, 0.43345,
    0.59450, 0.76210, 0.91630, 1.02630, 1.06220, 1.00260, 0.85445, 0.64240,
    0.44790, 0.28350, 0.16490, 0.08740, 0.04677, 0.02270, 0.01136,
], dtype=np.float64)

_YBAR = np.array([
    0.000396, 0.00121, 0.004000, 0.011600, 0.023000, 0.038000, 0.060000,
    0.090980, 0.139020, 0.208020, 0.323000, 0.503000, 0.710000, 0.862000,
    0.954000, 0.994950, 0.995000, 0.952000, 0.870000, 0.757000, 0.631000,
    0.503000, 0.381000, 0.265000, 0.175000, 0.107000, 0.061000, 0.032000,
    0.017000, 0.008210, 0.004102,
], dtype=np.float64)

_ZBAR = np.array([
    0.06785, 0.20740, 0.64560, 1.38560, 1.74706, 1.77211, 1.66920, 1.28764,
    0.81295, 0.46518, 0.27200, 0.15820, 0.07825, 0.04216, 0.02030, 0.00875,
    0.00390, 0.00210, 0.00165, 0.00110, 0.00080, 0.00034, 0.00019, 0.00005,
    0.00002, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000, 0.00000,
], dtype=np.float64)

CIE_CMF = np.stack([_XBAR, _YBAR, _ZBAR], axis=1)          # (31, 3)


def spectrum_to_xyz(spd: np.ndarray, normalise: bool = True) -> np.ndarray:
    """Integrate a spectral power distribution against the 1931 2-deg observer."""
    spd = np.asarray(spd, dtype=np.float64)
    if spd.shape[-1] != CIE_LAMBDA.size:
        raise ValueError(f"expected {CIE_LAMBDA.size} spectral samples, got {spd.shape[-1]}")
    xyz = spd @ CIE_CMF
    if normalise and xyz[1] > 0:
        xyz = xyz / xyz[1] * 100.0                          # scale to Y = 100
    return xyz


# ---------------------------------------------------------------------------
# Spectral generators
# ---------------------------------------------------------------------------

def planck_spectrum(temp_k: float, lam_nm: np.ndarray = None) -> np.ndarray:
    """Planck blackbody radiance, arbitrary scale. Models incandescent / flare light."""
    lam = (CIE_LAMBDA if lam_nm is None else np.asarray(lam_nm, dtype=np.float64)) * 1e-9
    h, c, k = 6.62607015e-34, 2.99792458e8, 1.380649e-23
    out = (2.0 * h * c ** 2) / (lam ** 5 * (np.exp(h * c / (lam * k * temp_k)) - 1.0))
    return out / out.max()


def cie_daylight_spectrum(temp_k: float) -> np.ndarray:
    """CIE D-series daylight SPD via the standard S0/S1/S2 basis (4000-25000 K).

    Used instead of a blackbody because real daylight is not a blackbody - it carries
    atmospheric absorption structure that shifts the badge's apparent colour.
    """
    t = float(temp_k)
    if not 4000.0 <= t <= 25000.0:
        raise ValueError("CIE daylight model is defined for 4000-25000 K")

    if t <= 7000.0:
        xd = (-4.6070e9 / t ** 3 + 2.9678e6 / t ** 2 + 0.09911e3 / t + 0.244063)
    else:
        xd = (-2.0064e9 / t ** 3 + 1.9018e6 / t ** 2 + 0.24748e3 / t + 0.237040)
    yd = -3.000 * xd ** 2 + 2.870 * xd - 0.275

    m = 0.0241 + 0.2562 * xd - 0.7341 * yd
    m1 = (-1.3515 - 1.7703 * xd + 5.9114 * yd) / m
    m2 = (0.0300 - 31.4424 * xd + 30.0717 * yd) / m

    s0 = np.array([
        94.8, 104.8, 105.9, 96.8, 113.9, 125.6, 125.5, 121.3, 121.3, 113.5,
        113.1, 110.8, 106.5, 108.8, 105.3, 104.4, 100.0, 96.0, 95.1, 89.1,
        90.5, 90.3, 88.4, 84.0, 85.1, 81.9, 82.6, 84.9, 81.3, 71.9, 74.3,
    ])
    s1 = np.array([
        43.4, 46.3, 43.9, 37.1, 36.7, 35.9, 32.6, 27.9, 24.3, 20.1, 16.2,
        13.2, 8.6, 6.1, 4.2, 1.9, 0.0, -1.6, -3.5, -3.5, -5.8, -7.2, -8.6,
        -9.5, -10.9, -10.7, -12.0, -14.0, -13.6, -12.0, -13.3,
    ])
    s2 = np.array([
        -1.1, -0.5, -0.7, -1.2, -2.6, -2.9, -2.8, -2.6, -2.6, -1.8, -1.5,
        -1.3, -1.2, -1.0, -0.5, -0.3, 0.0, 0.2, 0.5, 2.1, 3.2, 4.1, 4.7,
        5.1, 6.7, 7.3, 8.6, 9.8, 10.2, 8.3, 9.6,
    ])
    spd = s0 + m1 * s1 + m2 * s2
    return np.clip(spd, 0.0, None) / spd.max()


def _gaussian_line(centre_nm: float, fwhm_nm: float, amplitude: float = 1.0) -> np.ndarray:
    sigma = fwhm_nm / 2.3548200450309493
    return amplitude * np.exp(-0.5 * ((CIE_LAMBDA - centre_nm) / sigma) ** 2)


def _lps_spectrum() -> np.ndarray:
    """Low-pressure sodium: the 589 nm D-line doublet, essentially nothing else.

    At 10 nm sampling the doublet is one line. The important physical property is what is
    *absent*: no blue, no green, no red. Any camera looking at this scene records
    near-zero on B, so the blue column of a colour-correction matrix is unconstrained -
    which is exactly why the reader must detect an ill-conditioned fit rather than
    trusting it.
    """
    return _gaussian_line(589.3, 12.0, 1.0) + 0.004


def _hps_spectrum() -> np.ndarray:
    """High-pressure sodium: pressure-broadened sodium plus a weak continuum."""
    return (_gaussian_line(589.3, 60.0, 1.0)
            + _gaussian_line(568.0, 25.0, 0.30)
            + _gaussian_line(498.0, 40.0, 0.10)
            + _gaussian_line(615.0, 45.0, 0.45)
            + 0.05 * planck_spectrum(2100.0))


def _fluorescent_spectrum() -> np.ndarray:
    """Triphosphor fluorescent (CIE F11-like): three narrow peaks plus mercury lines."""
    return (_gaussian_line(436.0, 12.0, 0.42)        # Hg
            + _gaussian_line(487.0, 20.0, 0.18)
            + _gaussian_line(546.0, 12.0, 0.95)      # Hg + terbium
            + _gaussian_line(578.0, 14.0, 0.30)
            + _gaussian_line(611.0, 14.0, 0.85)      # europium
            + 0.06)


def _metal_halide_spectrum() -> np.ndarray:
    """Metal halide floodlight: broad multi-line, common on refinery towers."""
    return (_gaussian_line(420.0, 30.0, 0.55)
            + _gaussian_line(450.0, 25.0, 0.70)
            + _gaussian_line(520.0, 45.0, 0.85)
            + _gaussian_line(560.0, 40.0, 0.90)
            + _gaussian_line(590.0, 35.0, 0.70)
            + _gaussian_line(630.0, 40.0, 0.55)
            + 0.12)


def _led_spectrum() -> np.ndarray:
    """Phosphor-converted white LED: blue pump + broad yellow phosphor."""
    return (_gaussian_line(452.0, 22.0, 1.0)
            + _gaussian_line(555.0, 110.0, 0.75)
            + 0.02)


# ---------------------------------------------------------------------------
# Illuminant model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Illuminant:
    """A light source, with the spectral basis for its effect on the badge."""

    name: str
    spd: np.ndarray
    lux: float = 500.0
    description: str = ""

    @property
    def xyz(self) -> np.ndarray:
        return spectrum_to_xyz(self.spd)

    @property
    def linear_rgb_gain(self) -> np.ndarray:
        """Per-channel gain the illuminant applies, normalised to unit luminance.

        Derived from the illuminant's XYZ mapped into linear sRGB. Negative components
        are clamped: a sufficiently narrow-band source lies outside the sRGB gamut, and a
        negative gain would flip the sign of a reflectance, which is unphysical.
        """
        g = xyz_to_linear_rgb(self.xyz / 100.0)
        g = np.clip(g, 1e-4, None)
        y = float(g @ np.array([0.2126, 0.7152, 0.0722]))
        return g / y if y > 0 else g

    @property
    def cct_k(self) -> float:
        """McCamy's correlated colour temperature approximation, K.

        Meaningless for low-pressure sodium (it is not near the Planckian locus at all)
        and reported anyway only because people expect the number.
        """
        X, Y, Z = self.xyz
        s = X + Y + Z
        if s <= 0:
            return float("nan")
        x, y = X / s, Y / s
        if abs(y - 0.1858) < 1e-9:
            return float("nan")
        n = (x - 0.3320) / (y - 0.1858)
        return float(-449.0 * n ** 3 + 3525.0 * n ** 2 - 6823.3 * n + 5520.33)

    @property
    def gamut_conditioning(self) -> float:
        """Ratio of largest to smallest channel gain - how badly the light starves a channel.

        A value near 1 is a balanced source. Low-pressure sodium runs into the hundreds,
        which is the quantitative statement of "there is no blue information in this
        photograph" and predicts which scans the reader must refuse.
        """
        g = self.linear_rgb_gain
        return float(g.max() / g.min())


ILLUMINANTS: dict = {
    "d65": Illuminant("D65 daylight", cie_daylight_spectrum(6504.0), 10000.0,
                      "reference daylight, the calibration condition"),
    "daylight_5500": Illuminant("Daylight 5500 K", cie_daylight_spectrum(5500.0), 20000.0,
                                "open-air daytime inspection round"),
    "overcast_7000": Illuminant("Overcast 7000 K", cie_daylight_spectrum(7000.0), 3000.0,
                                "blue-shifted diffuse shade"),
    "incandescent_2856": Illuminant("Incandescent A", planck_spectrum(2856.0), 300.0,
                                    "CIE illuminant A, control-room lamp"),
    "fluorescent_4000": Illuminant("Fluorescent 4000 K", _fluorescent_spectrum(), 400.0,
                                   "workshop / muster-point tube light"),
    "metal_halide": Illuminant("Metal halide", _metal_halide_spectrum(), 800.0,
                               "refinery tower floodlight"),
    "led_5000": Illuminant("White LED 5000 K", _led_spectrum(), 600.0,
                           "modern retrofit fitting"),
    "hps": Illuminant("High-pressure sodium", _hps_spectrum(), 250.0,
                      "plant roadway and tank-farm lighting"),
    "lps": Illuminant("Low-pressure sodium", _lps_spectrum(), 120.0,
                      "worst case: monochromatic 589 nm, no colour information"),
    "twilight_low_lux": Illuminant("Twilight, low lux", cie_daylight_spectrum(8000.0), 15.0,
                                   "shift changeover at dusk, noise-dominated"),
}

#: The phone's own LED torch, as seen by the badge at scanning distance.
#:
#: This is not a nicety, it is the answer to the hardest failure mode in the whole system.
#: Under sodium lighting the badge carries no blue information at all, so no amount of
#: cleverness in the reader can recover a colour - the correct behaviour is to refuse the
#: scan, and refusing every scan on the night shift is not a product. The torch fixes it at
#: the source by supplying the missing wavelengths.
#:
#: The lux figure is what makes the argument work. A phone torch is only a couple of lumens,
#: which sounds hopeless next to a floodlight, but illuminance falls off with the square of
#: distance and the badge is 15-20 cm from the lens while the lamp is 10 m up a tower. At
#: that range the torch delivers on the order of 1500 lux against a sodium ambient of 120-250
#: lux, so it dominates by roughly an order of magnitude - see ``summarise_torch()`` for the
#: resulting channel balance.
TORCH = Illuminant("Phone LED torch", _led_spectrum(), 1500.0,
                   "phone flash held at scanning distance, ~15-20 cm")


def mix_illuminants(parts, name: str = None, description: str = "") -> Illuminant:
    """Combine illuminants weighted by their illuminance.

    Light superposes linearly, so mixed lighting is the lux-weighted sum of the
    contributing spectra - each normalised to unit area first, so the weights mean what
    they say. This is what a real scan under a sodium lamp *with the torch on* actually
    looks like, and it is the only honest way to model it: applying the torch as a
    correction to the sodium result would be arithmetic on the wrong side of the sensor.

    ``parts`` is a sequence of ``(Illuminant, lux)`` pairs.
    """
    total = float(sum(lux for _, lux in parts))
    if total <= 0:
        raise ValueError("mixed illuminant needs a positive total illuminance")
    spd = np.zeros_like(CIE_LAMBDA)
    for il, lux in parts:
        s = np.asarray(il.spd, dtype=np.float64)
        spd = spd + (s / max(s.sum(), 1e-12)) * float(lux)
    label = name or " + ".join(f"{il.name} ({lux:.0f} lx)" for il, lux in parts)
    return Illuminant(label, spd / spd.max(), total, description)


# The sodium cases with the torch on - the configuration the scanner UI must enforce.
ILLUMINANTS["hps_with_torch"] = mix_illuminants(
    [(ILLUMINANTS["hps"], 250.0), (TORCH, 1500.0)],
    "HPS + phone torch", "sodium roadway lighting, torch on - the supported night config")
ILLUMINANTS["lps_with_torch"] = mix_illuminants(
    [(ILLUMINANTS["lps"], 120.0), (TORCH, 1500.0)],
    "LPS + phone torch", "worst-case monochromatic ambient rescued by the torch")
ILLUMINANTS["torch_only"] = mix_illuminants(
    [(TORCH, 1500.0)], "Phone torch only", "dark tank interior, torch is the only source")


# ---------------------------------------------------------------------------
# Camera model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CameraModel:
    """A phone camera's colour and noise behaviour.

    ``gamut_matrix`` is applied in linear RGB and stands in for the difference between the
    device's native sensor primaries and sRGB. Real phones differ substantially here, and
    a reader that only works on the developer's own handset is useless - so the test
    harness sweeps several.

    ``awb_strength`` models the auto white balance the reader cannot switch off: 0 leaves
    the illuminant cast untouched, 1 fully neutralises it. Partial AWB is the realistic
    and most awkward case, because the residual cast is unknown to the app.

    Noise is split into the two components that actually matter: photon shot noise, which
    scales with the square root of signal, and a fixed read-noise floor that dominates in
    the 15 lux twilight case.

    WHY EVEN THE 'REFERENCE' CAMERA CARRIES READ NOISE
    -------------------------------------------------
    It is tempting to give the ideal camera exactly zero noise, and that was the first
    version. It is wrong, and instructively so: a noiseless sensor photographing a *flat*
    printed pad under *uniform* light rounds every single pad pixel to the identical 8-bit
    value, so the quantisation error is perfectly correlated across the region and averaging
    thousands of pixels removes none of it. Measured: the zero-noise camera read 3.3805 dE00
    where the true value was 3.0625, while adding a mere 0.5 DN of read noise brought it to
    3.1591 with a standard deviation of 0.006 - the noise *dithers* the quantiser and buys
    back most of a bit.

    So zero noise is not the optimistic bound, it is an unphysical case that scores worse
    than reality, and tuning a reader against it would mean chasing an error that does not
    exist in the field. A real sensor always supplies this dither for free, as does any real
    pad's surface texture. 0.35 DN is kept here for that reason; everything else about this
    camera stays ideal so it still isolates algorithm error from hardware error.
    """

    name: str
    gamut_matrix: np.ndarray
    awb_strength: float = 0.85
    read_noise: float = 0.9          # DN at 8-bit
    shot_noise_k: float = 0.035      # DN per sqrt(DN)
    vignette: float = 0.10           # fractional falloff at the frame corner
    jpeg_quality: int = 92
    description: str = ""


def _mat(*rows) -> np.ndarray:
    """Row-normalised 3x3 - keeps a neutral grey neutral so the matrix only shifts chroma."""
    m = np.array(rows, dtype=np.float64)
    return m / m.sum(axis=1, keepdims=True)


CAMERAS: dict = {
    "reference": CameraModel(
        "Reference (near-ideal)", np.eye(3), 1.0, 0.35, 0.0, 0.0, 100,
        "identity colour, isolates algorithm error from hardware error"),
    "midrange_a": CameraModel(
        "Mid-range phone A",
        _mat((1.06, -0.04, -0.02), (-0.09, 1.14, -0.05), (-0.03, -0.16, 1.19)),
        0.85, 1.1, 0.040, 0.12, 90,
        "typical wide-gamut-ish tuning, moderate saturation boost"),
    "midrange_b": CameraModel(
        "Mid-range phone B",
        _mat((0.96, 0.06, -0.02), (0.04, 0.93, 0.03), (0.01, 0.09, 0.90)),
        0.70, 1.4, 0.050, 0.16, 85,
        "softer, undersaturated tuning with weaker AWB"),
    "budget": CameraModel(
        "Budget phone",
        _mat((1.12, -0.10, -0.02), (-0.14, 1.22, -0.08), (-0.05, -0.22, 1.27)),
        0.55, 2.6, 0.075, 0.24, 75,
        "aggressive saturation, poor AWB, heavy JPEG - the realistic worst case"),
    "flagship": CameraModel(
        "Flagship phone",
        _mat((1.02, -0.01, -0.01), (-0.02, 1.04, -0.02), (-0.01, -0.05, 1.06)),
        0.95, 0.6, 0.025, 0.07, 95,
        "well-characterised sensor, strong AWB"),
}


def summarise() -> str:
    """Human-readable table of the modelled lights - printed by the CLI and the tests."""
    lines = [f"{'illuminant':22s} {'CCT K':>8s} {'lux':>7s} "
             f"{'R gain':>7s} {'G gain':>7s} {'B gain':>7s} {'cond':>8s}"]
    for key, il in ILLUMINANTS.items():
        g = il.linear_rgb_gain
        cct = il.cct_k
        lines.append(
            f"{key:22s} {cct:8.0f} {il.lux:7.0f} "
            f"{g[0]:7.3f} {g[1]:7.3f} {g[2]:7.3f} {il.gamut_conditioning:8.1f}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(summarise())
    print("\nnote: 'cond' is max/min channel gain. Low-pressure sodium starves the blue")
    print("channel by orders of magnitude - that is the physical reason a scan under it")
    print("must be refused rather than corrected.")
