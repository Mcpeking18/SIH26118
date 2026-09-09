# SIH26118 - Passive Colorimetric H2S Exposure-Dosimeter Wristband

Smart India Hackathon 2026 - MRPL (Mangalore Refinery and Petrochemicals Limited)

A worker wears a wristband with no electronics in it. A CuSO4·5H2O (Copper II Sulfate) sensing strip on Whatman paper under an ePTFE membrane reacts with hydrogen sulphide that diffuses through it, darkening in proportion to accumulated dose. At the end of the shift, someone photographs the wristband with an ordinary phone, and this software turns that photograph into a number in ppm·hr, a time-weighted average in ppm, and a verdict against the ACGIH limits.

The wearable is passive because it has to be: MRPL's sour-service areas are ATEX/PESO Zone 0, where an intrinsically safe electronic dosimeter is expensive and a non-certified one is forbidden. Every gram of intelligence therefore lives on this side of the camera.

## Architecture

This repository contains the full ecosystem for the wristband, currently in transition from a Python prototype to a native Android application:

*   **`reference/python/`**: The golden mathematical reference implementation. Contains the OpenCV processing pipeline (`engine/`), synthetic generators (`sim/`), and end-to-end tests (`tests/`). This code remains the operational source of truth while the Android app is built.
*   **`experimental/`**: The decoupled calibration zone. True gaseous H2S exposure data (from spectrophotometer measurements) will live here alongside Python scripts to curve-fit that raw data into calibration coefficients.
*   **`android/`**: The future Kotlin + OpenCV native Android application. It will run the image pipeline locally on the phone, consuming calibration coefficients exported by the experimental layer.
*   **`backend/`**: A reference FastAPI service (`hse/`), scanning PWA (`webapp/`), and risk map (`dashboard/`). This acts as the cloud sync target for the Android app.
*   **`cpp_legacy/`**: An abandoned experimental C++ port of the engine.

## Chemistry and Calibration Status (Important Limitations)

**This project explicitly uses CuSO4, not Lead Acetate.** While lead acetate is a common colorimetric agent, it introduces heavy metal disposal issues and toxicity.

**Calibration is Pending:** 
Currently, the pipeline uses a synthetic placeholder calibration model for software testing. Preliminary lab tests using liquid Na2S proved the progressive color change of CuSO4, but **liquid testing is not gaseous H2S calibration.** 
Before field use, the calibration curve must be experimentally fitted against certified H2S atmospheres at known concentration-time products.

The architecture strictly decouples this: the Android/Python image-processing engines simply read a configuration profile containing the calibration polynomial coefficients. When the real lab data arrives, you only update the configuration file; no computer vision code needs to be rewritten.

## Why -dL* rather than dE00?

The obvious choice for "how much did this colour change" is CIEDE2000, but it can be the wrong choice for pure darkening reactions. The CuSO4 reaction locus moves almost purely along the lightness axis. `dE00` spends most of its sensitivity on chroma noise it should be ignoring.

Currently, the engine uses `-dL*` as the primary exposure predictor, while `dE00` and chroma paths are used as **integrity checks** to ensure the color trajectory actually matches CuSO4 and not a contaminant (or a lead acetate fake). **However, the final choice of metric (-dL*, dE, or a multi-feature model) will be decided by the final experimental data.**

## Quick start (Reference Backend)

Zero-install path - no FastAPI, no wheels, standard library only. 
Run this from the project root:

```bash
python3 -m backend.hse.serve_dev --port 8000 --seed-demo 80
```

Then open the scanner at <http://localhost:8000/> and the HSE dashboard at <http://localhost:8000/dashboard/>. `--seed-demo 80` writes 80 clearly-labelled synthetic scans so the map has something on it.

### Verifying the Reference Implementation

The Python reference includes an end-to-end smoke test that runs the backend and simulates HTTP multipart uploads of synthetically rendered wristbands. To run it:

```bash
# Set PYTHONPATH to include both the reference engine and the backend
export PYTHONPATH="$PWD/reference/python:$PWD/backend"

# Run the test
python3 -m reference.python.tests.smoke_endtoend
```
