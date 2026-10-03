# 🧪 SIH26118 - Passive Colorimetric H2S Exposure-Dosimeter Wristband

<div align="center">
  <b>Smart India Hackathon 2026 - Problem Statement 118</b><br>
  <i>Mangalore Refinery and Petrochemicals Limited (MRPL)</i><br><br>
</div>

An innovative, purely passive approach to H₂S dosimetry. A worker wears a wristband with absolutely no electronics. A **CuSO₄·5H₂O (Copper II Sulfate)** sensing strip on Whatman paper (under an ePTFE membrane) reacts with ambient hydrogen sulphide, darkening in proportion to the accumulated dose. 

At the end of the shift, a team leader photographs the wristband using our **Android App**. The app uses Computer Vision (OpenCV) to rectify the image, normalize the illumination and color against reference patches, calculate the accumulated dose (in `ppm·hr`) and the 8-hour Time-Weighted Average (`TWA ppm`), and evaluates it against safety limits.

The wearable is completely passive because it has to be: sour-service areas in refineries are ATEX/PESO Zone 0, where intrinsically safe electronic dosimeters are expensive and non-certified ones are strictly forbidden. **All the intelligence lives on the smartphone and the cloud.**

---

## 🌟 Key Achievements & What We Built

We took the initial Python mathematical prototypes and scaled them into a complete, deployment-ready software ecosystem:

### 📱 1. Native Android Application (Kotlin + OpenCV)
The mathematical Python prototypes were successfully ported to a native, performant Android app:
- **ArUco Detection & Rectification**: Warps the wristband photo into a flat plane regardless of the angle it was taken at.
- **Illumination & Color Normalization**: Uses Matrix Polynomial Regression (and Von Kries fallbacks) against printed reference patches on the wristband to ensure the exact same reading regardless of the smartphone's camera, flash, or environmental lighting.
- **Scientific Dosimetry**: Calculates `Delta L*` (Lightness shift) and `Delta E00` to measure the chemical reaction and extract exact `ppm·hr` values without "fudging" numbers.
- **Direct Cloud Sync**: The app instantly pushes finalized measurement records to the centralized HSE dashboard.

### 🌐 2. Centralized HSE Dashboard (Python FastAPI + SQLite)
A robust, lightweight backend for HSE (Health, Safety, and Environment) supervisors:
- **API Server**: A `FastAPI` service with `Pydantic` models and `SQLite` that safely ingests `POST /api/measurements` from all active smartphones on the field.
- **Interactive Web UI**: A beautiful, dark-themed industrial dashboard that focuses on clarity. Shows the **Latest Measurement**, an Exposure History log, and an interactive **Leaflet Map** to quickly identify H₂S risk clusters in specific refinery zones (like the SWS or SRU).

---

## 🏗️ Architecture

- **`android/`**: The native Kotlin + OpenCV application. Contains the CV pipeline, dosimetry math, and UI layers.
  - *Note: The massive OpenCV Android SDK (version 5.0.0+) is NOT tracked in Git. You must download the official OpenCV Android SDK and extract the `sdk` folder directly into `android/opencv/`.*
- **`backend/`**: The Python backend server and dashboard.
  - `hse/api.py`: FastAPI routes and SQLite integrations.
  - `dashboard/index.html`: The HTML/JS/CSS frontend for the dashboard.
- **`reference/python/`**: The golden mathematical reference implementation (the origin of our formulas). 

---

## 🧪 Chemistry and Calibration Status 

**We explicitly use CuSO₄, not Lead Acetate.** While lead acetate is a common colorimetric agent, it introduces severe heavy metal disposal issues and toxicity.

**Calibration Note:** 
Currently, the pipeline uses a synthetic placeholder calibration model for software testing. While preliminary lab tests using liquid Na₂S proved the progressive color change of CuSO₄, *liquid testing is not gaseous H₂S calibration.* 

Before field use, the calibration curve must be experimentally fitted against certified H₂S atmospheres at known concentration-time products. The software architecture strictly decouples this: when real lab data arrives, we simply update the configuration files. No computer vision or Android code needs to be rewritten.

## 🚀 Quick Start (Dashboard & API)

Run the FastAPI backend with Uvicorn (requires `fastapi`, `uvicorn`, `pydantic`):

```bash
# Set your PYTHONPATH to the project root
$env:PYTHONPATH="C:\Rishi\Hackathon\SIH26\SIH26118\reference\python"

# Start the API server
python -m uvicorn backend.hse.api:app --port 8000
```
Open your browser to `http://127.0.0.1:8000/dashboard/index.html` to view the HSE Dashboard!

*(To seed the dashboard with 15 synthetic scans for testing, run `POST http://127.0.0.1:8000/api/demo/seed?n=15`)*

---

*Built with ❤️ for SIH 2026*
