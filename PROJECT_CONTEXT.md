# Project Context: SIH26118 H2S Dosimeter Wristband

## Current Architecture & Reference
- **Python Engine:** The current eference/python/ directory remains the intact mathematical and image-processing GOLDEN reference implementation.
- **Legacy C++:** The cpp_legacy/ directory is abandoned in favor of Kotlin, retained only as a historical reference.
- **Physical Concept:** A wearable dosimeter *wristband* (not a rigid badge). Uses a CuSO4.5H2O sensing strip on Whatman paper under an ePTFE membrane.
- **Fiducials & References:** ArUco markers are strictly for geometric alignment and perspective correction. Reference color patches are strictly for normalizing camera/lighting differences. They do *not* provide H2S calibration.

## Chemistry & Calibration Status (Important Limitations)
- **Calibration is Pending:** True gaseous H2S exposure calibration curves are pending future spectrophotometric chamber tests.
- **No Final Metric:** The final dose metric (e.g., -dL*, dE, or a multi-feature model) is NOT yet experimentally established. The architecture must allow the calibration model to be entirely replaceable.
- **Liquid Testing is NOT Calibration:** Preliminary tests using liquid Na2S proved progressive color change but CANNOT be used to generate H2S calibration coefficients.
- **Synthetic Placeholders:** Current calibrations (SYNTHETIC_CALIBRATION) are placeholders for software testing only.

## Phase 1 Status
- **Phase 1 COMPLETE.**
- Android project foundation successfully scaffolded, synced, and built on a physical device.
- Kotlin + OpenCV SDK architecture successfully linked and compiling.
- Full engine migration has NOT happened yet. The migration boundary is mapped in ndroid/MIGRATION_MAP.md.

## What Remains Incomplete (Phase 2+)
- Full implementation of the Kotlin/OpenCV pipeline inside the Android app.
- Real gaseous H2S calibration data integration.
- Final wristband geometry dimensions.
