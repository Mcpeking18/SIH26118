"""
CIEDE2000 verification against the official supplementary test data of
Sharma, Wu & Dalal (2005), Color Research & Application 30(1), 21-30.

These 34 pairs are not random: pairs 1-6 probe the blue-region rotation term R_T,
pairs 7-16 sit on the hue discontinuity at 0/360 degrees and on zero chroma, and
pairs 17-34 are real-surface differences from the CIE test set. An implementation
that fumbles the four-branch mean-hue rule or the zero-chroma special case passes
the easy pairs and fails loudly on 9-16.

Run:  python3 tests/test_ciede2000.py
"""

from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np

from engine.colorimetry import (
    delta_e_ciede2000,
    srgb_to_lab,
    lab_to_srgb,
    xyz_to_lab,
    lab_to_xyz,
)

# (L1, a1, b1, L2, a2, b2, expected dE00)
SHARMA_2005 = [
    (50.0000,  2.6772, -79.7751, 50.0000,  0.0000, -82.7485,  2.0425),
    (50.0000,  3.1571, -77.2803, 50.0000,  0.0000, -82.7485,  2.8615),
    (50.0000,  2.8361, -74.0200, 50.0000,  0.0000, -82.7485,  3.4412),
    (50.0000, -1.3802, -84.2814, 50.0000,  0.0000, -82.7485,  1.0000),
    (50.0000, -1.1848, -84.8006, 50.0000,  0.0000, -82.7485,  1.0000),
    (50.0000, -0.9009, -85.5211, 50.0000,  0.0000, -82.7485,  1.0000),
    (50.0000,  0.0000,   0.0000, 50.0000, -1.0000,   2.0000,  2.3669),
    (50.0000, -1.0000,   2.0000, 50.0000,  0.0000,   0.0000,  2.3669),
    (50.0000,  2.4900,  -0.0010, 50.0000, -2.4900,   0.0009,  7.1792),
    (50.0000,  2.4900,  -0.0010, 50.0000, -2.4900,   0.0010,  7.1792),
    (50.0000,  2.4900,  -0.0010, 50.0000, -2.4900,   0.0011,  7.2195),
    (50.0000,  2.4900,  -0.0010, 50.0000, -2.4900,   0.0012,  7.2195),
    (50.0000, -0.0010,   2.4900, 50.0000,  0.0009,  -2.4900,  4.8045),
    (50.0000, -0.0010,   2.4900, 50.0000,  0.0010,  -2.4900,  4.8045),
    (50.0000, -0.0010,   2.4900, 50.0000,  0.0011,  -2.4900,  4.7461),
    (50.0000,  2.5000,   0.0000, 50.0000,  0.0000,  -2.5000,  4.3065),
    (50.0000,  2.5000,   0.0000, 73.0000, 25.0000, -18.0000, 27.1492),
    (50.0000,  2.5000,   0.0000, 61.0000, -5.0000,  29.0000, 22.8977),
    (50.0000,  2.5000,   0.0000, 56.0000, -27.0000, -3.0000, 31.9030),
    (50.0000,  2.5000,   0.0000, 58.0000, 24.0000,  15.0000, 19.4535),
    (50.0000,  2.5000,   0.0000, 50.0000,  3.1736,   0.5854,  1.0000),
    (50.0000,  2.5000,   0.0000, 50.0000,  3.2972,   0.0000,  1.0000),
    (50.0000,  2.5000,   0.0000, 50.0000,  1.8634,   0.5757,  1.0000),
    (50.0000,  2.5000,   0.0000, 50.0000,  3.2592,   0.3350,  1.0000),
    (60.2574, -34.0099, 36.2677, 60.4626, -34.1751, 39.4387,  1.2644),
    (63.0109, -31.0961, -5.8663, 62.8187, -29.7946, -4.0864,  1.2630),
    (61.2901,   3.7196, -5.3901, 61.4292,   2.2480, -4.9620,  1.8731),
    (35.0831, -44.1164,  3.7933, 35.0232, -40.0716,  1.5901,  1.8645),
    (22.7233,  20.0904, -46.6940, 23.0331, 14.9730, -42.5619,  2.0373),
    (36.4612,  47.8580, 18.3852, 36.2715,  50.5065, 21.2231,  1.4146),
    (90.8027,  -2.0831,  1.4410, 91.1528,  -1.6435,  0.0447,  1.4441),
    (90.9257,  -0.5406, -0.9208, 88.6381,  -0.8985, -0.7239,  1.5381),
    ( 6.7747,  -0.2908, -2.4247,  5.8714,  -0.0985, -2.2286,  0.6377),
    ( 2.0776,   0.0795, -1.1350,  0.9033,  -0.0636, -0.5514,  0.9082),
]

TOL = 1e-4


def test_sharma_dataset():
    fails = []
    for i, (L1, a1, b1, L2, a2, b2, expected) in enumerate(SHARMA_2005, start=1):
        got = delta_e_ciede2000([L1, a1, b1], [L2, a2, b2])
        if abs(got - expected) > TOL:
            fails.append((i, expected, got, abs(got - expected)))
    if fails:
        print(f"  FAIL {len(fails)}/{len(SHARMA_2005)} pairs outside {TOL}:")
        for i, exp, got, err in fails:
            print(f"    pair {i:2d}: expected {exp:9.4f}  got {got:9.4f}  err {err:.2e}")
        return False
    print(f"  ok  all {len(SHARMA_2005)} Sharma/Wu/Dalal pairs match within {TOL}")
    return True


def test_symmetry_and_identity():
    """dE00(x,x) == 0 and dE00 is symmetric (both required by CIE 142-2001)."""
    rng = np.random.default_rng(7)
    lab = np.column_stack([
        rng.uniform(0, 100, 4000),
        rng.uniform(-90, 90, 4000),
        rng.uniform(-90, 90, 4000),
    ])
    lab2 = np.roll(lab, 1, axis=0)
    self_de = delta_e_ciede2000(lab, lab)
    fwd = delta_e_ciede2000(lab, lab2)
    rev = delta_e_ciede2000(lab2, lab)
    ok = True
    if np.max(np.abs(self_de)) > 1e-12:
        print(f"  FAIL identity: max dE00(x,x) = {np.max(np.abs(self_de)):.3e}")
        ok = False
    if np.max(np.abs(fwd - rev)) > 1e-10:
        print(f"  FAIL symmetry: max |dE(a,b)-dE(b,a)| = {np.max(np.abs(fwd - rev)):.3e}")
        ok = False
    if not np.all(np.isfinite(fwd)):
        print("  FAIL non-finite dE00 produced")
        ok = False
    if ok:
        print("  ok  identity, symmetry and finiteness hold over 4000 random pairs")
    return ok


def test_vectorisation():
    """Vectorised call must equal the scalar loop, and shapes must be preserved."""
    rng = np.random.default_rng(11)
    a = rng.uniform([0, -60, -60], [100, 60, 60], size=(37, 3))
    b = rng.uniform([0, -60, -60], [100, 60, 60], size=(37, 3))
    vec = delta_e_ciede2000(a, b)
    loop = np.array([delta_e_ciede2000(a[i], b[i]) for i in range(len(a))])
    img_a = a.reshape(37, 1, 3).repeat(3, axis=1)
    img_b = b.reshape(37, 1, 3).repeat(3, axis=1)
    img = delta_e_ciede2000(img_a, img_b)
    ok = True
    if np.max(np.abs(vec - loop)) > 1e-12:
        print(f"  FAIL vector/scalar mismatch {np.max(np.abs(vec - loop)):.3e}")
        ok = False
    if img.shape != (37, 3):
        print(f"  FAIL image-shaped call returned {img.shape}, expected (37, 3)")
        ok = False
    if ok:
        print("  ok  vectorised == scalar loop; (H,W,3) input yields (H,W) output")
    return ok


def test_scale_is_explicit():
    """Regression: 8-bit near-black must not be mistaken for normalised full-scale.

    The triplet (1, 0, 0) is the canonical trap - max(rgb) == 1.0, so any
    "guess the scale" heuristic decodes it as full-scale red and lands 79 dE away.
    """
    dark = srgb_to_lab([1, 0, 0], max_value=255.0)
    full = srgb_to_lab([1, 0, 0], max_value=1.0)
    ok = True
    if dark[0] > 0.5:
        print(f"  FAIL 8-bit (1,0,0) decoded as L*={dark[0]:.2f}, expected near 0")
        ok = False
    if abs(full[0] - 53.2408) > 1e-3:
        print(f"  FAIL normalised (1,0,0) gave L*={full[0]:.4f}, expected 53.2408")
        ok = False
    if ok:
        print(f"  ok  scale is explicit: 8-bit L*={dark[0]:.4f}, "
              f"normalised L*={full[0]:.4f}")
    return ok


def test_srgb_primaries():
    """Anchor against the published sRGB/D65 L*a*b* values for white and primaries."""
    expected = {
        (255, 255, 255): (100.0000,   0.0000,    0.0000),
        (0, 0, 0):       (  0.0000,   0.0000,    0.0000),
        (255, 0, 0):     ( 53.2408,  80.0925,   67.2032),
        (0, 255, 0):     ( 87.7347, -86.1827,   83.1793),
        (0, 0, 255):     ( 32.2970,  79.1875, -107.8602),
    }
    fails = []
    for rgb, exp in expected.items():
        got = srgb_to_lab(list(rgb))
        if np.abs(got - np.array(exp)).max() > 5e-4:
            fails.append((rgb, exp, np.round(got, 4)))
    if fails:
        for rgb, exp, got in fails:
            print(f"  FAIL rgb={rgb} expected {exp} got {tuple(got)}")
        return False
    print(f"  ok  sRGB white and RGB primaries match published D65 L*a*b* values")
    return True


def _lab_via_decimal(r8, g8, b8, prec=50):
    """sRGB -> L*a*b* recomputed with 50-digit Decimal arithmetic.

    A deliberately separate code path from engine.colorimetry: scalar Decimal maths,
    exact rational companding constants, no numpy, no vectorisation, no `np.where`.
    Agreement to 1e-9 therefore tests the *formulation* (matrix, white point, knee),
    not merely numpy self-consistency.
    """
    from decimal import Decimal, getcontext

    getcontext().prec = prec
    third = Decimal(1) / Decimal(3)

    def lin(v):
        x = Decimal(int(v)) / Decimal(255)
        if x <= Decimal("0.04045"):
            return x / Decimal("12.92")
        return ((x + Decimal("0.055")) / Decimal("1.055")) ** Decimal("2.4")

    rgb = [lin(r8), lin(g8), lin(b8)]
    M = [
        ["0.4124564", "0.3575761", "0.1804375"],
        ["0.2126729", "0.7151522", "0.0721750"],
        ["0.0193339", "0.1191920", "0.9503041"],
    ]
    xyz = [sum(Decimal(M[i][j]) * rgb[j] for j in range(3)) * 100 for i in range(3)]
    white = [Decimal("95.047"), Decimal("100"), Decimal("108.883")]
    eps = Decimal(216) / Decimal(24389)
    kappa = Decimal(24389) / Decimal(27)
    f = []
    for v, w in zip(xyz, white):
        ratio = v / w
        f.append(ratio ** third if ratio > eps else (kappa * ratio + 16) / 116)
    return (
        float(116 * f[1] - 16),
        float(500 * (f[0] - f[1])),
        float(200 * (f[1] - f[2])),
    )


def test_lab_against_decimal_reference():
    """Strict: our L*a*b* must match a 50-digit Decimal recomputation.

    The colour set deliberately includes the sRGB primaries, the neutral axis, and
    near-black values that straddle the L* companding knee (ratio ~ 216/24389),
    which is where lookup-table implementations lose accuracy.
    """
    probes = [
        (255, 255, 255), (0, 0, 0), (128, 128, 128), (255, 0, 0), (0, 255, 0),
        (0, 0, 255), (14, 29, 29), (8, 8, 8), (9, 9, 9), (10, 10, 10),
        (3, 1, 0), (1, 0, 0), (2, 2, 2), (243, 243, 242), (35, 45, 60),
        (200, 190, 150), (60, 42, 30), (77, 63, 51),
    ]
    worst, worst_at = 0.0, None
    for p in probes:
        ref = np.array(_lab_via_decimal(*p))
        got = srgb_to_lab(list(p))
        err = float(np.abs(ref - got).max())
        if err > worst:
            worst, worst_at = err, (p, ref, got)
    if worst > 1e-9:
        p, ref, got = worst_at
        print(f"  FAIL max deviation {worst:.3e} at rgb={p}")
        print(f"    decimal ref {np.round(ref, 8)}")
        print(f"    ours        {np.round(got, 8)}")
        return False
    print(f"  ok  L*a*b* matches 50-digit Decimal reference to {worst:.1e} "
          f"over {len(probes)} colours (incl. knee cases)")
    return True


def test_lab_against_opencv():
    """Loose cross-check against OpenCV as a third implementation.

    OpenCV's cvtColor uses an interpolated 1024-entry sRGB gamma table and a spline
    LUT for the cube root, so it carries its own error - up to ~0.3 L*a*b* units on
    near-black colours sitting at the companding knee, where we were verified exact
    against Decimal above. This test therefore asserts on the *median* (structural
    agreement) with a generous cap on the max, and exists only to catch gross errors
    such as a swapped matrix row or a D50/D65 white-point mix-up.
    """
    try:
        import cv2
    except ImportError:
        print("  skip  opencv not available")
        return True
    rng = np.random.default_rng(3)
    rgb = rng.integers(0, 256, size=(4096, 3)).astype(np.float64)
    ours = srgb_to_lab(rgb)
    img = (rgb.reshape(-1, 1, 3) / 255.0).astype(np.float32)
    theirs = cv2.cvtColor(img, cv2.COLOR_RGB2Lab).reshape(-1, 3).astype(np.float64)
    err = np.abs(ours - theirs)
    med, p99, worst = np.median(err), np.percentile(err, 99), err.max()
    # OpenCV's LUT error is systematic, ~0.08 median / ~0.4 worst-case against an
    # exact reference. These bounds catch structural faults, not precision.
    if med > 0.15 or worst > 0.6:
        print(f"  FAIL vs OpenCV: median {med:.4f}, p99 {p99:.4f}, max {worst:.4f}")
        return False
    print(f"  ok  agrees with OpenCV: median {med:.3f}, p99 {p99:.3f}, max {worst:.3f} "
          f"(OpenCV LUT noise floor)")
    return True


def test_roundtrips():
    """Lab->sRGB->Lab and XYZ->Lab->XYZ must be self-inverse (needed by the simulator)."""
    rng = np.random.default_rng(5)
    rgb = rng.integers(0, 256, size=(2000, 3)).astype(np.float64)
    lab = srgb_to_lab(rgb)
    back = lab_to_srgb(lab, max_value=255.0)
    rgb_err = np.abs(rgb - back).max()

    xyz = lab_to_xyz(lab)
    lab_again = xyz_to_lab(xyz)
    lab_err = np.abs(lab - lab_again).max()

    ok = True
    if rgb_err > 1e-6:
        print(f"  FAIL sRGB round-trip error {rgb_err:.3e}")
        ok = False
    if lab_err > 1e-9:
        print(f"  FAIL XYZ/Lab round-trip error {lab_err:.3e}")
        ok = False
    if ok:
        print(f"  ok  round-trips exact (sRGB {rgb_err:.1e}, Lab {lab_err:.1e})")
    return ok


def main():
    print("CIEDE2000 / colorimetry verification")
    print("-" * 68)
    results = {
        "Sharma 2005 reference dataset": test_sharma_dataset(),
        "identity / symmetry":           test_symmetry_and_identity(),
        "vectorisation":                 test_vectorisation(),
        "explicit input scale":          test_scale_is_explicit(),
        "sRGB primaries":                test_srgb_primaries(),
        "L*a*b* vs Decimal reference":   test_lab_against_decimal_reference(),
        "L*a*b* vs OpenCV":              test_lab_against_opencv(),
        "round-trips":                   test_roundtrips(),
    }
    print("-" * 68)
    bad = [k for k, v in results.items() if not v]
    if bad:
        print(f"FAILED: {', '.join(bad)}")
        return 1
    print(f"PASSED all {len(results)} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
