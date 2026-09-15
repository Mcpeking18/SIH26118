package com.mrpl.wristband.ui

import android.app.Dialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.ColorDrawable
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.view.Window
import android.widget.EditText
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import com.mrpl.wristband.R
import com.mrpl.wristband.data.DosimetryBridge
import com.mrpl.wristband.data.ScanUiResult

class ScannerActivity : AppCompatActivity() {

    private var isTorchOn = false
    private var isFrontCamera = false
    private var selectedBitmap: Bitmap? = null
    private lateinit var ivPreview: ImageView
    private lateinit var tvStandby: TextView

    private val pickImageLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        uri?.let {
            try {
                @Suppress("DEPRECATION")
                val bitmap = MediaStore.Images.Media.getBitmap(contentResolver, it)
                selectedBitmap = bitmap
                ivPreview.setImageBitmap(bitmap)
                tvStandby.text = "● LOADED"
                tvStandby.setTextColor(getColor(R.color.h2s_blue_light))
                Toast.makeText(this, "Sample photo loaded. Press Initiate Scan to analyze.", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(this, "Failed to load sample image", Toast.LENGTH_SHORT).show()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_scanner)

        ivPreview = findViewById(R.id.ivCameraPreview)
        tvStandby = findViewById(R.id.tvStandbyStatus)

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
            if (isTorchOn) {
                btnTorch.setColorFilter(getColor(R.color.h2s_yellow))
                Toast.makeText(this, "Torch ON (Target Illuminator)", Toast.LENGTH_SHORT).show()
            } else {
                btnTorch.setColorFilter(getColor(R.color.white))
                Toast.makeText(this, "Torch OFF", Toast.LENGTH_SHORT).show()
            }
        }

        btnSwitchCamera.setOnClickListener {
            isFrontCamera = !isFrontCamera
            val mode = if (isFrontCamera) "Macro Inspection Camera" else "Standard Field Lens"
            Toast.makeText(this, "Switched to $mode", Toast.LENGTH_SHORT).show()
        }

        btnLibrary.setOnClickListener {
            pickImageLauncher.launch("image/*")
        }

        btnMetric.setOnClickListener {
            Toast.makeText(this, "Dosimetry Standards: OSHA (20 ppm ceiling), ACGIH (1 ppm TWA, 5 ppm STEL)", Toast.LENGTH_LONG).show()
        }

        btnInitiateScan.setOnClickListener {
            runScanPipeline()
        }

        tvManualEntry.setOnClickListener {
            showManualSensorIdDialog()
        }
    }

    private fun runScanPipeline(sensorIdHint: String = "H2S-G4-9982") {
        val dialog = Dialog(this)
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        dialog.setContentView(R.layout.dialog_scanner_processing)
        dialog.window?.setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
        dialog.setCancelable(false)
        dialog.show()

        val tvStep = dialog.findViewById<TextView>(R.id.tvProcessingStep)
        val handler = Handler(Looper.getMainLooper())

        handler.postDelayed({
            tvStep.text = "Detecting 4x4 ArUco markers..."
        }, 400)

        handler.postDelayed({
            tvStep.text = "Computing homography & perspective warp..."
        }, 800)

        handler.postDelayed({
            tvStep.text = "Sampling colorimetry & baseline patches..."
        }, 1200)

        handler.postDelayed({
            tvStep.text = "Evaluating ΔL* spectrophotometric dose..."
        }, 1600)

        handler.postDelayed({
            dialog.dismiss()
            // Execute clean integration point
            val result: ScanUiResult = DosimetryBridge.processBitmap(selectedBitmap, sensorIdHint)

            val intent = Intent(this, ExposureResultActivity::class.java)
            intent.putExtra("SCAN_RESULT", result)
            startActivity(intent)
            finish()
        }, 2000)
    }

    private fun showManualSensorIdDialog() {
        val builder = AlertDialog.Builder(this)
        builder.setTitle("Enter Wristband Sensor ID")
        val input = EditText(this)
        input.hint = "e.g. H2S-G4-9982"
        input.setPadding(48, 32, 48, 32)
        builder.setView(input)

        builder.setPositiveButton("Verify & Scan") { _, _ ->
            val id = input.text.toString().trim()
            if (id.isNotEmpty()) {
                runScanPipeline(id)
            } else {
                runScanPipeline("H2S-G4-9982")
            }
        }
        builder.setNegativeButton("Cancel", null)
        builder.show()
    }
}
