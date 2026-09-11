# Python to Android/Kotlin Migration Map

| Python Module (reference/python/engine/) | Kotlin Package/Class (android/app/.../wristband/) | OpenCV Dependency | Android Dependency | Pure Math? | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| Badge_spec.py | config.WristbandSpec | No | No | Yes | Defines physical geometries in mm. Outputs coordinates. |
| detect.py | cv.Detector | **Yes** (ArUco, WarpPerspective) | No | No | Finds markers and rectifies image. In: Image, Out: Warped canonical plane. |
| 
oi.py | cv.Sampler | **Yes** (Core operations, Means) | No | No | Extracts patch statistics using WristbandSpec. In: Warped image, Out: RGB Samples. |
| 
ormalize.py | color.Normalizer | No (pure matrix math) | No | Yes | Fits illumination/CCM. Corrects optical error. In: Samples, Out: Normalized Samples. |
| colorimetry.py | color.Colorimetry | No (pure matrix math) | No | Yes | Converts RGB to CIELAB and computes dE00. In: RGB, Out: L*a*b*. |
| dosimetry.py | dosimetry.Dosimetry | No (pure math) | No | Yes | Evaluates -dL* against CalibrationModel to estimate ppm.hr. In: L*a*b*, Out: Verdict. |
| pipeline.py | cv.Pipeline | Yes (orchestrates cv) | No | No | Chains detect -> sample -> normalize -> assess. |
