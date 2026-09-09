# Project Context: SIH26118 H2S Dosimeter Wristband

## Current Architecture & Reference
- **Python Engine:** The current engine/ directory remains the intact mathematical and image-processing reference implementation.
- **Legacy C++:** The cpp/ directory is EXPERIMENTAL/LEGACY and will eventually be abandoned in favor of Kotlin, but it remains in the repo for now.
- **Physical Concept:** A wearable dosimeter *wristband* (not a rigid badge). Uses a CuSO4·5H2O sensing strip on Whatman paper under an ePTFE membrane.
- **Fiducials & References:** ArUco markers are strictly for geometric alignment and perspective correction. Reference color patches are strictly for normalizing camera/lighting differences. They do *not* provide H2S calibration.

## Chemistry & Calibration Status (Important Limitations)
- **Calibration is Pending:** True gaseous H2S exposure calibration curves are pending future spectrophotometric chamber tests.
- **No Final Metric:** The final dose metric (e.g., -dL*, ?E, or a multi-feature model) is NOT yet experimentally established. The architecture must allow the calibration model to be entirely replaceable.
- **Liquid Testing is NOT Calibration:** Preliminary tests using liquid Na2S proved progressive color change but CANNOT be used to generate H2S calibration coefficients.
- **Synthetic Placeholders:** Current calibrations (SYNTHETIC_CALIBRATION) are placeholders for software testing only.

## What Remains Incomplete
- Real gaseous H2S calibration data.
- Final color-to-dose metric determination.
- Final wristband geometry dimensions (current values in code are provisional/legacy).
- The entire Kotlin/Android implementation.

## Next Steps
- Revise the architectural restructuring plan.
- Await approval before performing ANY cleanup, deletion, or conversion.
- Do NOT start Kotlin development yet.
