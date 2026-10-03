# SIH26118 — Final Submission Material

> Built strictly from the approved corrected fact sheets (Pass 1 + Pass 2).

---

## POLISHED ABSTRACT (~250 words)

Workers in hydrogen sulfide (H₂S) sour-service areas at oil refineries operate in environments where intrinsically safe operation is required and active electronic dosimeters face significant certification barriers. Existing passive colorimetric badges require operators to compare a color change against a printed reference ladder — a process that is subjective, lighting-dependent, and produces no digital record.

We present a passive, zero-electronics wristband dosimeter coupled with quantitative smartphone-based image analysis. The sensing element is a CuSO₄·5H₂O strip on Whatman Grade 1 paper beneath an ePTFE diffusion membrane. Exposure to H₂S converts CuSO₄ to insoluble CuS, darkening the pad irreversibly in proportion to cumulative dose, while avoiding the heavy metal toxicity of conventional lead acetate.

The badge (30 × 40 mm) incorporates four 8 mm ArUco fiducial markers for geometric rectification and twelve reference color patches in a cross layout for illumination and camera normalization. A native Kotlin/OpenCV Android application executes a four-stage deterministic pipeline: perspective rectification via homography, spatial flat-field correction, ridge-regularized Color Correction Matrix fitting from the on-badge patches, and CIELAB lightness analysis. The primary dose observable is −dL* (lightness drop), selected over CIEDE2000 for its resistance to chroma noise on this near-achromatic reaction path. A chemical locus integrity check rejects badges exhibiting off-path chroma displacement inconsistent with CuS formation.

The measured exposure record can be synchronized through a backend service to a centralized Factory/HSE dashboard, enabling digital traceability and work-area exposure analysis.

Preliminary experiments have demonstrated visible color response under both liquid Na₂S and gaseous H₂S exposure. Validated quantitative calibration against certified H₂S reference concentrations, including generation of the gas-phase color-response trajectory, is the planned next stage.

---

## COMPACT ABSTRACT (~130 words)

Workers in refinery sour-service areas require intrinsically safe H₂S monitoring. We present a passive CuSO₄·5H₂O wristband dosimeter that darkens irreversibly upon H₂S exposure (CuSO₄ + H₂S → CuS + H₂SO₄), replacing toxic lead acetate chemistry. The 30 × 40 mm badge incorporates ArUco fiducial markers and twelve reference color patches for geometric and photometric normalization. A native Kotlin/OpenCV Android application performs perspective rectification, flat-field correction, ridge-regularized color correction, and CIELAB lightness analysis (−dL*) to convert the color change into cumulative exposure (ppm·hr), shift TWA, and a safety verdict against ACGIH/OSHA/NIOSH limits. Exposure records synchronize to a backend HSE dashboard for digital traceability. Preliminary experiments confirm visible color response under both liquid sulfide and gaseous H₂S exposure. Generation of the gas-phase color-response trajectory and validated quantitative calibration are the planned next steps.

---

## PPT SLIDES (Copy-Ready)

### Slide 1: The Problem
- H₂S is acutely toxic — ACGIH TLV-TWA is 1 ppm over 8 hours
- Refinery sour-service areas require intrinsically safe operation; active electronic dosimeters face significant certification barriers
- Existing passive badges rely on **subjective visual color comparison** by operators
- No digital record, no traceability, no reproducibility

### Slide 2: Our Solution — The Passive Dosimeter Wristband
- **Zero-electronics wearable** — passive form factor, intrinsically safe
- Sensing strip: CuSO₄·5H₂O on Whatman Grade 1 paper under ePTFE membrane
- Reaction: `CuSO₄ + H₂S → CuS(s) + H₂SO₄`
- CuS darkens irreversibly in proportion to **cumulative H₂S dose**
- Replaces toxic lead acetate — no heavy metal disposal
- System measures cumulative exposure (ppm·hr), not instantaneous concentration

### Slide 3: Badge V2 Design
- **30 × 40 mm** portrait badge with **10 × 20 mm** rectangular sensing region
- **Four 8 mm ArUco fiducials** (DICT_4X4_50) at corners → perspective correction from any scan angle
- **Twelve 4 × 4 mm reference patches** in cross layout → normalize for camera variation and industrial lighting (sodium lamps, LED flash, daylight)
- Two substrate patches matching the unexposed pad tone → on-badge zero-dose baseline

### Slide 4: The Smartphone Pipeline
- Native **Kotlin + OpenCV 5.0** Android app — runs entirely on-device
- **Four-stage deterministic pipeline:**
  1. **Rectify** — ArUco detection with sub-pixel refinement + homography → flat canonical image
  2. **Sample** — ROI extraction in linear light with luminance-based trim-mean outlier rejection
  3. **Normalize** — Flat-field spatial correction + ridge-regularized Color Correction Matrix from 12 on-badge patches (root6 → affine → linear → von Kries fallback)
  4. **Assess** — CIELAB −dL* (lightness drop) → calibration model → ppm·hr, TWA, verdict
- **Chemical integrity check:** Rejects badges with chroma trajectory inconsistent with CuS chemistry
- Result: **Quantitative, reproducible, digitally logged** — replaces subjective human interpretation

### Slide 5: Calibration & Validation Status
| What | Status |
|---|---|
| CuSO₄ darkening under liquid Na₂S (chemistry proof-of-concept) | ✅ Demonstrated |
| Visible color response under gaseous H₂S exposure | ✅ Demonstrated (preliminary) |
| Full Android CV pipeline (detect → sample → normalize → assess) | ✅ Implemented & tested with reference images |
| Backend API + database + HSE dashboard | ✅ Implemented & demonstrated with synthetic data |
| H₂S-specific color-response trajectory (gas-phase reference ladder) | 🔬 To be generated from controlled gas exposure |
| Quantitative calibration (−dL* → ppm·hr) against certified H₂S | 🔬 To be validated |
| Temperature/humidity correction characterization | 🔬 To be characterized during calibration |

### Slide 6: Backend & HSE Dashboard Architecture
```
Worker wears passive wristband during shift
        ↓
Post-shift: scan with Android app (on-device CV pipeline)
        ↓
Measurement record: worker ID, badge serial, timestamp,
GPS coordinates, dose (ppm·hr), TWA, verdict, quality audit trail
        ↓
Backend API → Database (SQLite pilot / PostgreSQL+PostGIS production)
        ↓
HSE Dashboard: per-worker rollup, per-unit exposure,
spatial risk-map, trend analysis, immutable audit trail
```

**Environmental Factors:**
Temperature and humidity influence the CuSO₄/H₂S reaction kinetics. The software architecture includes parameterized fields for correction factors. Temperature dependence will be characterized during controlled calibration, with data collected across the intended operating range.

### Slide 7: Summary & Next Steps
- **Demonstrated:** CuSO₄ chemistry proof + preliminary H₂S gas response + full CV pipeline + backend architecture
- **Built:** Complete Android scanning app with quantitative dose estimation architecture
- **Next:** Generate H₂S-specific color-response curve from controlled gaseous exposure → calibrate software → characterize temperature dependence
- **Value:** Low-cost, passive, portable, intrinsically safe, digitally traceable H₂S dose monitoring

---

## KEYWORDS

1. Hydrogen Sulfide (H₂S) Dosimetry
2. Passive Colorimetric Dosimeter
3. Copper(II) Sulphate (CuSO₄) Sensing
4. Wearable Industrial Safety
5. ArUco Marker Detection
6. Color Correction Matrix (CCM)
7. CIELAB Lightness Analysis (−dL*)
8. OpenCV Android Application
9. Perspective Rectification
10. Cumulative Exposure Monitoring
11. HSE Digital Traceability
12. Occupational Exposure Limits (ACGIH TWA)
