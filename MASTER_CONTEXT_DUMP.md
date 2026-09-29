# MASTER CONTEXT DUMP 
**Date:** September 16, 2026
**Purpose:** Comprehensive context transfer to a new AI assistant instance.

---

# 🤖 INSTRUCTIONS FOR THE NEXT AI ASSISTANT

**Hello new AI instance! The user has migrated to a new account. To get up to speed immediately, please perform the following actions:**

1. **Scan all Git branches:** We have active work across `main`, `debug-camera`, `Vanshika_test`, and `real_building`. Check out the UI work in `Vanshika_test` and the camera integration in `debug-camera`.
2. **Go through the codebase thoroughly:** Start by reading `README.md`, `PROJECT_CONTEXT.md`, and `phase_2.md`. Understand the strict separation between the Python reference engine and the Kotlin Android app.
3. **Understand the SIH Problem Statement:** This project is for Smart India Hackathon (SIH26118) for MRPL (Mangalore Refinery and Petrochemicals Limited). The problem is measuring worker H₂S exposure in ATEX/PESO Zone 0 environments where electronic devices are forbidden.
4. **Understand Our Solution:** We are building a passive wristband with NO electronics, using a CuSO4·5H2O (Copper II Sulfate) sensing strip that darkens upon H₂S exposure. The "intelligence" is entirely in an Android app that scans the wristband after a shift, uses OpenCV to correct perspective and lighting, and computes the H₂S exposure using `-dL*` color changes.
5. **Acknowledge constraints:** DO NOT delete the Python reference. DO NOT migrate the entire Android CV engine at once. DO NOT treat liquid testing as real calibration. 
6. **Future tasks:** We will be containerizing the backend for the team, and awaiting spectrophotometer chamber data for true H₂S calibration.

---

## 1. Project Overview & Architecture (Detailed)
The project is a passive colorimetric H₂S exposure-dosimeter wristband.

- **The Wearable:** A passive wristband containing no electronics. It uses a CuSO4·5H2O (Copper II Sulfate) sensing strip on Whatman paper beneath an ePTFE membrane.
- **Color Metric:** The system primarily uses `-dL*` (change in lightness) rather than `dE00` (which is prone to chroma noise), as the chemical reaction is a pure darkening process.

### Directory Structure
- **`reference/python/`**: The Golden Reference. Contains the mathematically correct Python/OpenCV pipeline and tests.
- **`android/`**: The target native Android app (Kotlin + OpenCV).
- **`backend/`**: A reference FastAPI service with a scanning PWA and an HSE risk map dashboard.
- **`experimental/`**: Zone for true H₂S calibration data and curve-fitting scripts.
- **`cpp_legacy/`**: Abandoned C++ port (kept for historical reference).

---

## 2. Python to Kotlin Port (Phase 2)
The project is currently in **Phase 2**, migrating the image processing engine from the Golden Python Reference to a Kotlin Android App using the OpenCV Android SDK (version 5.0.0+).

**Migration Progress:**
1. **Module 1 (Geometry):** `badge_spec.py` ported to `WristbandSpec.kt`.
2. **Module 2 (Detection & Rectification):** `detect.py` ported to `Detector.kt`.
3. **Module 3 & 4 (Colorimetry & Normalization):** `Colorimetry.kt` and `Normalizer.kt` have been implemented.
4. **Module 5 (Dosimetry):** `Dosimetry.kt` and `CalibrationModel.kt` have been implemented.

---

## 3. UI Branches: `debug-camera` vs `Vanshika_test`
### `debug-camera` Branch
- Implemented a `DebugCameraActivity.kt` to capture live camera frames.
- Mapped the "Scan Wristband" button on the main screen to launch this debug camera view.

### `Vanshika_test` Branch
- Created a massive set of UI components, fragments, and activities under the `ui` package (e.g., `ScannerActivity`, `SignInActivity`, `DevicePairingFragment`, `RefineryMapFragment`, `ExposureHistoryFragment`).
- Added extensive custom styling, drawables, and layouts to make the app look like a premium enterprise product.

---

## 4. Current State: Things to Do vs. Do NOT Do
### ✅ To Do
- **Calibration:** Await true gaseous H₂S exposure calibration data from spectrophotometer chamber tests.
- **Finalize Geometry:** Wait for the physical wristbands to be finalized to lock in dimensions.

### 🚫 Do NOT Do
- **Do NOT** redesign the architecture or revert to C++.
- **Do NOT** delete or modify the Python reference engine.
- **Do NOT** treat liquid Na₂S testing as valid calibration for gaseous H₂S.

---

## 5. Future Plans
- **Containerization:** Dockerize the Python backend, dependencies, and testing tools for the team.
- **Field Use:** Full integration of the true H₂S calibration curve into the Kotlin app for real-world deployment.
