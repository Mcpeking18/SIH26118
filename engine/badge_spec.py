"""
Canonical badge specification for SIH26118 - single source of truth for geometry.

Both the print artwork generator (`badge/make_badge.py`) and the reader
(`engine/roi.py`) import from here, so artwork and reader can never drift apart.
Everything is defined in real-world millimetres and converted to pixels on demand.

DIMENSIONAL CORRECTION vs the original concept note
---------------------------------------------------
The original spec put a 14 mm well plus a patch ring plus 3 mm corner fiducials on a
22 mm-wide wristband. That does not close: 14 mm well + 2x2 mm ring + 2x3 mm markers
is about 25 mm of required width, i.e. 3 mm wider than the strap itself, and it leaves
zero quiet zone around the ArUco markers (which need >= 1 module of white border or
they will not be detected at all).

The fix used here is standard wearable practice: a 30 x 30 mm badge head (a paddle,
like a watch face) moulded onto the 22 mm strap. The well shrinks slightly to 12 mm.
This preserves the whole optical scheme, keeps a 1.25 mm quiet zone on every marker,
and is manufacturable by the same injection-moulding step.

    +----------------------------------+  30 mm
    | [M0]      P0  P1  P2       [M1]  |
    |     P11   .------------.    P3   |
    |           |  reactive  |         |
    |     P10   |    pad     |    P4   |
    |           |  d=10 mm   |         |
    |     P9    '------------'    P5   |
    | [M3]      P8  P7  P6       [M2]  |
    +----------------------------------+
    M0..M3 = ArUco 4x4 markers, IDs 0..3, 4.5 mm
    P0..P11 = reference patches, 2.2 mm, on a 8.6 mm radius ring
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .colorimetry import lab_to_srgb, srgb_to_lab

__all__ = [
    "BADGE",
    "BadgeSpec",
    "Patch",
    "PATCHES",
    "PATCH_NAMES",
    "REFERENCE_SRGB",
    "REFERENCE_LAB",
    "NEUTRAL_INDICES",
    "SUBSTRATE_PATCH_INDICES",
    "UNEXPOSED_PAD_LAB",
    "FULLY_REACTED_PAD_LAB",
    "PRINTABLE_MIN",
    "PRINTABLE_MAX",
    "REAGENT_NAME",
    "REACTION_PRODUCT_NAME",
    "REACTION_EQUATION",
    "PAD_STAGE_ANCHORS_LAB",
    "PAD_STAGE_NAMES",
    "PAD_STAGE_LABELS",
    "PAD_STAGE_SRGB",
    "PAD_STAGE_DOSE_BANDS",
    "SUPPLIED_STAGE_HEX_UNCORRECTED",
]


# ---------------------------------------------------------------------------
# Chemistry (CuSO4 -> CuS)
# ---------------------------------------------------------------------------

REAGENT_NAME: str = "Copper(II) Sulphate (CuSO4)"
REACTION_PRODUCT_NAME: str = "Copper(II) Sulfide (CuS)"
REACTION_EQUATION: str = "CuSO4 + H2S -> CuS(s) + H2SO4"


# ---------------------------------------------------------------------------
# Pad endpoints & Color Anchors
# ---------------------------------------------------------------------------

#: L*a*b* of a pristine, unexposed reactive pad (Pale cyan / ice blue).
UNEXPOSED_PAD_LAB: np.ndarray = np.array([91.20, -3.80, -1.50], dtype=np.float64)

#: Saturated (fully-reacted) dense CuS pad.
FULLY_REACTED_PAD_LAB: np.ndarray = np.array([13.00, 1.80, 2.40], dtype=np.float64)

#: sRGB derived directly from UNEXPOSED_PAD_LAB for reference swatches
_SUBSTRATE_SRGB: tuple = tuple(
    int(round(float(v))) for v in lab_to_srgb(UNEXPOSED_PAD_LAB, max_value=255.0)
)

#: Multi-stage CIELAB anchors across the CuS formation curve
PAD_STAGE_ANCHORS_LAB: np.ndarray = np.array([
    [91.20, -3.80, -1.50],    # unexposed baseline (pale ice blue)
    [74.20, -4.19, 12.22],    # reagent spending (muted olive/khaki)
    [40.16,  9.40, 27.32],    # CuS accumulating (medium bronze / amber)
    [15.99,  8.14, 13.42],    # dense CuS (deep chocolate / umber)
    [13.00,  1.80,  2.40],    # saturated CuS
], dtype=np.float64)

PAD_STAGE_NAMES: tuple = (
    "Pale Ice Blue / Off-White",
    "Muted Olive-Grey / Khaki",
    "Medium Bronze / Amber Brown",
    "Deep Chocolate / Umber",
    "Deep Charcoal / Jet Black",
)

PAD_STAGE_LABELS: tuple = (
    "SAFE - unexposed baseline",
    "PERMISSIBLE - trace background",
    "COMPLIANT / ACTION",
    "WARNING - exceeds 8-hr TLV",
    "CRITICAL / EVACUATE",
)

PAD_STAGE_SRGB: tuple = tuple(
    tuple(int(round(float(v))) for v in lab_to_srgb(lab, max_value=255.0))
    for lab in PAD_STAGE_ANCHORS_LAB[:4]
) + ((13, 12, 12),)

SUPPLIED_STAGE_HEX_UNCORRECTED: tuple = (
    "#E2EDF8", "#B8B8A0", "#7A5832", "#382315", "#0D0C0C",
)

PAD_STAGE_DOSE_BANDS: tuple = (0.2, 1.5, 8.0, 20.0)


# ---------------------------------------------------------------------------
# Reference Patches
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Patch:
    name: str
    srgb: tuple
    role: str          # 'neutral' | 'chroma' | 'substrate'
    note: str = ""


PATCHES: tuple = (
    Patch("WHITE",       (243, 243, 242), "neutral",   "paper white, near D65"),
    Patch("CYAN",        (22, 163, 218),  "chroma",    "-a*, -b* axis"),
    Patch("SUBSTRATE_A", _SUBSTRATE_SRGB, "substrate", "baseline, paired with SUBSTRATE_B"),
    Patch("MAGENTA",     (200, 24, 124),  "chroma",    "+a* axis"),
    Patch("GREY_50",     (119, 119, 119), "neutral",   "18% reflectance, L* ~ 50"),
    Patch("YELLOW",      (243, 214, 26),  "chroma",    "+b* axis, brightest chroma"),
    Patch("BLACK",       (35, 35, 35),    "neutral",   "printable black, not 0/0/0"),
    Patch("RED",         (196, 48, 43),   "chroma",    "+a*, +b* quadrant"),
    Patch("SUBSTRATE_B", _SUBSTRATE_SRGB, "substrate", "baseline, opposite SUBSTRATE_A"),
    Patch("GREEN",       (60, 140, 78),   "chroma",    "-a*, +b* quadrant"),
    Patch("GREY_20",     (75, 75, 75),    "neutral",   "shadow tone"),
    Patch("BLUE",        (46, 62, 148),   "chroma",    "-b* axis"),
)

PRINTABLE_MIN: int = 8
PRINTABLE_MAX: int = 247

PATCH_NAMES: tuple = tuple(p.name for p in PATCHES)
REFERENCE_SRGB: np.ndarray = np.array([p.srgb for p in PATCHES], dtype=np.float64)
REFERENCE_LAB: np.ndarray = srgb_to_lab(REFERENCE_SRGB, max_value=255.0)

NEUTRAL_INDICES: tuple = tuple(
    i for i, p in enumerate(PATCHES) if p.role == "neutral"
)

SUBSTRATE_PATCH_INDICES: tuple = tuple(
    i for i, p in enumerate(PATCHES) if p.role == "substrate"
)


# ---------------------------------------------------------------------------
# Physical Geometry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BadgeSpec:
    head_mm: float = 30.0
    strap_width_mm: float = 22.0
    strap_length_mm: float = 240.0
    strap_thickness_mm: float = 3.5

    well_diameter_mm: float = 12.0
    well_depth_mm: float = 2.2
    pad_diameter_mm: float = 10.0
    membrane_diameter_mm: float = 11.5
    scrubber_diameter_mm: float = 11.5
    pad_substrate: str = "silica / borosilicate glass-fibre (acid-stable)"

    marker_mm: float = 4.5
    marker_inset_mm: float = 3.5
    marker_quiet_zone_mm: float = 1.25
    aruco_dict: str = "DICT_4X4_50"
    marker_ids: tuple = (0, 1, 2, 3)

    patch_mm: float = 2.2
    patch_ring_radius_mm: float = 8.6
    patch_start_deg: float = -90.0
    n_patches: int = 12

    pad_sample_fraction: float = 0.75
    patch_sample_fraction: float = 0.70

    white_probe_inner_mm: float = 0.9
    white_probe_outer_mm: float = 2.0
    px_per_mm: float = 20.0

    @property
    def canonical_px(self) -> int:
        return int(round(self.head_mm * self.px_per_mm))

    @property
    def centre_mm(self) -> tuple:
        c = self.head_mm / 2.0
        return (c, c)

    def marker_centres_mm(self) -> np.ndarray:
        lo = self.marker_inset_mm
        hi = self.head_mm - self.marker_inset_mm
        return np.array([[lo, lo], [hi, lo], [hi, hi], [lo, hi]], dtype=np.float64)

    def marker_outer_corners_mm(self) -> np.ndarray:
        h = self.marker_mm / 2.0
        out = []
        for cx, cy in self.marker_centres_mm():
            out.append([[cx - h, cy - h], [cx + h, cy - h],
                        [cx + h, cy + h], [cx - h, cy + h]])
        return np.array(out, dtype=np.float64)

    def patch_centres_mm(self) -> np.ndarray:
        cx, cy = self.centre_mm
        r = self.patch_ring_radius_mm
        step = 360.0 / self.n_patches
        pts = []
        for i in range(self.n_patches):
            th = math.radians(self.patch_start_deg + i * step)
            pts.append([cx + r * math.cos(th), cy + r * math.sin(th)])
        return np.array(pts, dtype=np.float64)

    def white_field_probes_mm(self) -> np.ndarray:
        cx, cy = self.centre_mm
        out = []
        r_in = (self.well_diameter_mm / 2.0 + (self.patch_ring_radius_mm - self.patch_mm / 2.0)) / 2.0
        for k in range(8):
            th = math.radians(self.patch_start_deg + 22.5 + k * 45.0)
            out.append([cx + r_in * math.cos(th), cy + r_in * math.sin(th), self.white_probe_inner_mm])

        r_out = self.head_mm / 2.0 - self.white_probe_outer_mm / 2.0 - 0.8
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            out.append([cx + dx * r_out, cy + dy * r_out, self.white_probe_outer_mm])

        return np.array(out, dtype=np.float64)

    def mm_to_px(self, pts_mm) -> np.ndarray:
        return np.asarray(pts_mm, dtype=np.float64) * self.px_per_mm

    def validate(self, verbose: bool = False) -> list:
        problems = []
        half = self.marker_mm / 2.0
        hp = self.patch_mm / 2.0
        cx, cy = self.centre_mm

        for i, (mx, my) in enumerate(self.marker_centres_mm()):
            margin = min(mx - half, my - half, self.head_mm - (mx + half), self.head_mm - (my + half))
            if margin < self.marker_quiet_zone_mm - 1e-9:
                problems.append(f"marker {i}: quiet zone {margin:.2f} mm < required {self.marker_quiet_zone_mm:.2f} mm")

        well_r = self.well_diameter_mm / 2.0
        for i, (px, py) in enumerate(self.patch_centres_mm()):
            d = math.hypot(px - cx, py - cy)
            if d - hp * math.sqrt(2) < well_r:
                problems.append(f"patch P{i}: overlaps well")

        for i, (px, py) in enumerate(self.patch_centres_mm()):
            for j, (mx, my) in enumerate(self.marker_centres_mm()):
                if (abs(px - mx) < hp + half) and (abs(py - my) < hp + half):
                    problems.append(f"patch P{i} overlaps marker {j}")

        from .colorimetry import delta_e_ciede2000
        for i in SUBSTRATE_PATCH_INDICES:
            sub_lab = srgb_to_lab(np.array(PATCHES[i].srgb, dtype=np.float64), max_value=255.0)
            d = float(delta_e_ciede2000(sub_lab, UNEXPOSED_PAD_LAB))
            if d > 0.5:
                problems.append(f"{PATCHES[i].name} is {d:.2f} dE00 from UNEXPOSED_PAD_LAB")

        if verbose and problems:
            print("\n".join(problems))
        return problems


BADGE = BadgeSpec()


def load_measured_patches(path) -> np.ndarray:
    import csv
    table = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            table[row["name"].strip().upper()] = (
                float(row["R"]), float(row["G"]), float(row["B"])
            )
    missing = [n for n in PATCH_NAMES if n not in table]
    if missing:
        raise ValueError(f"measured patch file is missing: {', '.join(missing)}")
    return np.array([table[n] for n in PATCH_NAMES], dtype=np.float64)


if __name__ == "__main__":
    problems = BADGE.validate(verbose=True)
    print("Geometry check:", "OK" if not problems else problems)