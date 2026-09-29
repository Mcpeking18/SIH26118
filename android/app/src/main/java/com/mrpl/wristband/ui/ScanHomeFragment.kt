package com.mrpl.wristband.ui

import android.Manifest
import android.app.Activity
import android.app.Dialog
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.graphics.Matrix
import android.graphics.drawable.ColorDrawable
import android.net.Uri
import android.content.Context
import android.os.Bundle
import com.mrpl.wristband.data.HistoryManager
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.Window
import android.widget.ImageButton
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
    private val currentWristbandId: String = "WB-DEMO-001" // Prototype Dummy ID

    private lateinit var cameraExecutor: ExecutorService
    
    private var isTorchOn = false
    private var camera: Camera? = null
    private var imageCapture: ImageCapture? = null
    
    private var isAutoMode = true
    private var isProcessingCapture = false
    private var consecutiveHits = 0
    private val HIT_THRESHOLD = 10
    private var lastAnalysisTime = 0L
    private var stabilizationStartTime = 0L

    private val detector by lazy { Detector() }

    private val requestPermissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { isGranted: Boolean ->
            if (isGranted) {
                startCamera()
            } else {
                Toast.makeText(requireContext(), "Camera permission is required to scan.", Toast.LENGTH_LONG).show()
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

        val prefs = requireContext().getSharedPreferences("scanner_prefs", Context.MODE_PRIVATE)
        isAutoMode = prefs.getBoolean("is_auto_mode", true)
        if (isAutoMode) {
            btnToggleMode.setImageResource(R.drawable.ic_auto_mode)
        } else {
            btnToggleMode.setImageResource(R.drawable.ic_manual_mode)
        }

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
            prefs.edit().putBoolean("is_auto_mode", isAutoMode).apply()
            consecutiveHits = 0
            stabilizationStartTime = 0L
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
            if (isProcessingCapture) return@setOnClickListener
            val capture = imageCapture ?: return@setOnClickListener
            
            isProcessingCapture = true
            tvStandby.text = "● CAPTURING..."
            tvStandby.setTextColor(requireContext().getColor(R.color.h2s_blue_light))
            
            capture.takePicture(
                ContextCompat.getMainExecutor(requireContext()),
                object : ImageCapture.OnImageCapturedCallback() {
                    @androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
                    override fun onCaptureSuccess(image: ImageProxy) {
                        var bitmap = image.toBitmap()
                        val rotationDegrees = image.imageInfo.rotationDegrees
                        if (rotationDegrees != 0) {
                            val matrix = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
                            bitmap = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
                        }
                        image.close()
                        runScanPipeline(bitmap, "H2S-G4-9982")
                    }
                    override fun onError(exception: ImageCaptureException) {
                        isProcessingCapture = false
                        Toast.makeText(requireContext(), "Capture failed: ${exception.message}", Toast.LENGTH_SHORT).show()
                    }
                }
            )
        }

        if (ContextCompat.checkSelfPermission(requireContext(), Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            startCamera()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(requireContext())
        cameraProviderFuture.addListener({
            val cameraProvider: ProcessCameraProvider = cameraProviderFuture.get()

            val displayRotation = viewFinder.display.rotation
            val rotation = when (displayRotation) {
                0 -> 0
                90 -> 90
                180 -> 180
                270 -> 270
                else -> 0
            }

            val preview = Preview.Builder()
                .setTargetRotation(rotation)
                .build()
                .also { it.setSurfaceProvider(viewFinder.surfaceProvider) }

            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .setTargetRotation(rotation)
                .build()

            val imageAnalyzer = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setTargetRotation(rotation)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor) { imageProxy ->
                        processImageProxy(imageProxy)
                    }
                }

            val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA
            try {
                cameraProvider.unbindAll()
                camera = cameraProvider.bindToLifecycle(viewLifecycleOwner, cameraSelector, preview, imageAnalyzer, imageCapture)
            } catch (exc: Exception) {
                Log.e("ScanHomeFragment", "Use case binding failed", exc)
            }
        }, ContextCompat.getMainExecutor(requireContext()))
    }

    @androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
    private fun processImageProxy(imageProxy: ImageProxy) {
        if (isProcessingCapture) {
            imageProxy.close()
            return
        }

        val currentTime = System.currentTimeMillis()
        if (currentTime - lastAnalysisTime < 200) { // 5 FPS cap
            imageProxy.close()
            return
        }
        
        lastAnalysisTime = currentTime

        try {
            var bitmap = imageProxy.toBitmap()
            
            // Apply rotation from ImageProxy metadata as a safety net
            // Target rotation on use cases should align frames, but this handles any mismatch
            val rotationDegrees = imageProxy.imageInfo.rotationDegrees
            if (rotationDegrees != 0) {
                val matrix = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
                bitmap = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
            }
            
            val rgbaMat = Mat()
            Utils.bitmapToMat(bitmap, rgbaMat)
            val mat = Mat()
            org.opencv.imgproc.Imgproc.cvtColor(rgbaMat, mat, org.opencv.imgproc.Imgproc.COLOR_RGBA2BGR)
            rgbaMat.release()
            
            val detection = detector.rectify(mat)
            if (detection.ok) {
                if (isAutoMode && !isProcessingCapture) {
                    if (stabilizationStartTime == 0L) {
                        stabilizationStartTime = System.currentTimeMillis()
                    }
                    
                    val elapsed = System.currentTimeMillis() - stabilizationStartTime
                    val remaining = 5 - (elapsed / 1000).toInt()
                    
                    if (elapsed >= 5000) {
                        isProcessingCapture = true
                        stabilizationStartTime = 0L
                        activity?.runOnUiThread {
                            tvStandby.text = "● CAPTURING..."
                            tvStandby.setTextColor(requireContext().getColor(R.color.h2s_blue_light))
                            
                            imageCapture?.takePicture(
                                ContextCompat.getMainExecutor(requireContext()),
                                object : ImageCapture.OnImageCapturedCallback() {
                                    @androidx.annotation.OptIn(androidx.camera.core.ExperimentalGetImage::class)
                                    override fun onCaptureSuccess(image: ImageProxy) {
                                        var bmp = image.toBitmap()
                                        val rotationDegrees = image.imageInfo.rotationDegrees
                                        if (rotationDegrees != 0) {
                                            val matrix = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
                                            bmp = Bitmap.createBitmap(bmp, 0, 0, bmp.width, bmp.height, matrix, true)
                                        }
                                        image.close()
                                        runScanPipeline(bmp, "H2S-G4-9982")
                                    }
                                    override fun onError(exception: ImageCaptureException) {
                                        isProcessingCapture = false
                                        stabilizationStartTime = 0L
                                        Toast.makeText(requireContext(), "Capture failed", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            )
                        }
                    } else {
                        activity?.runOnUiThread {
                            tvStandby.text = "● HOLD STEADY... ${remaining}s"
                            tvStandby.setTextColor(requireContext().getColor(R.color.h2s_yellow))
                        }
                    }
                } else if (!isAutoMode && !isProcessingCapture) {
                    activity?.runOnUiThread {
                        tvStandby.text = "● ALIGNED - READY TO CAPTURE"
                        tvStandby.setTextColor(requireContext().getColor(R.color.h2s_yellow))
                    }
                }
            } else {
                stabilizationStartTime = 0L
                activity?.runOnUiThread {
                    tvStandby.text = "● ALIGN THE WRISTBAND"
                    tvStandby.setTextColor(requireContext().getColor(R.color.h2s_text_muted))
                }
            }
            mat.release()
        } catch (e: Exception) {
            Log.e("ScanHomeFragment", "Error processing frame", e)
        } finally {
            imageProxy.close()
        }
    }
    
    private fun processGalleryImage(uri: Uri) {
        try {
            val inputStream: InputStream? = requireContext().contentResolver.openInputStream(uri)
            val bitmap = BitmapFactory.decodeStream(inputStream)
            inputStream?.close()
            
            if (bitmap != null) {
                runScanPipeline(bitmap, "GALLERY-UPLOAD")
            }
        } catch (e: Exception) {
            e.printStackTrace()
            Toast.makeText(requireContext(), "Failed to load image", Toast.LENGTH_SHORT).show()
        }
    }

    private fun runScanPipeline(bitmap: Bitmap, sensorIdHint: String) {
        val actualId = if (sensorIdHint == "GALLERY-UPLOAD") sensorIdHint else currentWristbandId
        if (!isAdded || activity == null) {
            isProcessingCapture = false
            return
        }
        
        val dialog = Dialog(requireContext())
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        dialog.setContentView(R.layout.dialog_scanner_processing)
        dialog.window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
        dialog.setCancelable(false)
        dialog.show()

        val tvStep = dialog.findViewById<TextView>(R.id.tvProcessingStep)
        val handler = Handler(Looper.getMainLooper())

        handler.postDelayed({ tvStep.text = "Processing wristband..." }, 200)
        
        handler.postDelayed({
            Thread {
                val result = DosimetryBridge.processBitmap(bitmap, actualId)
                activity?.runOnUiThread {
                    dialog.dismiss()
                    
                    if (result.scanState?.name == "PROCESSING_ERROR" || result.scanState?.name == "POOR_IMAGE_QUALITY" || result.errorMessage != null) {
                        // OpenCV failed, keep scanner open and allow retry
                        stabilizationStartTime = 0L
                        isProcessingCapture = false
                        Toast.makeText(requireContext(), "Wristband could not be detected/aligned. Please try again.", Toast.LENGTH_LONG).show()
                    } else {
                        // Success, open result activity. 
                        // Do NOT set isProcessingCapture = false here, leave it true to block auto-capture 
                        // until onResume() is called when returning to this screen.
                        HistoryManager.saveRecord(requireContext(), result)
                        val intent = Intent(requireActivity(), ExposureResultActivity::class.java)
                        intent.putExtra("SCAN_RESULT", result)
                        startActivity(intent)
                    }
                }
            }.start()
        }, 500)
    }
    
    override fun onResume() {
        super.onResume()
        consecutiveHits = 0
        stabilizationStartTime = 0L
        isProcessingCapture = false
    }

    override fun onDestroyView() {
        super.onDestroyView()
        cameraExecutor.shutdown()
    }
}
