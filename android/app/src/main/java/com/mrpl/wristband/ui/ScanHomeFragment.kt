package com.mrpl.wristband.ui

import android.Manifest
import android.app.Activity
import android.app.Dialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.Window
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import com.mrpl.wristband.R
import com.mrpl.wristband.cv.Detector
import com.mrpl.wristband.data.DosimetryBridge
import com.mrpl.wristband.data.ScanUiResult
import org.opencv.android.Utils
import org.opencv.core.Mat
import java.io.InputStream
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class ScanHomeFragment : Fragment() {

    private lateinit var viewFinder: PreviewView
    private lateinit var tvStandby: TextView
    private lateinit var cameraExecutor: ExecutorService
    
    private var isTorchOn = false
    private var isFrontCamera = false
    private var camera: Camera? = null
    
    private var isAutoMode = true
    private var autoCaptureActive = true
    private var consecutiveHits = 0
    private val HIT_THRESHOLD = 10
    private var lastAnalysisTime = 0L
    private var isProcessingFrame = false

    private val detector by lazy { Detector() }

    private val requestPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted: Boolean ->
            if (isGranted) {
                startCamera()
            } else {
                Toast.makeText(requireContext(), "Camera permission is required to scan.", Toast.LENGTH_LONG).show()
                // You could show a "Permission Denied" UI layout here
            }
        }

    private val pickImageLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == Activity.RESULT_OK) {
                val data: Intent? = result.data
                val uri: Uri? = data?.data
                if (uri != null) {
                    processGalleryImage(uri)
                }
            }
        }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        return inflater.inflate(R.layout.fragment_scan_home, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        viewFinder = view.findViewById(R.id.viewFinder)
        tvStandby = view.findViewById(R.id.tvStandbyStatus)
        cameraExecutor = Executors.newSingleThreadExecutor()

        val btnTorch = view.findViewById<ImageButton>(R.id.btnTorch)
        
        val btnToggleMode = view.findViewById<ImageButton>(R.id.btnToggleMode)
        val btnLibrary = view.findViewById<LinearLayout>(R.id.btnLibrary)
        val btnInitiateScan = view.findViewById<LinearLayout>(R.id.btnInitiateScan)
        val tvManualEntry = view.findViewById<TextView>(R.id.tvManualSensorEntry)

        btnTorch.setOnClickListener {
            isTorchOn = !isTorchOn
            camera?.cameraControl?.enableTorch(isTorchOn)
            if (isTorchOn) {
                btnTorch.setColorFilter(requireContext().getColor(R.color.h2s_yellow))
            } else {
                btnTorch.setColorFilter(requireContext().getColor(R.color.white))
            }
        }

        
        
        btnToggleMode.setOnClickListener {
            isAutoMode = !isAutoMode
            autoCaptureActive = true
            consecutiveHits = 0
            if (isAutoMode) {
                btnToggleMode.setImageResource(R.drawable.ic_auto_mode)
                Toast.makeText(requireContext(), "Auto-scan enabled", Toast.LENGTH_SHORT).show()
            } else {
                btnToggleMode.setImageResource(R.drawable.ic_manual_mode)
                Toast.makeText(requireContext(), "Manual scan enabled. Tap shutter to capture.", Toast.LENGTH_SHORT).show()
            }
        }

        btnLibrary.setOnClickListener {
            val intent = Intent(Intent.ACTION_PICK)
            intent.type = "image/*"
            pickImageLauncher.launch(intent)
        }
        
        btnInitiateScan.setOnClickListener {
            if (!isAutoMode && autoCaptureActive) {
                autoCaptureActive = false
                // Force a capture on the next frame or use a distinct capture process
                // Here we just flag that manual shutter was pressed
                Toast.makeText(requireContext(), "Capturing...", Toast.LENGTH_SHORT).show()
                // We let processImageProxy catch the flag if we wanted to grab a frame,
                // but since it's cleaner, we will set a flag that the next valid frame is grabbed.
                manualShutterRequested = true
            } else if (isAutoMode) {
                Toast.makeText(requireContext(), "In Auto mode. Hold camera steady over badge.", Toast.LENGTH_SHORT).show()
            }
        }

        tvManualEntry.setOnClickListener {
            // handle entry
        }

        if (ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private var manualShutterRequested = false

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(requireContext())
        cameraProviderFuture.addListener({
            val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()
            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(viewFinder.surfaceProvider)
            }

            val imageAnalyzer = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor) { imageProxy ->
                        processImageProxy(imageProxy)
                    }
                }

            val cameraSelector = if (isFrontCamera) CameraSelector.DEFAULT_FRONT_CAMERA else CameraSelector.DEFAULT_BACK_CAMERA

            try {
                cameraProvider.unbindAll()
                camera = cameraProvider.bindToLifecycle(viewLifecycleOwner, cameraSelector, preview, imageAnalyzer)
            } catch (exc: Exception) {
                Log.e("ScanHomeFragment", "Use case binding failed", exc)
            }
        }, ContextCompat.getMainExecutor(requireContext()))
    }

    @androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
    private fun processImageProxy(imageProxy: ImageProxy) {
        if (!autoCaptureActive || isProcessingFrame) {
            imageProxy.close()
            return
        }

        val currentTime = System.currentTimeMillis()
        if (currentTime - lastAnalysisTime < 200) { // 5 FPS cap
            imageProxy.close()
            return
        }
        
        isProcessingFrame = true
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
                
                requireActivity().runOnUiThread {
                    tvStandby.text = "* ALIGNING (${consecutiveHits}/${HIT_THRESHOLD})"
                    tvStandby.setTextColor(requireContext().getColor(R.color.h2s_yellow))
                }
                
                if ((isAutoMode && consecutiveHits >= HIT_THRESHOLD) || (!isAutoMode && manualShutterRequested)) {
                    autoCaptureActive = false
                    manualShutterRequested = false
                    val safeBitmap = bitmap.copy(Bitmap.Config.ARGB_8888, false)
                    requireActivity().runOnUiThread {
                        runScanPipeline(safeBitmap, "H2S-G4-9982")
                    }
                }
            } else {
                consecutiveHits = 0
                manualShutterRequested = false // reset if frame is bad
                requireActivity().runOnUiThread {
                    tvStandby.text = "* SEARCHING"
                    tvStandby.setTextColor(requireContext().getColor(R.color.h2s_text_muted))
                }
            }
            mat.release()
        } catch (e: Exception) {
            Log.e("ScanHomeFragment", "Error processing frame", e)
        } finally {
            isProcessingFrame = false
            imageProxy.close()
        }
    }
    
    private fun processGalleryImage(uri: Uri) {
        try {
            val inputStream: InputStream? = requireContext().contentResolver.openInputStream(uri)
            val bitmap = BitmapFactory.decodeStream(inputStream)
            inputStream?.close()
            
            if (bitmap != null) {
                // Resize if needed, then pass to pipeline
                runScanPipeline(bitmap, "GALLERY-UPLOAD")
            }
        } catch (e: Exception) {
            e.printStackTrace()
            Toast.makeText(requireContext(), "Failed to load image", Toast.LENGTH_SHORT).show()
        }
    }

    private fun runScanPipeline(bitmap: Bitmap, sensorIdHint: String) {
        val dialog = Dialog(requireContext())
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
                if (activity != null) {
                    requireActivity().runOnUiThread {
                        val intent = Intent(requireActivity(), ExposureResultActivity::class.java)
                        intent.putExtra("SCAN_RESULT", result)
                        startActivity(intent)
                    }
                }
            }.start()
        }, 1800)
    }
    
    override fun onResume() {
        super.onResume()
        autoCaptureActive = true
        consecutiveHits = 0
        manualShutterRequested = false
    }

    override fun onDestroyView() {
        super.onDestroyView()
        cameraExecutor.shutdown()
    }
}
