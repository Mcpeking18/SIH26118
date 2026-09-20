package com.mrpl.wristband.ui

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AlertDialog
import com.mrpl.wristband.R
import com.mrpl.wristband.data.ScanUiResult
import com.mrpl.wristband.data.ScanState
import com.mrpl.wristband.ui.view.TrendLineChartView

class ExposureResultActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_exposure_result)

        @Suppress("DEPRECATION")
        val result = intent.getSerializableExtra("SCAN_RESULT") as? ScanUiResult
            ?: return

        if (result.scanState != ScanState.SUCCESS) {
            androidx.appcompat.app.AlertDialog.Builder(this)
                .setTitle("Scan Failed")
                .setMessage(result.errorMessage ?: "Unknown error during scan.")
                .setCancelable(false)
                .setPositiveButton("Try Again") { _, _ ->
                    val intent = Intent(this, MainActivity::class.java)
                    intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP
                    startActivity(intent)
                    finish()
                }
                .show()
        }

        // Bind data to views
        findViewById<TextView>(R.id.tvResultSensorId).text = result.wristbandId
        findViewById<TextView>(R.id.tvResultPeak).text = String.format("%.2f PPM", result.peakIntensityPpm)
        findViewById<TextView>(R.id.tvResultCumulative).text = String.format("%.2f PPM", result.cumulativeConcentrationPpm)
        findViewById<TextView>(R.id.tvResultVerdict).text = result.verdict
        
        findViewById<TextView>(R.id.tvLastSync).text = result.timestamp

        val tvPeakLevel = findViewById<TextView>(R.id.tvResultPeakLevel)
        tvPeakLevel.text = "LEVEL: ${result.level}"
        val levelColor = when (result.level) {
            "LOW" -> Color.parseColor("#10B981")
            "ELEVATED" -> Color.parseColor("#F59E0B")
            "HIGH" -> Color.parseColor("#F97316")
            "CRITICAL" -> Color.parseColor("#EF4444")
            else -> Color.parseColor("#10B981")
        }
        tvPeakLevel.setTextColor(levelColor)
        findViewById<TextView>(R.id.tvResultVerdict).setTextColor(levelColor)

        val calibText = "CALIBRATION\\nPENDING LAB"
        
        // Seed chart with mock waveform data
        val chart = findViewById<TrendLineChartView>(R.id.chartWaveform)
        chart.setData(
            floatArrayOf(0.3f, 0.6f, 0.8f, 1.42f, 1.1f, 0.7f, 0.34f, 0.45f),
            Color.parseColor("#3B82F6"),
            0.72f,
            Color.parseColor("#F59E0B")
        )

        // Actions
        val btnDashboard = findViewById<LinearLayout>(R.id.btnGoDashboard)
        val btnScanNew = findViewById<LinearLayout>(R.id.btnScanNewDevice)
        val btnViewHistory = findViewById<LinearLayout>(R.id.btnViewFullHistory)

        btnDashboard.setOnClickListener {
            val intent = Intent(this, MainActivity::class.java)
            intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP
            startActivity(intent)
            finish()
        }

        btnScanNew.setOnClickListener {
            startActivity(Intent(this, ScannerActivity::class.java))
            finish()
        }

        btnViewHistory.setOnClickListener {
            // Navigate to main activity on History tab
            val intent = Intent(this, MainActivity::class.java)
            intent.putExtra("OPEN_TAB", "HISTORY")
            intent.flags = Intent.FLAG_ACTIVITY_CLEAR_TOP
            startActivity(intent)
            finish()
        }
    }
}
