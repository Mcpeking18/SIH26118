package com.mrpl.wristband.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.widget.Button
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.mrpl.wristband.R
import com.mrpl.wristband.color.Colorimetry
import com.mrpl.wristband.color.Normalizer
import com.mrpl.wristband.config.WristbandSpec
import com.mrpl.wristband.cv.Detector
import com.mrpl.wristband.cv.Sampler
import com.mrpl.wristband.dosimetry.Dosimetry
import org.opencv.android.CameraBridgeViewBase
import org.opencv.android.CameraBridgeViewBase.CvCameraViewFrame
import org.opencv.android.CameraBridgeViewBase.CvCameraViewListener2
import org.opencv.android.OpenCVLoader
import org.opencv.core.Mat
import org.opencv.core.CvType
import org.opencv.imgproc.Imgproc

class DebugCameraActivity : AppCompatActivity(), CvCameraViewListener2 {

    private lateinit var cameraView: CameraBridgeViewBase
    private lateinit var tvDebugOutput: TextView
    private lateinit var btnCapture: Button

    private var captureRequested = false
    private lateinit var detector: Detector
    

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_debug_camera)

        cameraView = findViewById(R.id.cameraView)
        tvDebugOutput = findViewById(R.id.tvDebugOutput)
        btnCapture = findViewById(R.id.btnCapture)

        btnCapture.setOnClickListener {
            captureRequested = true
            tvDebugOutput.text = "Processing frame..."
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), 1)
        } else {
            initializeCamera()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 1 && grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
            initializeCamera()
        } else {
            tvDebugOutput.text = "Camera Permission Denied"
        }
    }

    private fun initializeCamera() {
        if (OpenCVLoader.initLocal()) {
            detector = Detector()
            cameraView.setCameraPermissionGranted()
            cameraView.setCvCameraViewListener(this)
            cameraView.enableView()
        } else {
            tvDebugOutput.text = "OpenCV Init Failed"
        }
    }

    override fun onPause() {
        super.onPause()
        cameraView.disableView()
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraView.disableView()
    }

    override fun onCameraViewStarted(width: Int, height: Int) {}

    override fun onCameraViewStopped() {}

    override fun onCameraFrame(inputFrame: CvCameraViewFrame): Mat {
        val rgba = inputFrame.rgba()

        if (captureRequested) {
            captureRequested = false
            
            val rgb = Mat()
            Imgproc.cvtColor(rgba, rgb, Imgproc.COLOR_RGBA2RGB)
            
            Thread {
                processPipeline(rgb)
            }.start()
        }

        return rgba
    }

    private fun logToUI(msg: String) {
        runOnUiThread {
            tvDebugOutput.append("\n$msg")
        }
    }

    private fun processPipeline(image: Mat) {
        runOnUiThread { tvDebugOutput.text = "=== PIPELINE START ===" }
        
        try {
            // 1. Detector
            logToUI("Detecting markers...")
            val detResult = detector.rectify(image)
            if (!detResult.ok) {
                logToUI("[FAIL] Detector: ${detResult.reason}")
                return
            }
            logToUI("[OK] Detector. Found ${detResult.nMarkers} markers. Error: ${String.format("%.3f", detResult.reprojRmseMm)} mm")

            // 2. Sampler
            logToUI("Extracting samples...")
            val samples = Sampler.sampleBadge(detResult.warped!!)

            logToUI("[OK] Sampler. Extracted patch & probe values.")

            // 3. Normalizer
            logToUI("Normalizing (luma mode)...")
            val normResult = Normalizer.normalizeBadge(samples, mode = "luma")
            if (!normResult.ok) {
                logToUI("[FAIL] Normalizer: ${normResult.reason}")
                return
            }
            logToUI("[OK] Normalizer. Used patches: ${normResult.usedPatches.joinToString()}")
            logToUI("   Locus projection (delta_l): ${String.format("%.3f", normResult.locusProjection)}")
            logToUI("   Chroma residual: ${String.format("%.3f", normResult.chromaResidual)}")

            // 4. Dosimetry
            logToUI("Assessing Dose (8h shift)...")
            val doseResult = Dosimetry.assessScan(
                observable = normResult.locusProjection,
                shiftHours = 8.0,
                deltaE00 = normResult.deltaE00,
                chromaResidual = normResult.chromaResidual,
                deltaLStar = normResult.deltaLStar
            )
            
            logToUI("[OK] Dosimetry.")
            logToUI("=== FINAL VERDICT ===")
            logToUI("Dose: ${String.format("%.2f", doseResult.dosePpmHr)} ppm*hr")
            logToUI("TWA (8h): ${String.format("%.2f", doseResult.twaPpm)} ppm")
            logToUI("Verdict: ${doseResult.verdict.name}")
            logToUI("Integrity OK: ${doseResult.integrityOk}")
            if (doseResult.messages.isNotEmpty()) {
                logToUI("Messages:\n" + doseResult.messages.joinToString("\n- ", prefix = "- "))
            }

        } catch (e: Exception) {
            logToUI("[FAIL] EXCEPTION: ${e.message}")
            e.printStackTrace()
        } finally {
            image.release()
        }
    }
}
