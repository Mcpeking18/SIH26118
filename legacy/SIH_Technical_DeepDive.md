# SIH26118 — Technical Deep-Dive (Final Corrected Version)

> All corrections from both approval passes applied.
> Use this to write the abstract's technical sections and PPT slides.

---

## 1. BADGE V2 — PHYSICAL DESIGN

### 1.1 Form Factor & Dimensions

The dosimeter badge is a **30 mm wide × 40 mm tall** (portrait orientation) flat substrate designed to be mounted on the head of a 22 mm wristband strap. The portrait aspect ratio accommodates a tall rectangular sensing region while keeping the badge narrow enough for a wrist-mounted form factor.

### 1.2 Sensing Region

The central sensing region is a **10 × 20 mm rectangle**, centered at position (15, 20) mm on the badge. This region contains the CuSO₄·5H₂O-impregnated Whatman Grade 1 paper strip, covered by an ePTFE gas-permeable membrane.

**Why rectangular, not circular:** A rectangular sensing strip provides a larger reactive area (200 mm²) compared to a circular pad of comparable width (a 10 mm diameter circle = ~78.5 mm²). The larger area serves two purposes:
- More CuS product accumulates per unit of exposure, increasing the measurable lightness change (−dL*) and improving signal-to-noise ratio at low doses.
- The image-processing pipeline can sample more pixels from the sensing region, reducing the statistical uncertainty of the mean color measurement.

**The ePTFE membrane** serves a dual role:
- It is gas-permeable (allows H₂S diffusion to the sensing strip) while being liquid-impermeable (protects the strip from rain, sweat, and accidental splashes).
- It acts as a diffusion barrier that regulates the rate at which H₂S reaches the CuSO₄ substrate, which is essential for the badge to function as a cumulative dose integrator rather than a threshold detector.

### 1.3 ArUco Fiducial Markers

Four **8 × 8 mm** ArUco fiducial markers from the **DICT_4X4_50** dictionary are placed at the four corners of the badge.

| Marker | ID | Center Position |
|---|---|---|
| Top-Left | 0 | (5, 5) mm |
| Top-Right | 1 | (25, 5) mm |
| Bottom-Right | 2 | (25, 35) mm |
| Bottom-Left | 3 | (5, 35) mm |

**Why ArUco markers:**
- ArUco markers are binary fiducial markers specifically designed for robust detection under partial occlusion, variable lighting, and perspective distortion — conditions expected in industrial field environments.
- Each marker encodes a unique ID, allowing the software to identify which corner is which even if only 2 of 4 markers are detected. This is critical because fingers, wristband straps, or dirt may occlude one or two corners during scanning.
- The 4×4 bit pattern (DICT_4X4_50) provides the smallest marker grid that still allows reliable error correction, maximizing the physical area devoted to the black-white pattern within the 8 mm marker space.

**Why 8 mm:** At typical smartphone scanning distances (15–30 cm), an 8 mm marker spans approximately 40–80 pixels on the sensor. This is well above the minimum (~20 px) required for reliable detection and sub-pixel corner refinement, providing margin for motion blur and poor focus.

**Why corner placement:** Placing the markers at the four extremes of the badge maximizes the baseline for the homography computation. A wider baseline produces a more numerically stable perspective transform, meaning the rectified image has lower geometric distortion — which directly affects how accurately the software can locate and sample the sensing region and reference patches.

### 1.4 Reference Color Patches

Twelve **4 × 4 mm** reference color patches are arranged in a **cross/plus layout** around the central sensing region:

| Arm | Patches | Direction |
|---|---|---|
| Top | P1, P2 | Horizontal, above sensing region |
| Right | P3, P4, P5, P6 | Vertical column, right of sensing region |
| Bottom | P7, P8 | Horizontal, below sensing region |
| Left | P9, P10, P11, P12 | Vertical column, left of sensing region |

**The 12 patches include three functional categories:**

| Category | Patches | Purpose |
|---|---|---|
| **Neutrals** (4) | White, Grey-50, Grey-20, Black | Span the lightness axis from L*≈96 to L*≈14. These anchor the lightness response of the color correction — the axis that carries the dose signal. |
| **Chromatic** (6) | Cyan, Magenta, Yellow, Red, Green, Blue | Cover all four quadrants of the a*b* chroma plane. These constrain the CCM's off-diagonal terms (cross-talk correction). |
| **Substrate** (2) | Substrate_A, Substrate_B | sRGB matches the unexposed CuSO₄ pad tone. These provide a **zero-dose baseline** without needing a separate unexposed badge — the on-badge baseline tracks the same print lot and aging as the rest of the badge. |

**Why a cross/plus layout instead of a ring:**
The cross layout distributes patches across all four spatial quadrants of the badge. This is advantageous for the flat-field spatial illumination model: patches at different (x, y) positions on the badge allow the software to detect and correct illumination gradients (e.g., a light source brighter on the left than the right, or the phone body shadowing the top). A ring layout at constant radius from the center would be blind to radial illumination falloff (lens vignetting), since `x² + y²` is constant on a circle.

**Why 12 patches:**
- The highest-accuracy Color Correction Matrix (root6 mode) uses 6 features per patch. With 12 patches, this gives a 2:1 ratio of observations to parameters — enough for a well-conditioned regression while still leaving room for leave-one-out cross-validation (where each patch is held out in turn to honestly estimate prediction error).
- The fallback ladder (affine: 4 features, linear: 3 features, von Kries: 1 neutral) means that even if patches are occluded or clipped, the system gracefully degrades rather than failing entirely.

---

## 2. DIGITAL PIPELINE — THE ANDROID CV ENGINE

The Android application (native Kotlin + OpenCV 5.0.0+) runs a **four-stage deterministic pipeline** entirely on-device. No internet connection is required for the scan. The pipeline's design rule is: **fail loudly, never guess.** A safety instrument that returns a plausible-looking number from a bad photograph is worse than one that says "retake."

### 2.1 Stage 1 — Detection & Rectification

**Input:** Raw camera frame (8-bit BGR, typically 12 MP from a smartphone camera).

**Step 1a — Downscaling:**
The frame is downscaled so its longest edge does not exceed 2000 px, using `INTER_AREA` interpolation. This is not an arbitrary choice: `INTER_AREA` is a proper box filter — it averages the pixels being merged, which is the photometrically correct operation when reducing resolution. Nearest-neighbor or bilinear resampling would alias the printed patch edges into the patch interiors and shift the sampled colors. ArUco detection accuracy does not improve past the point where an 8 mm marker spans ~60 px, so downscaling saves processing time without sacrificing geometric precision.

**Step 1b — ArUco Detection:**
The OpenCV `ArucoDetector` (class-based API, OpenCV 5.0+) locates the four corner markers. Detection parameters are tuned for printed markers on paper/plastic substrates:
- **Sub-pixel corner refinement** (`CORNER_REFINE_SUBPIX`) with a 5×5 window and 50 iterations at 0.01 accuracy — this recovers the exact corner positions to sub-pixel precision, which is essential for accurate homography computation.
- Adaptive threshold window sizes from 3 to 43 px with step 4 — this handles the wide range of marker sizes that occur across scanning distances.
- Minimum marker perimeter rate of 0.01 — allows detection of markers that occupy as little as 1% of the frame perimeter, enabling scanning from further distances.

**Step 1c — Homography & Warp:**
The detected corner positions (in pixels) are matched against the known millimeter coordinates from the BadgeV2Spec. A homography matrix is computed via `findHomography`, and the image is warped to a canonical fronto-parallel plane using `warpPerspective`. This transforms an arbitrary hand-held photograph taken at any angle into a standardized flat image where every downstream ROI is at a fixed, known pixel location.

**Quality gate:** The reprojection RMSE (root-mean-square error between detected corners and their expected positions after applying the homography) must be below 0.35 mm. If it exceeds this, the geometric model is unreliable and the scan is rejected with an operator instruction to hold the badge flat and square to the camera.

**Minimum markers:** The pipeline requires at least 2 of 4 markers to be detected. Two markers are sufficient to constrain a homography when combined with the known badge geometry (the remaining two corner positions can be inferred). This tolerance allows scanning when fingers or the wristband strap occlude corners.

### 2.2 Stage 2 — ROI Sampling

**Input:** The rectified (warped) canonical image of the badge.

**Step 2a — Region Extraction:**
ROIs for each of the 12 reference patches and the central sensing region are extracted using the pixel coordinates computed from the BadgeV2Spec geometry (millimeters × pixels-per-mm).

**Step 2b — Linear-Light Conversion:**
All pixel values are converted from gamma-encoded sRGB to linear light **before** averaging. This is a correctness requirement, not an optimization. The sRGB encoding is a ~1/2.4 power law, so the arithmetic mean of encoded values is *not* the encoding of the mean radiance. Averaging encoded pixels over a sensing strip that carries any shading gradient biases the result brighter — which reads as a lower dose (the dangerous direction for a safety instrument).

**Step 2c — Trim Mean:**
A **20% trim mean** is applied to reject outlier pixels. Critically, the trim is decided once from **luminance** (Rec. 709 weights: 0.2126R + 0.7152G + 0.0722B), not per-channel. Rejecting the top/bottom percentiles of each channel independently would pull R, G, and B from different pixel populations and shift the sampled chromaticity. The luminance-based trim identifies a single set of surviving pixels, and that pixel set is averaged across all three channels, preserving the color relationship.

**Quality gates:**
- **Clip fraction:** If more than 15% of pixels in the sensing region are at or near the 8-bit ceiling (255), the region is saturated (specular glare) and the scan is rejected.
- **Black fraction:** Similar check for crushed shadows.
- **Coefficient of variation:** If spatial variation within the sensing region exceeds 25%, the sensing strip may be damaged or the rectification is incorrect.

### 2.3 Stage 3 — Illumination & Color Normalization

This is the stage that makes the entire concept work. A passive colorimetric badge is only as good as the reader's ability to separate **chemistry** (the pad darkening) from **optics** (illuminant color, camera white balance, exposure, sensor cross-talk). The 12 printed reference patches — photographed in the same frame, under the same light, by the same camera — provide the known-color targets that turn this separation into a tractable regression problem.

**Two independent corrections are applied, fixing genuinely different errors:**

#### 2.3.1 Flat-Field Correction (Spatial)

Illumination is never uniform across a 30 × 40 mm badge surface. Sources of non-uniformity include:
- An oblique lamp or the sun at an angle
- The operator's own shadow falling partially across the badge
- The phone body blocking overhead light
- The camera lens's own optical vignetting (radial brightness falloff)

The reference patches sit at various positions around the badge while the sensing strip sits at the center. Any brightness variation makes them disagree about how bright the light is, and a Color Correction Matrix (which applies one global correction) cannot fix this.

The flat-field model is fitted from white-field probe points and patch positions. A quadratic spatial illumination model (linear ramp + radial term) captures both directional gradients and vignetting. The radial term is identifiable because the cross layout places patches at multiple distances from the center, unlike a ring layout where all patches sit at the same radius.

Measured impact (in simulation): a 25% illumination ramp across the frame inflated the dose reading by 21%, and lens vignetting alone walked it from +5.8% to −9.7%. Flat-field correction eliminates this.

#### 2.3.2 Color Correction Matrix (Colorimetric)

After flat-fielding ensures all patches see consistent brightness, a Color Correction Matrix (CCM) corrects for illuminant color, camera white balance, and sensor channel cross-talk.

**The CCM is a ridge-regularized regression** mapping the camera's observed RGB values to the known standard sRGB values of the 12 patches. Ridge regularization (L2 penalty) prevents overfitting when the condition number is high (e.g., under near-monochromatic sodium lighting where different colors become hard to distinguish).

**Fallback ladder** (most to least capable):

| Mode | Features | Min. Patches Required | Capability |
|---|---|---|---|
| root6 | 6 (R, G, B, √RG, √RB, √GB) | 6 | Exposure-invariant, best accuracy. Cross-terms capture sensor channel coupling. |
| affine | 4 (R, G, B, 1) | 4 | Handles veiling glare / black-level offset. |
| linear | 3 (R, G, B) | 3 | Classic 3×3 color matrix. |
| von Kries | grey balance from ≥1 neutral | 1 | Diagonal scaling only — corrects color cast but not cross-talk. Last resort. |

If patches are occluded or clipped (specular highlights), they are excluded from the fit. The system steps down the fallback ladder as needed.

**Quality gating — Leave-One-Out (LOO) residual:**
Quality is assessed using a leave-one-out cross-validation residual, *not* a training residual. The CCM is refit 12 times, each time holding out one patch and predicting it. This honestly estimates how well the pad — a color the model never saw — will be corrected.

The residual is **locus-weighted**: patches near the pad's own color path (near-neutral, warm tones) contribute more to the quality score than distant chromatic patches. A perfect correction of saturated blue is irrelevant if the near-neutral tones the pad lives in are poorly corrected.

**Narrowband / sodium lamp detection:**
Low-pressure sodium lamps are nearly monochromatic (~589 nm). Under such illumination, a camera sees no color differences between patches — the CCM becomes unsolvable. The pipeline detects this via a channel-balance metric (ratio of the weakest to strongest channel across the neutral patches). If the illumination lacks sufficient spectral bandwidth, the scan is rejected with an explicit operator instruction to use supplemental white-light illumination.

### 2.4 Stage 4 — Dosimetry Assessment

#### 2.4.1 The Primary Observable: −dL*

The corrected sensing pad and baseline (from the on-badge substrate patches) are converted to CIELAB (L*a*b*) color space under D65 illuminant.

The primary dose observable is **−dL*** — the drop in lightness (L*) from the unexposed baseline to the exposed pad.

**Why −dL* instead of CIEDE2000 (dE00):**

The CuSO₄ → CuS reaction path is overwhelmingly a darkening process. The direction vector from the unexposed pad to the fully reacted pad in L*a*b* space is approximately `[−0.996, +0.071, +0.050]` — meaning **99.6% of the color change is in the lightness axis**.

CIEDE2000 divides chroma and hue differences by weighting functions (S_C, S_H) that shrink toward 1 as chroma approaches zero, while the lightness weighting (S_L) stays near 1. Near the neutral axis — where the CuSO₄ pad lives — dE00 amplifies chroma error relative to lightness error. This is exactly where a phone camera's residual error lives after white balancing.

Evaluated over 40 camera × illuminant combinations in a **synthetic simulation study** (not a field trial with physical badges):

| Observable | RMS Error | Worst Case |
|---|---|---|
| dE00 | 11.6% | 40.4% |
| Locus projection | 6.8% | 20.2% |
| **−dL* alone** | **4.9%** | **14.8%** |

These figures demonstrate the relative advantage of −dL* over alternative observables within the simulation framework. They should not be interpreted as validated field accuracy. dE00 is still computed and stored on every scan for reference, but it does not drive the dose number.

#### 2.4.2 Chemical Locus Integrity Check

The chroma information (a*, b*) that was deliberately excluded from the dose calculation is repurposed as a **chemical integrity check**.

The CuSO₄ → CuS reaction follows a specific curved path through L*a*b* space. Unlike lead acetate (which darkens nearly in a straight line), the CuS path involves three optical species — pale cyan CuSO₄ being consumed, white substrate being revealed, and brown-black CuS accumulating — so the pad swings through khaki and bronze before collapsing to near-black.

Five L*a*b* anchor points currently define this arc. **These anchors are an engineering prototype derived from the CuSO₄ reagent specification and liquid Na₂S proxy experiments. Preliminary gaseous H₂S exposure has shown that the actual gas-phase color trajectory does not precisely match these values. The anchor table will be regenerated from controlled gaseous H₂S exposure data during the calibration campaign.**

| Stage | L* | a* | b* | Visual Description |
|---|---|---|---|---|
| Unexposed | 91.2 | −3.8 | −1.5 | Pale ice blue |
| Trace | 74.2 | −4.2 | +12.2 | Muted olive / khaki |
| Mid-dose | 40.2 | +9.4 | +27.3 | Medium bronze / amber |
| High dose | 16.0 | +8.1 | +13.4 | Deep chocolate / umber |
| Saturated | 13.0 | +1.8 | +2.4 | Near-black |

At each measured lightness, the software interpolates along these anchors to determine the **expected** chroma (a*, b*). The distance between the measured chroma and the expected chroma is the **chroma residual**.

**Dose-dependent tolerance:** The allowed chroma residual scales with the magnitude of darkening. This is not a constant because:
- A contaminated pad's chroma displacement grows in proportion to how much it has darkened (proportional to the angular deviation × the path length traveled).
- The camera's residual chroma error after CCM correction is roughly constant with dose.
- A single threshold cannot work: set it to pass high-dose pads and it misses everything at low dose; set it to catch low-dose contamination and it fails half the legitimate high-dose scans.

**What this catches:** Reagent oxidation before use, mould, rust, blood, a badge from a different lot, a photograph of someone else's badge, or a counterfeit lead acetate badge. None of these perturb −dL* enough to notice, which is why this check is needed alongside it. A badge failing this check is flagged as **SUSPECT** and no dose number is issued.

#### 2.4.3 Dose Calculation

The −dL* value is passed into a **polynomial calibration model** that maps the observable to cumulative dose in ppm·hr. A second model form (Hill-type saturation curve) is available for the near-saturation regime where the polynomial may extrapolate poorly.

From the dose and the shift duration (default 8 hours), the **Time-Weighted Average (TWA)** is computed: `TWA = dose / shift_hours`.

The TWA is compared against occupational exposure limits:

| Standard | 8-hr TWA Limit |
|---|---|
| ACGIH TLV | 1 ppm |
| OSHA PEL | 10 ppm (ceiling) |
| NIOSH REL | 10 ppm (ceiling) |

A verdict is assigned: **SAFE**, **ACTION**, **WARNING**, or **CRITICAL**.

**STEL limitation (stated honestly):** A passive cumulative dosimeter integrates concentration over time. From a single end-of-shift scan, you can recover dose and TWA, but you **cannot** recover STEL — infinitely many concentration histories share the same integral (a steady 2 ppm for 8 hours and a 160 ppm spike for 6 minutes produce the same 16 ppm·hr). The system explicitly marks `stelDeterminable = false` for single scans. However, if multiple scans are performed through a shift (entry, mid-shift kiosk check, exit), the differences between consecutive readings yield interval-mean concentrations that can **bound** the short-term exposure.

---

## 3. CALIBRATION

### 3.1 Architecture

The calibration is **completely decoupled** from the image-processing pipeline. The `CalibrationModel` is a data object containing:
- The polynomial (or saturation-curve) coefficients
- The observable name (which measurement to use — currently `delta_l`)
- Observable range limits
- A noise floor below which readings are treated as zero
- Architecture fields for temperature and humidity correction factors (placeholder parameters; not yet experimentally characterized)
- Fit quality metadata (R², relative error, number of calibration points)

When validated calibration data becomes available, **only this data object changes**. No computer vision code, no color math code, no pipeline logic needs to be rewritten.

### 3.2 Current Calibration Status

The current calibration coefficients are **synthetic software-development placeholders**, explicitly labeled as such in the code:

```
notes = "derived from ReactionModel(d_char=55.0) over 0-200 ppm*hr 
         in delta_l; synthetic, replace with chamber data"
```

These coefficients were generated from a forward physics model for the purpose of testing the pipeline architecture end-to-end — verifying that data flows correctly from image → −dL* → dose → verdict. They do **not** represent validated H₂S response data.

### 3.3 Three Distinct Steps to Validated Calibration

It is important to distinguish between three separate activities that are sometimes conflated:

| Step | What It Establishes | Status |
|---|---|---|
| **Chemistry proof** | That CuSO₄ reacts with sulfide to form CuS and produce a visible color change | ✅ Demonstrated (Na₂S liquid + preliminary H₂S gas) |
| **Color reference generation** | The actual L*a*b* color path of the sensing strip under controlled gaseous H₂S exposure at known doses | 🔬 Pending — preliminary gas experiment showed the response does not precisely match the Na₂S-derived reference, indicating this must be regenerated from gaseous data |
| **Quantitative calibration** | A validated mathematical mapping from −dL* to ppm·hr, fitted against certified H₂S reference concentrations with known accuracy bounds | 🔬 Pending — requires controlled exposure chamber with a certified reference gas monitor |

### 3.4 Why Na₂S Liquid and H₂S Gas Responses Differ

Both experiments produce the same target product (CuS), but under fundamentally different mass-transfer and reaction conditions:

- **Liquid Na₂S:** Dissolved sulfide ions (S²⁻/HS⁻) contact the entire paper surface simultaneously and uniformly. Reaction is essentially instantaneous ionic precipitation.
- **Gaseous H₂S:** The gas must diffuse through the ePTFE membrane and into the pore structure of the paper. The reaction front progresses into the paper depth over time. Rate is limited by gas-phase diffusion, membrane permeability, and humidity (H₂S must dissolve into a thin water film on the CuSO₄ crystals to react).

The result is that CuS forms with a different **depth distribution** within the paper substrate — uniform in the liquid case, surface-concentrated in the gas case. Since the paper is translucent and the observer views reflected light, the same total mass of CuS can produce different apparent colors depending on where it sits within the paper thickness.

This is why the Na₂S color response **cannot** define the H₂S calibration curve, and why the existing reference color ladder must be regenerated from gaseous exposure data.

### 3.5 Color Reference Status and Next Step

The current reference color ladder (the five L*a*b* anchor points defining the CuSO₄ → CuS reaction path, and the printed substrate patch sRGB values) is an **engineering prototype**. It was derived from:
- The CuSO₄ reagent specification (unexposed and fully-reacted endpoint tones)
- Liquid Na₂S proxy experiments (intermediate stages)
- Interpolation based on the known three-species optical model (CuSO₄ consumed, substrate revealed, CuS accumulated)

**Preliminary gaseous H₂S exposure** has demonstrated that the CuSO₄ strip does respond to H₂S gas with a visible color change. However, the observed color did not precisely match the existing Na₂S-derived reference ladder. This is expected — liquid and gaseous exposure produce CuS with different spatial distributions within the paper substrate (see Section 3.4), leading to different apparent reflectance even at the same total CuS mass.

**Next step:** Controlled gaseous H₂S experiments at known concentration × time products will be used to:
1. Establish the actual CuSO₄ → CuS color-response trajectory under gaseous exposure conditions.
2. Regenerate the L*a*b* anchor table from experimentally measured gas-exposed strips.
3. Select the final reference patch set to span the experimentally observed trajectory.
4. Fit the quantitative calibration polynomial from the resulting −dL* vs. ppm·hr data.

The software architecture fully supports this: the anchor table, substrate patch values, and calibration coefficients are all configuration data that can be replaced without modifying any pipeline code.

### 3.6 Temperature and Humidity Dependence

The CuSO₄/H₂S reaction kinetics are influenced by temperature and humidity. The software calibration model includes **parameterized fields** for temperature and humidity correction factors, so a correction function can be incorporated without modifying the pipeline code. However:

- **No dedicated temperature sensor** is currently integrated into the wristband or the Android application.
- The temperature and humidity correction parameters currently present in the codebase are **architecture placeholders**, not experimentally validated coefficients.
- Temperature and humidity dependence will be characterized during the controlled calibration campaign, with calibration data collected across the intended operating temperature range (anticipated 25–50°C for refinery environments). The resulting correction model will be fitted from that data and loaded into the calibration layer.

---

## 4. PROPOSED DEPLOYMENT ARCHITECTURE — Backend & HSE Dashboard

The dosimetry system extends beyond the Android scanning application into a backend data layer and HSE (Health, Safety & Environment) dashboard, enabling centralized digital traceability of worker exposure records.

### 4.1 Architecture Overview

```
┌─────────────────────┐
│  Android App        │
│  (Kotlin + OpenCV)  │
│  On-device scan     │
│  & dose computation │
└────────┬────────────┘
         │ measurement record (JSON)
         ▼
┌─────────────────────┐
│  Backend API        │
│  (FastAPI / stdlib) │
│  POST /scan         │
│  GET /scans         │
│  GET /workers       │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Database           │
│  SQLite (pilot) or  │
│  PostgreSQL+PostGIS │
│  (production)       │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  HSE Dashboard      │
│  (Web-based)        │
│  Risk map, worker   │
│  history, trends    │
└─────────────────────┘
```

### 4.2 Current Implementation Status

| Component | Status | Implementation |
|---|---|---|
| Backend API | **Implemented** | FastAPI application with `/scan` endpoint accepting multipart image uploads. Also serves via stdlib when FastAPI is unavailable. |
| Database schema | **Implemented** | SQLite schema for pilot use, plus a PostGIS schema designed for production deployment with spatial queries. |
| Scanning PWA | **Implemented** | Progressive Web App with camera capture, geolocation, and scan upload. Service worker for offline capability. |
| HSE Risk-Map Dashboard | **Implemented** | Single-page web dashboard with map visualization. |
| End-to-end data flow | **Demonstrated** | Tested with synthetic scan generation and upload. |
| Physical factory deployment | **Not deployed** | The backend has not been deployed in a live refinery environment. |

### 4.3 Measurement Record Contents

Each scan record stored in the database contains:

| Field | Description |
|---|---|
| `worker_id` | Worker identifier |
| `badge_serial` | Badge lot and serial tracking |
| `scanned_at` | Timestamp of the scan |
| `geom` + `accuracy_m` | GPS coordinates and accuracy (where available) |
| `unit_code` | Refinery plant unit (e.g., SRU, ARU, DCU) |
| `ok` / `verdict` / `band` | Scan validity, safety verdict, exposure band |
| `dose_ppm_hr` / `twa_ppm` | Computed exposure metrics |
| `delta_l_star` / `delta_e00` | Color observables |
| `chroma_residual` | Chemical integrity metric |
| `ccm_mode` / `reproj_rmse_mm` | Scan quality provenance |
| `warnings` | Machine-readable quality flags |
| `result_json` | Full pipeline output (audit trail) |

Failed scans are deliberately retained — an unreadable badge means the worker's shift went unmonitored, which is a finding in its own right.

### 4.4 Dashboard Capabilities

The HSE dashboard is designed to provide:
- **Per-worker rollup:** 24-hour scan count, peak TWA, mean TWA, cumulative dose, number of TLV exceedances
- **Per-unit rollup:** Exposure statistics per refinery plant unit (spatially joined)
- **Spatial clustering:** Automatic identification of geographic clusters of concerning readings, distinguishing single-worker findings from area-wide findings
- **Risk-map visualization:** Map overlay of refinery plant units color-coded by H₂S propensity and recent exposure data
- **Audit trail:** Immutable scan records with correction tracking (corrections are new rows referencing the original, never edits)

### 4.5 Important Qualification

The backend and dashboard components exist as implemented software. They have been demonstrated with synthetic scan data. **They have not been deployed in a live factory environment.** The architecture is designed for that transition — the SQLite pilot schema and the PostGIS production schema share the same shape, so migration requires no application-layer changes.
