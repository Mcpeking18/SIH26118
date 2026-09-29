# Project Summary: SIH26118 H₂S Dosimeter Wristband

## 1. Project Overview & Architecture
The project is a passive colorimetric H₂S exposure-dosimeter wristband for MRPL (Mangalore Refinery and Petrochemicals Limited). It addresses the need for worker safety in ATEX/PESO Zone 0 environments where electronic devices are strictly regulated or forbidden. 

- **The Wearable:** A passive wristband containing no electronics. It uses a CuSO4·5H2O (Copper II Sulfate) sensing strip on Whatman paper beneath an ePTFE membrane. The chemical reacts to Hydrogen Sulfide (H₂S) gas by darkening.
- **The Concept:** Workers wear the wristband during their shift. Afterwards, they scan it with a smartphone app which processes the color change to compute H₂S exposure (ppm·hr and TWA in ppm) and checks it against ACGIH limits.
- **Color Metric:** The system primarily uses `-dL*` (change in lightness) rather than `dE00` (which is prone to chroma noise), as the chemical reaction is a pure darkening process.

### Directory Structure
- **`reference/python/`**: The Golden Reference. Contains the mathematically correct Python/OpenCV pipeline and tests.
- **`android/`**: The target native Android app (Kotlin + OpenCV) being built to run the pipeline locally.
- **`backend/`**: A reference FastAPI service with a scanning PWA and an HSE risk map dashboard.
- **`experimental/`**: Zone for true H₂S calibration data and curve-fitting scripts.
- **`cpp_legacy/`**: Abandoned C++ port (kept for historical reference).

---

## 2. Python to Kotlin Port (Phase 2)
The project is currently in **Phase 2**, migrating the image processing engine from the Golden Python Reference to a Kotlin Android App using the OpenCV Android SDK.

**Migration Progress:**
1. **Module 1 (Geometry):** `badge_spec.py` ported to `WristbandSpec.kt`.
2. **Module 2 (Detection & Rectification):** `detect.py` ported to `Detector.kt`.
3. **Module 3 & 4 (Colorimetry & Normalization):** `Colorimetry.kt` and `Normalizer.kt` have been implemented.
4. **Module 5 (Dosimetry):** `Dosimetry.kt` and `CalibrationModel.kt` have been implemented.

**Migration Principles:**
- Migrate module-by-module.
- Python remains the **Golden Reference**. Its outputs must perfectly match the Kotlin outputs (within a specified tolerance) before moving on.
- Architecture layers (geometry, CV, color math, calibration) must remain strictly decoupled.

---

## 3. UI Branches: `debug-camera` vs `Vanshika_test`
Two distinct UI efforts have been explored on different branches:

### `debug-camera` Branch
This branch focused on establishing a direct pipeline connection to the device's camera for testing the CV engine.
- Implemented a `DebugCameraActivity.kt` to capture live camera frames.
- Mapped the "Scan Wristband" button on the main screen to launch this debug camera view.
- Focused on functional integration of the Kotlin OpenCV backend with the camera hardware.

### `Vanshika_test` Branch
This branch focused on building a polished, feature-rich front-end demo for the Android App.
- Created a massive set of UI components, fragments, and activities under the `ui` package (e.g., `ScannerActivity`, `SignInActivity`, `DevicePairingFragment`, `RefineryMapFragment`, `ExposureHistoryFragment`).
- Added extensive custom styling, drawables, and layouts (e.g., `bg_badge_blue.xml`, `ic_shield_h2s.xml`, alert cards) to make the app look like a premium enterprise product.
- Implemented a bottom navigation flow and a mock dashboard, serving as the visual blueprint for the final product.

---

## 4. Current State: Things to Do vs. Do NOT Do

### ✅ To Do
- **Calibration:** Await true gaseous H₂S exposure calibration data from spectrophotometer chamber tests.
- **Update Coefficients:** Once lab data arrives, update the calibration polynomial coefficients in the configuration profile (without rewriting CV code).
- **Finalize Geometry:** Wait for the physical wristbands to be finalized to lock in dimensions.
- **Continue Kotlin Migration:** Verify OpenCV ArUco detector on a physical device.

### 🚫 Do NOT Do
- **Do NOT** redesign the architecture or revert to C++.
- **Do NOT** delete or modify the Python reference engine.
- **Do NOT** migrate the entire engine to Kotlin at once (avoid a monolithic `BadgeEngine.kt`).
- **Do NOT** treat liquid Na₂S testing as valid calibration for gaseous H₂S.
- **Do NOT** invent H₂S calibration coefficients or wristband dimensions.

---

## 5. Future Plans
- **Containerization:** You plan to containerize the application environment (likely Dockerizing the Python backend, backend dependencies, and testing tools) to make it easy for your friends/teammates to spin up the project on their local machines without fighting dependency hell.
- **Field Use:** Full integration of the true H₂S calibration curve into the Kotlin app for real-world deployment in the refinery.
