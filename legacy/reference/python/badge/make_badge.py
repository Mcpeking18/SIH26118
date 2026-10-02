"""
Print-ready badge artwork generator.

Produces four things:

1. ``badge`` - one badge head at real physical scale, for the moulded wristband label.
2. ``sheet`` - an A4 gang sheet of identical badges with cut marks, for production.
3. ``series`` - an A4 sheet of badges whose pads are **pre-shaded to known doses** using
   the forward reaction model.
4. ``card`` - the operator-facing visual comparator: the five-stage CuS colour ladder with
   its dose bands and verdicts, for reading a badge by eye when no phone is available.

The third one is the important one for a hackathon. It lets the entire reader stack -
detection, rectification, colour correction, dosimetry - be demonstrated and quantitatively
validated by printing a sheet and photographing it with a phone, *before* any wet chemistry
exists. Print it, shoot it under a sodium lamp, and the reader should recover the printed
dose. That is a real end-to-end accuracy claim obtainable in an afternoon.

Geometry comes from :mod:`engine.badge_spec`, never from constants here, so artwork and
reader cannot drift apart. The same applies to chemistry: the reagent name, the reaction
equation and the stage ladder are all imported, so a printed card cannot claim a different
chemistry from the one the reader is calibrated for.

Rendering rules that matter:

* Everything is drawn **without anti-aliasing**. ArUco decoding thresholds the image and a
  soft marker edge shifts the detected corner sub-pixel; soft patch edges bleed
  neighbouring colour into the sampled interior.
* Patch and pad colours are written as 8-bit sRGB directly, because PNG is an sRGB-encoded
  container. Writing linear values here would make every patch far too dark and the CCM
  would fit that error as if it were the illuminant.
* Output DPI is explicit and stamped on the sheet. A badge printed at the wrong scale
  still detects fine - the homography absorbs it - but the physical diffusion area changes,
  which silently invalidates the calibration. The printed ruler lets anyone check.
* The comparator card carries a PROVISIONAL stamp whenever
  :data:`engine.dosimetry.STAGE_TABLE_IS_VALIDATED` is false. An eye-read colour chart is a
  safety instrument in its own right, and shipping one that implies chamber-verified dose
  bands it does not have would be the single most misleading artefact in this repository.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from engine.badge_spec import (
    BADGE, BadgeSpec, PAD_STAGE_DOSE_BANDS, PAD_STAGE_LABELS, PAD_STAGE_NAMES,
    PAD_STAGE_SRGB, PATCHES, PATCH_NAMES, REACTION_EQUATION, REACTION_PRODUCT_NAME,
    REAGENT_NAME, SUBSTRATE_PATCH_INDICES,
)
from engine.colorimetry import linear_to_srgb
from engine.detect import generate_marker
from engine.dosimetry import (
    STAGE_TABLE_IS_VALIDATED, SYNTHETIC_CALIBRATION, ReactionModel, stage_for_dose,
)

__all__ = ["render_badge", "render_sheet", "render_series", "render_card",
           "CHEMISTRY_LINE", "A4_MM"]

A4_MM = (210.0, 297.0)
_WHITE = (255, 255, 255)
_BLACK = (0, 0, 0)

def _shout(chemical_name: str) -> str:
    """Upper-case a chemical name for print *without* destroying its formula.

    ``"Copper(II) Sulphate (CuSO4)".upper()`` yields ``CUSO4``, which is not a formula -
    element symbols are case-significant (Cu is copper, CU is nothing). So the descriptive
    words are upper-cased and the trailing parenthesised formula is passed through verbatim.
    """
    head, sep, tail = chemical_name.rpartition(" (")
    if not sep:
        return chemical_name.upper()
    return f"{head.upper()} ({tail}"


def _formula(chemical_name: str) -> str:
    """The trailing parenthesised formula, e.g. ``"Copper(II) Sulfide (CuS)"`` -> ``CuS``."""
    head, sep, tail = chemical_name.rpartition(" (")
    return tail.rstrip(")") if sep else chemical_name


#: The chemistry declaration stamped on every printed artefact. Built from the engine
#: constants rather than typed out, so it cannot drift from what the reader assumes.
CHEMISTRY_LINE = (
    f"CHEMICAL SENSING LAYER: {_shout(REAGENT_NAME)} -> "
    f"{_formula(REACTION_PRODUCT_NAME)}  |  {REACTION_EQUATION}"
)


def _mm(v: float, dpi: float) -> int:
    """Millimetres -> integer pixels at the given DPI."""
    return int(round(v * dpi / 25.4))


def _bgr(srgb) -> tuple:
    """(R, G, B) 0-255 -> OpenCV BGR tuple."""
    r, g, b = (int(round(float(c))) for c in srgb)
    return (b, g, r)


#: Cap height of Hershey Simplex at ``fontScale=1.0``, in pixels. Measured, not guessed:
#: ``cv2.getTextSize("H", FONT_HERSHEY_SIMPLEX, 1.0, 1)`` returns height 27 with baseline 0.
_HERSHEY_CAP_PX = 27.0


def _fs(cap_mm: float, dpi: float) -> float:
    """OpenCV ``fontScale`` that yields capitals ``cap_mm`` millimetres tall at ``dpi``.

    Necessary because ``fontScale`` is in units of the font's own design size, so a literal
    scale is a different physical size at every DPI. Type on a printed safety artefact has
    to be specified in millimetres or it is not specified at all - the comparator card was
    initially drawn with literal scales and came out with 0.9 mm capitals, which is below
    the ~1.5 mm floor for reliable reading at arm's length.
    """
    return float(cap_mm) * float(dpi) / 25.4 / _HERSHEY_CAP_PX


def pad_srgb_for_dose(dose_ppm_hr: float, model: ReactionModel = None) -> np.ndarray:
    """8-bit sRGB the pad should be printed as, for a given cumulative dose.

    Goes through linear reflectance (the reaction model's native domain) and encodes once
    at the end. This is the inverse of what the reader does, which is exactly the point:
    round-tripping print -> photograph -> read is what validates the pair.
    """
    model = model or ReactionModel()
    lin = np.asarray(model.pad_linear(float(dose_ppm_hr)), dtype=np.float64)
    return np.clip(np.round(linear_to_srgb(lin, max_value=1.0) * 255.0), 0, 255)


# ---------------------------------------------------------------------------
# Single badge head
# ---------------------------------------------------------------------------

def render_badge(
    spec: BadgeSpec = BADGE,
    dpi: float = 600.0,
    dose_ppm_hr: float = None,
    label: str = "",
    draw_well_outline: bool = True,
    model: ReactionModel = None,
    pad_linear: np.ndarray = None,
) -> np.ndarray:
    """Render one badge head as an 8-bit BGR image at ``dpi``.

    ``dose_ppm_hr`` shades the pad using the forward reaction model. ``None`` leaves the
    pad the pristine substrate tone, which is what production artwork wants (the real pad
    is a physical reagent disc dropped into the well, not printed).

    ``pad_linear`` overrides the pad with an arbitrary linear-RGB reflectance and ignores
    ``dose_ppm_hr`` for the pad. This exists to test the *integrity* check: the only way to
    verify that the reader rejects a pad which darkened by the wrong chemistry is to render
    one, and no dose can produce that colour by construction. Also useful for print-proofing
    a measured reagent lot whose tone differs from the model's endpoints.
    """
    problems = spec.validate()
    if problems:
        raise ValueError(
            "badge geometry does not close, refusing to write artwork:\n  - "
            + "\n  - ".join(problems)
        )

    n = _mm(spec.head_mm, dpi)
    img = np.full((n, n, 3), 255, dtype=np.uint8)
    px = lambda v: _mm(v, dpi)                      # noqa: E731 - local shorthand

    # ---- fiducials -------------------------------------------------------
    side = px(spec.marker_mm)
    for mid, (cx_mm, cy_mm) in zip(spec.marker_ids, spec.marker_centres_mm()):
        marker = generate_marker(int(mid), side)                 # uint8 grayscale
        m3 = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        x0, y0 = px(cx_mm) - side // 2, px(cy_mm) - side // 2
        img[y0:y0 + side, x0:x0 + side] = m3

    # ---- reactive well ---------------------------------------------------
    cx, cy = px(spec.centre_mm[0]), px(spec.centre_mm[1])
    if draw_well_outline:
        # Thin keyline only. A filled dark ring would sit inside the pad ROI's outer
        # margin and drag the sampled mean darker.
        cv2.circle(img, (cx, cy), px(spec.well_diameter_mm / 2.0),
                   (170, 170, 170), max(1, px(0.12)), lineType=cv2.LINE_8)

    if pad_linear is not None:
        lin = np.clip(np.asarray(pad_linear, dtype=np.float64).ravel()[:3], 0.0, 1.0)
        pad_colour = np.clip(np.round(linear_to_srgb(lin, max_value=1.0) * 255.0), 0, 255)
    elif dose_ppm_hr is None:
        pad_colour = PATCHES[SUBSTRATE_PATCH_INDICES[0]].srgb
    else:
        pad_colour = pad_srgb_for_dose(dose_ppm_hr, model)
    cv2.circle(img, (cx, cy), px(spec.pad_diameter_mm / 2.0),
               _bgr(pad_colour), -1, lineType=cv2.LINE_8)

    # ---- reference patch ring -------------------------------------------
    pside = px(spec.patch_mm)
    for patch, (mx, my) in zip(PATCHES, spec.patch_centres_mm()):
        x0, y0 = px(mx) - pside // 2, px(my) - pside // 2
        cv2.rectangle(img, (x0, y0), (x0 + pside - 1, y0 + pside - 1),
                      _bgr(patch.srgb), -1, lineType=cv2.LINE_8)

    # ---- human-readable label -------------------------------------------
    if label:
        scale = dpi / 600.0
        cv2.putText(img, label, (px(2.0), n - px(0.9)), cv2.FONT_HERSHEY_SIMPLEX,
                    0.34 * scale, (110, 110, 110), max(1, int(round(scale))),
                    cv2.LINE_AA)
    return img


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def _blank_a4(dpi: float) -> np.ndarray:
    return np.full((_mm(A4_MM[1], dpi), _mm(A4_MM[0], dpi), 3), 255, dtype=np.uint8)


def _draw_ruler(sheet: np.ndarray, dpi: float, x_mm: float, y_mm: float,
                length_mm: float = 50.0) -> None:
    """Print a 50 mm ruler so scale errors are caught by eye before chemistry is wasted."""
    x0, y0 = _mm(x_mm, dpi), _mm(y_mm, dpi)
    x1 = _mm(x_mm + length_mm, dpi)
    cv2.line(sheet, (x0, y0), (x1, y0), _BLACK, max(1, _mm(0.2, dpi)))
    for i in range(int(length_mm) + 1):
        x = _mm(x_mm + i, dpi)
        h = _mm(2.5 if i % 10 == 0 else (1.5 if i % 5 == 0 else 0.8), dpi)
        cv2.line(sheet, (x, y0), (x, y0 - h), _BLACK, max(1, _mm(0.15, dpi)))
    cv2.putText(sheet, f"{length_mm:.0f} mm - measure me before use",
                (x0, y0 + _mm(3.2, dpi)), cv2.FONT_HERSHEY_SIMPLEX,
                0.32 * dpi / 300.0, _BLACK, max(1, _mm(0.1, dpi)), cv2.LINE_AA)


def _place(sheet: np.ndarray, badge: np.ndarray, x_mm: float, y_mm: float,
           dpi: float, cut_marks: bool = True) -> None:
    x0, y0 = _mm(x_mm, dpi), _mm(y_mm, dpi)
    h, w = badge.shape[:2]
    if y0 + h > sheet.shape[0] or x0 + w > sheet.shape[1]:
        raise ValueError("badge does not fit on the sheet at the requested position")
    sheet[y0:y0 + h, x0:x0 + w] = badge

    if cut_marks:
        g = _mm(1.0, dpi)
        t = max(1, _mm(0.15, dpi))
        for (cx, cy) in ((x0, y0), (x0 + w, y0), (x0, y0 + h), (x0 + w, y0 + h)):
            sx = -1 if cx == x0 else 1
            sy = -1 if cy == y0 else 1
            cv2.line(sheet, (cx + sx * g, cy), (cx + sx * (g + _mm(2.0, dpi)), cy),
                     (150, 150, 150), t)
            cv2.line(sheet, (cx, cy + sy * g), (cx, cy + sy * (g + _mm(2.0, dpi))),
                     (150, 150, 150), t)


def _grid_positions(spec: BadgeSpec, dpi: float, margin_mm: float, gap_mm: float,
                    top_mm: float) -> list:
    step = spec.head_mm + gap_mm
    cols = int((A4_MM[0] - 2 * margin_mm + gap_mm) // step)
    rows = int((A4_MM[1] - top_mm - margin_mm + gap_mm) // step)
    return [(margin_mm + c * step, top_mm + r * step)
            for r in range(rows) for c in range(cols)]


def render_sheet(spec: BadgeSpec = BADGE, dpi: float = 600.0,
                 margin_mm: float = 10.0, gap_mm: float = 6.0,
                 prefix: str = "MRPL") -> np.ndarray:
    """A4 gang sheet of production badges (pristine pads)."""
    sheet = _blank_a4(dpi)
    top = 25.0
    cv2.putText(sheet, f"SIH26118 H2S dosimeter badge  |  {spec.head_mm:.0f}x"
                       f"{spec.head_mm:.0f} mm  |  {dpi:.0f} dpi  |  print at 100%, "
                       "no scaling, no colour management",
                (_mm(margin_mm, dpi), _mm(8.0, dpi)), cv2.FONT_HERSHEY_SIMPLEX,
                0.42 * dpi / 300.0, _BLACK, max(1, _mm(0.12, dpi)), cv2.LINE_AA)
    cv2.putText(sheet, CHEMISTRY_LINE,
                (_mm(margin_mm, dpi), _mm(12.0, dpi)), cv2.FONT_HERSHEY_SIMPLEX,
                0.34 * dpi / 300.0, (90, 90, 90), max(1, _mm(0.1, dpi)), cv2.LINE_AA)
    cv2.putText(sheet, f"pad substrate: {spec.pad_substrate}",
                (_mm(margin_mm, dpi), _mm(15.5, dpi)), cv2.FONT_HERSHEY_SIMPLEX,
                0.30 * dpi / 300.0, (120, 120, 120), max(1, _mm(0.09, dpi)), cv2.LINE_AA)
    _draw_ruler(sheet, dpi, margin_mm, 20.0)

    for i, (x, y) in enumerate(_grid_positions(spec, dpi, margin_mm, gap_mm, top)):
        _place(sheet, render_badge(spec, dpi, None, f"{prefix}-{i + 1:03d}"), x, y, dpi)
    return sheet


def render_series(spec: BadgeSpec = BADGE, dpi: float = 600.0,
                  doses=None, margin_mm: float = 10.0, gap_mm: float = 6.0,
                  model: ReactionModel = None) -> tuple:
    """A4 sheet of badges pre-shaded to known doses, plus the ground-truth table.

    Returns ``(sheet, truth)`` where ``truth`` is a list of dicts with the printed dose,
    the model's dE00 and the pad sRGB - i.e. the answer key the test harness scores
    against.
    """
    model = model or ReactionModel()
    if doses is None:
        # Geometric-ish spacing: dense where the compliance decision lives (a 1 ppm TWA
        # over 8 h is 8 ppm*hr, so the 2-16 range is what actually has to be right),
        # sparse in the saturated tail where the badge only reports a lower bound.
        doses = [0.0, 1.0, 2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0,
                 32.0, 48.0, 64.0, 96.0, 128.0, 160.0, 200.0]

    sheet = _blank_a4(dpi)
    top = 25.0
    cv2.putText(sheet, "SIH26118 SYNTHETIC TEST SERIES - printed doses, "
                       "NOT a real exposure record",
                (_mm(margin_mm, dpi), _mm(8.0, dpi)), cv2.FONT_HERSHEY_SIMPLEX,
                0.42 * dpi / 300.0, (0, 0, 200), max(1, _mm(0.12, dpi)), cv2.LINE_AA)
    cv2.putText(sheet, CHEMISTRY_LINE,
                (_mm(margin_mm, dpi), _mm(12.0, dpi)), cv2.FONT_HERSHEY_SIMPLEX,
                0.34 * dpi / 300.0, (90, 90, 90), max(1, _mm(0.1, dpi)), cv2.LINE_AA)
    cv2.putText(sheet, f"pad tones from ReactionModel(d_char={model.d_char:g}) along the "
                       f"{len(PAD_STAGE_SRGB)}-stage CuS locus - synthetic, not measured",
                (_mm(margin_mm, dpi), _mm(15.5, dpi)), cv2.FONT_HERSHEY_SIMPLEX,
                0.30 * dpi / 300.0, (120, 120, 120), max(1, _mm(0.09, dpi)), cv2.LINE_AA)
    _draw_ruler(sheet, dpi, margin_mm, 20.0)

    pos = _grid_positions(spec, dpi, margin_mm, gap_mm, top)
    if len(doses) > len(pos):
        raise ValueError(f"{len(doses)} doses requested but only {len(pos)} fit on A4")

    truth = []
    for (x, y), dose in zip(pos, doses):
        badge = render_badge(spec, dpi, dose, f"{dose:g} ppm.hr", model=model)
        _place(sheet, badge, x, y, dpi)
        stage = stage_for_dose(dose)
        truth.append({
            "dose_ppm_hr": float(dose),
            "expected_delta_l_star": float(model.delta_l(dose)),
            "expected_delta_e00": float(model.delta_e(dose)),
            "pad_srgb": [int(v) for v in pad_srgb_for_dose(dose, model)],
            # Recorded so the answer key shows what an eye-read would have called this
            # badge next to what the reader measures. They are two different instruments
            # and the harness should be able to compare them.
            "stage": int(stage["stage"]),
            "stage_label": stage["label"],
            "stage_validated": bool(stage["validated"]),
            "x_mm": float(x), "y_mm": float(y),
        })
    return sheet, truth


# ---------------------------------------------------------------------------
# Operator comparator card
# ---------------------------------------------------------------------------

def render_card(spec: BadgeSpec = BADGE, dpi: float = 600.0,
                width_mm: float = 90.0, margin_mm: float = 6.0) -> np.ndarray:
    """The five-stage CuS colour ladder as a pocket comparator card.

    This is the fallback instrument: no phone, no network, no reader - hold the card next to
    the badge and read the nearest chip. It is printed at the same pad diameter as the badge
    so the comparison is like-for-like, because a chip much larger or smaller than the pad
    biases the eye (simultaneous contrast scales with the area of the surround).

    WHY THE CHIPS ARE THE STAGE ANCHORS, NOT MODEL OUTPUT AT THE BAND MIDPOINTS
    -------------------------------------------------------------------------
    The two disagree, and the disagreement is the honest part. The chip colours are the
    specified visual appearance ladder; the dose bands beside them are the specification's
    claim about which dose produces that appearance. Reproducing those bands with the
    forward model would need ``d_char`` near 3 rather than 55 - i.e. it would require
    asserting that CuSO4 is roughly 18x more sensitive than the lead acetate the model was
    built on, which is the wrong direction on the chemistry. So the chips are drawn as
    specified, and the bands are stamped PROVISIONAL until a chamber says otherwise.

    Printing the model's colours instead would look self-consistent and *be* wrong: it would
    quietly redefine the appearance ladder to match an unvalidated kinetic constant.
    """
    stages = len(PAD_STAGE_SRGB)
    chip_mm = spec.pad_diameter_mm
    row_mm = chip_mm + 3.0
    header_mm = 23.0
    footer_mm = 17.0 if not STAGE_TABLE_IS_VALIDATED else 8.0
    height_mm = header_mm + stages * row_mm + footer_mm

    card = np.full((_mm(height_mm, dpi), _mm(width_mm, dpi), 3), 255, dtype=np.uint8)
    thin = max(1, _mm(0.12, dpi))
    text_col_mm = margin_mm + chip_mm + 4.0
    overflow = []

    def text(txt, x_mm, y_mm, cap_mm=1.8, colour=_BLACK, weight=None):
        """Draw text with a physically-specified cap height, and record any overflow.

        ``y_mm`` is the *baseline*, so rows can be spaced by cap height plus leading
        without the drawn glyphs creeping into the row below.
        """
        scale = _fs(cap_mm, dpi)
        w = max(1, int(round(_mm(0.035 * cap_mm + 0.06, dpi))))
        (tw, _th), _b = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, scale, w)
        if x_mm + tw * 25.4 / dpi > width_mm - margin_mm:
            overflow.append((txt, round(x_mm + tw * 25.4 / dpi, 1)))
        cv2.putText(card, txt, (_mm(x_mm, dpi), _mm(y_mm, dpi)),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, colour,
                    weight if weight is not None else w, cv2.LINE_AA)

    # ---- header ----------------------------------------------------------
    text("H2S EXPOSURE COMPARATOR", margin_mm, 6.0, 3.2)
    text(f"{_shout(REAGENT_NAME)} -> {_formula(REACTION_PRODUCT_NAME)}",
         margin_mm, 10.2, 1.9, (70, 70, 70))
    text(REACTION_EQUATION, margin_mm, 13.6, 1.7, (120, 120, 120))
    text("Compare in daylight or white light. Sodium lamps mislead the eye.",
         margin_mm, 17.4, 1.5, (120, 120, 120))
    cv2.line(card, (_mm(margin_mm, dpi), _mm(19.6, dpi)),
             (_mm(width_mm - margin_mm, dpi), _mm(19.6, dpi)), (200, 200, 200), thin)
    text("dose (ppm.hr)", text_col_mm, 22.4, 1.4, (150, 150, 150))

    # ---- the ladder ------------------------------------------------------
    lo = 0.0
    for i, srgb in enumerate(PAD_STAGE_SRGB):
        y = header_mm + i * row_mm
        side = _mm(chip_mm, dpi)
        ccx = _mm(margin_mm, dpi) + side // 2
        ccy = _mm(y, dpi) + side // 2
        # Circular, matching the pad, not a square swatch: the eye judges a disc against a
        # disc more reliably, and the operator is looking at a disc.
        cv2.circle(card, (ccx, ccy), side // 2, _bgr(srgb), -1, lineType=cv2.LINE_8)
        cv2.circle(card, (ccx, ccy), side // 2, (190, 190, 190), thin, lineType=cv2.LINE_8)

        hi = PAD_STAGE_DOSE_BANDS[i] if i < len(PAD_STAGE_DOSE_BANDS) else float("inf")
        band = f"{lo:g} - {hi:g}" if np.isfinite(hi) else f"over {lo:g}"
        text(f"{i + 1}.  {band}", text_col_mm, y + 3.4, 2.4)
        text(PAD_STAGE_LABELS[i], text_col_mm, y + 6.9, 1.9, (60, 60, 60))
        text(PAD_STAGE_NAMES[i], text_col_mm, y + 9.8, 1.5, (150, 150, 150))
        lo = hi

    # ---- footer ----------------------------------------------------------
    fy = header_mm + stages * row_mm + 4.5
    if not STAGE_TABLE_IS_VALIDATED:
        # Loud, boxed, and at the bottom where the eye lands after reading the ladder.
        cv2.rectangle(card, (_mm(margin_mm, dpi), _mm(fy - 3.6, dpi)),
                      (_mm(width_mm - margin_mm, dpi), _mm(fy + 8.4, dpi)),
                      (60, 60, 200), thin)
        text("PROVISIONAL - dose bands are specified, not chamber-verified.",
             margin_mm + 1.8, fy, 1.7, (60, 60, 200))
        text("Colours are authoritative; the ppm.hr figures are not.",
             margin_mm + 1.8, fy + 3.4, 1.5, (90, 90, 160))
        text("Use the phone reader for any compliance or evacuation decision.",
             margin_mm + 1.8, fy + 6.6, 1.5, (90, 90, 160))
    else:
        text("Dose bands chamber-verified.", margin_mm, fy, 1.7, (60, 60, 60))

    if overflow:
        raise ValueError(
            f"comparator card text does not fit inside {width_mm:g} mm - widen the card or "
            f"shrink the type; offenders (text, right edge mm): {overflow}"
        )
    return card


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate print-ready SIH26118 badge artwork.")
    ap.add_argument("mode", choices=("badge", "sheet", "series", "card"))
    ap.add_argument("-o", "--out", default=None, help="output PNG path")
    ap.add_argument("--dpi", type=float, default=600.0)
    ap.add_argument("--dose", type=float, default=None,
                    help="shade the pad to this dose in ppm*hr (badge mode)")
    ap.add_argument("--label", default="")
    ap.add_argument("--outdir", default="out")
    args = ap.parse_args(argv)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.mode == "badge":
        img = render_badge(BADGE, args.dpi, args.dose, args.label)
        out = Path(args.out) if args.out else outdir / "badge.png"
        cv2.imwrite(str(out), img)
        print(f"wrote {out}  {img.shape[1]}x{img.shape[0]} px "
              f"= {BADGE.head_mm:g} mm at {args.dpi:g} dpi")

    elif args.mode == "sheet":
        img = render_sheet(BADGE, args.dpi)
        out = Path(args.out) if args.out else outdir / "badge_sheet_a4.png"
        cv2.imwrite(str(out), img)
        print(f"wrote {out}  {img.shape[1]}x{img.shape[0]} px (A4 at {args.dpi:g} dpi)")

    elif args.mode == "card":
        img = render_card(BADGE, args.dpi)
        out = Path(args.out) if args.out else outdir / "comparator_card.png"
        cv2.imwrite(str(out), img)
        print(f"wrote {out}  {img.shape[1]}x{img.shape[0]} px at {args.dpi:g} dpi")
        print(f"chemistry: {CHEMISTRY_LINE}")
        if not STAGE_TABLE_IS_VALIDATED:
            print("NOTE: dose bands are PROVISIONAL - the card says so on its face. "
                  "Chamber-verify them before this card is used for any decision.")

    else:
        import csv
        img, truth = render_series(BADGE, args.dpi)
        out = Path(args.out) if args.out else outdir / "badge_series_a4.png"
        cv2.imwrite(str(out), img)
        csv_path = out.with_suffix(".truth.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(truth[0].keys()))
            w.writeheader()
            for row in truth:
                r = dict(row)
                r["pad_srgb"] = " ".join(str(v) for v in row["pad_srgb"])
                w.writerow(r)
        print(f"wrote {out}  ({len(truth)} badges) and {csv_path}")
        print(f"calibration in use: {SYNTHETIC_CALIBRATION.notes}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
