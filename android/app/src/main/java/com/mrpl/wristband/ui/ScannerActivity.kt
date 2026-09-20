package com.mrpl.wristband.ui

import android.app.Dialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Window
import android.widget.EditText
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import com.mrpl.wristband.R
import com.mrpl.wristband.cv.Detector
import com.mrpl.wristband.data.DosimetryBridge
import com.mrpl.wristband.data.ScanUiResult
import org.opencv.android.OpenCVLoader
import org.opencv.android.Utils
import org.opencv.core.Mat
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class ScannerActivity : AppCompatActivity() {

    private lateinit var viewFinder: PreviewView
    private lateinit var tvStandby: TextView
    private lateinit var cameraExecutor: ExecutorService
    
    private var isTorchOn = false
    private var isFrontCamera = false
    private var camera: Camera? = null
    private var autoCaptureActive = true
    private var consecutiveHits = 0
    private val HIT_THRESHOLD = 10
    private var lastAnalysisTime = 0L
    
    private val detector by lazy { Detector() }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!OpenCVLoader.initDebug()) {
            Log.e("OpenCV", "Unable to load OpenCV!")
        }
        setContentView(R.layout.activity_scanner)

        viewFinder = findViewById(R.id.viewFinder)
        tvStandby = findViewById(R.id.tvStandbyStatus)
        cameraExecutor = Executors.newSingleThreadExecutor()

        val btnBack = findViewById<ImageView>(R.id.btnScannerBack)
        val btnTorch = findViewById<ImageButton>(R.id.btnTorch)
        val btnSwitchCamera = findViewById<ImageButton>(R.id.btnSwitchCamera)
        val btnLibrary = findViewById<LinearLayout>(R.id.btnLibrary)
        val btnInitiateScan = findViewById<LinearLayout>(R.id.btnInitiateScan)
        val btnMetric = findViewById<LinearLayout>(R.id.btnMetric)
        val tvManualEntry = findViewById<TextView>(R.id.tvManualSensorEntry)

        btnBack.setOnClickListener { finish() }

        btnTorch.setOnClickListener {
            isTorchOn = !isTorchOn
            camera?.cameraControl?.enableTorch(isTorchOn)
            if (isTorchOn) {
                btnTorch.setColorFilter(getColor(R.color.h2s_yellow))
            } else {
                btnTorch.setColorFilter(getColor(R.color.white))
            }
        }

        btnSwitchCamera.setOnClickListener {
            isFrontCamera = !isFrontCamera
            startCamera()
        }

        btnLibrary.setOnClickListener {
            Toast.makeText(this, "Manual image picker disabled in live scan mode.", Toast.LENGTH_SHORT).show()
        }
        
        btnInitiateScan.setOnClickListener {
            // Manual override for trigger
            Toast.makeText(this, "Please hold the camera steady. Auto-scan is active.", Toast.LENGTH_SHORT).show()
        }

        tvManualEntry.setOnClickListener {
            // show dialog
        }

        startCamera()
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener({
            val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(viewFinder.surfaceProvider)
            }

            val imageAnalyzer = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor, { imageProxy ->
                        processImageProxy(imageProxy)
                    })
                }

            val cameraSelector = if (isFrontCamera) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA

            try {
                cameraProvider.unbindAll()
                camera = cameraProvider.bindToLifecycle(this, cameraSelector, preview, imageAnalyzer)
            } catch (exc: Exception) {
                Log.e("ScannerActivity", "Use case binding failed", exc)
            }
        }, ContextCompat.getMainExecutor(this))
    }

    @androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
    private fun processImageProxy(imageProxy: ImageProxy) {
        if (!autoCaptureActive) {
            imageProxy.close()
            return
        }

        val currentTime = System.currentTimeMillis()
        if (currentTime - lastAnalysisTime < 200) { // Capped at 5 FPS
            imageProxy.close()
            return
        }
        lastAnalysisTime = currentTime

        try {
            val bitmap = imageProxy.toBitmap()
            val rgbaMat = Mat()
            Utils.bitmapToMat(bitmap, rgbaMat)
            val mat = Mat()
            org.opencv.imgproc.Imgproc.cvtColor(rgbaMat, mat, org.opencv.imgproc.Imgproc.COLOR_RGBA2BGR)
            rgbaMat.release()
            
            val detection = detector.rectify(mat)
            if (detection.ok) {
                consecutiveHits++
                runOnUiThread {
                    tvStandby.text = "● ALIGNING (${consecutiveHits}/${HIT_THRESHOLD})"
                    tvStandby.setTextColor(getColor(R.color.h2s_yellow))
                }
                
                if (consecutiveHits >= HIT_THRESHOLD) {
                    autoCaptureActive = false
                    runOnUiThread {
                        runScanPipeline(bitmap, "H2S-G4-9982")
                    }
                }
            } else {
                consecutiveHits = 0
                runOnUiThread {
                    tvStandby.text = "● SEARCHING"
                    tvStandby.setTextColor(getColor(R.color.h2s_text_muted))
                }
            }
        } catch (e: Exception) {
            Log.e("ScannerActivity", "Error processing frame", e)
        } finally {
            imageProxy.close()
        }
    }

    private fun runScanPipeline(bitmap: Bitmap, sensorIdHint: String) {
        val dialog = Dialog(this)
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        dialog.setContentView(R.layout.dialog_scanner_processing)
        dialog.window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
        dialog.setCancelable(false)
        dialog.show()

        val tvStep = dialog.findViewById<TextView>(R.id.tvProcessingStep)
        val handler = Handler(Looper.getMainLooper())

        handler.postDelayed({ tvStep.text = "Detecting 4x4 ArUco markers..." }, 200)
        handler.postDelayed({ tvStep.text = "Computing homography & perspective warp..." }, 600)
        handler.postDelayed({ tvStep.text = "Sampling colorimetry & baseline patches..." }, 1000)
        handler.postDelayed({ tvStep.text = "Evaluating dose..." }, 1400)
        
        handler.postDelayed({
            dialog.dismiss()
            Thread {
                val result: ScanUiResult = DosimetryBridge.processBitmap(bitmap, sensorIdHint)
                runOnUiThread {
                    val intent = Intent(this@ScannerActivity, ExposureResultActivity::class.java)
                    intent.putExtra("SCAN_RESULT", result)
                    startActivity(intent)
                    finish()
                }
            }.start()
        }, 1800)
    }
    
    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }
}
