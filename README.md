# 🧪 SIH26118 - Passive Colorimetric H2S Exposure-Dosimeter Wristband

<div align="center">
  <b>Smart India Hackathon 2026 - Problem Statement 118</b><br>
  <i>Mangalore Refinery and Petrochemicals Limited (MRPL)</i><br><br>
</div>

## 📖 Abstract

Hydrogen sulfide (H₂S) is a routine hazard in oil refineries, sewers, wastewater, and biogas plants. At higher concentrations, it causes olfactory fatigue, meaning the natural odor warning vanishes as danger escalates. The challenge is sharpest in refinery sour-service areas classified as **ATEX or PESO Zone 0**, where explosive atmospheres exist continuously. 

In these zones, traditional electronic detectors are either prohibited or require costly intrinsic-safety certification. Even certified units depend on batteries and frequent calibration, leading to them being shared among teams. As a result, readings describe the last person holding the detector—leaving many contract crews unmeasured. Existing passive badges exist, but require workers to judge color changes by eye against a printed ladder, which varies drastically with lighting and leaves zero digital record.

**Our Proposed Solution:** An intrinsically safe, battery-free wristband dosimeter coupled with an offline smartphone computer-vision application to accurately digitize and log H₂S exposure.

---

## 🌟 Key Features & Innovations

### 1. 🛡️ Battery-Free Intrinsically Safe Wearable (Zone 0 Compliant)
The physical wristband contains absolutely no electronics. It holds a **CuSO₄·5H₂O (Copper II Sulfate)** sensing strip on Whatman paper under a diffusion-controlling ePTFE membrane. It is completely intrinsically safe by elimination, not mitigation.

### 2. 📱 Computer Vision Dose Readout (Native Android App)
At the end of a shift, a team leader photographs the wristband using our Android App (Kotlin + OpenCV). The application performs:
- **ArUco Fiducial Rectification:** Warps the badge into a flat plane regardless of camera angle.
- **Dynamic Illumination Normalization:** Uses printed reference patches to apply Matrix Polynomial Regression and Von Kries transformations to completely neutralize camera auto-white-balance, flash variations, and HDR tone mapping.
- **Scientific Colorimetry:** Measures chemical darkening via `Delta L*` (Lightness) and computes the exact accumulated dose (`ppm·hr`) and the 8-hour Time-Weighted Average (`TWA ppm`).

### 3. 🌐 Centralized HSE Cloud Dashboard (Python FastAPI)
The native app automatically syncs exposure records to a centralized HSE (Health, Safety, and Environment) dashboard.
- Built with **Python, FastAPI, and SQLite**.
- Industrial dark-themed web interface highlighting the **Latest Measurements**, historical exposure logs, and an interactive **Leaflet Map** to pinpoint H₂S risks in specific refinery areas (e.g., SWS, SRU).

---

## 🏗️ Repository Architecture

- **`android/`**: The native Kotlin + OpenCV application. Contains the CV pipeline, dosimetry math, and UI layers.
  - *Note: The massive OpenCV Android SDK (version 5.0.0+) is NOT tracked in Git. You must download the official OpenCV Android SDK and extract the `sdk` folder directly into `android/opencv/`.*
- **`backend/`**: The Python backend server and dashboard.
  - `hse/api.py`: FastAPI endpoints that safely ingest `POST /api/measurements` from field smartphones.
  - `dashboard/index.html`: The HTML/JS/CSS frontend for the dashboard.
- **`reference/python/`**: The golden mathematical reference implementation (the origin of our computer vision and calibration formulas). 
- **`H2S_Dosimeter_White_Paper_Final.docx`**: Our complete engineering white paper detailing the physical chemistry, chassis materials (medical-grade silicone), and pipeline math.

---

## 🧪 Chemistry and Calibration

**Why Copper Sulfate?** We explicitly use CuSO₄ instead of Lead Acetate to completely eliminate heavy metal toxicity and disposal hazards.

**Calibration Architecture:** The software pipeline calculates exact CIELAB metrics (`L*a*b*`), but currently uses a synthetic placeholder calibration curve to map `Delta L*` to `ppm·hr`. Before actual field deployment, this curve will be easily updated by swapping a single configuration profile with data from certified H₂S gas chamber testing—requiring zero code changes to the app itself.

---

## 🚀 Quick Start (Running the Dashboard Locally)

Run the FastAPI backend with Uvicorn (requires `fastapi`, `uvicorn`, `pydantic`):

```bash
# Set your PYTHONPATH to the project root
$env:PYTHONPATH="C:\Rishi\Hackathon\SIH26\SIH26118\reference\python"

# Start the API server
python -m uvicorn backend.hse.api:app --port 8000
```
Open your browser to `http://127.0.0.1:8000/dashboard/index.html` to view the HSE Dashboard!

*(To seed the dashboard with synthetic scans for testing, run `POST http://127.0.0.1:8000/api/demo/seed?n=15`)*

---

*Built with ❤️ for SIH 2026*
