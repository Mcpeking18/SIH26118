package com.mrpl.wristband.ui

import android.os.Build
import android.os.Bundle
import android.widget.ArrayAdapter
import android.widget.Spinner
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.mrpl.wristband.R
import com.mrpl.wristband.data.ScanUiResult

class ExposureResultActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_exposure_result)

        val btnSaveResult = findViewById<Button>(R.id.btnSaveResult)
        val btnClose = findViewById<ImageView>(R.id.btnCloseResult)

        
        val spinnerArea = findViewById<Spinner>(R.id.spinnerArea)
        val areas = listOf("Unknown Area") + com.mrpl.wristband.data.DemoAreas.AREAS
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, areas)
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
        spinnerArea.adapter = adapter


        btnClose.setOnClickListener { finish() }

        val scanResult: ScanUiResult? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableExtra("SCAN_RESULT", ScanUiResult::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableExtra("SCAN_RESULT")
        }

        val tvDose = findViewById<TextView>(R.id.tvDosePpmHr)
        val tvTwa = findViewById<TextView>(R.id.tvTwaPpm)
        val tvDeltaL = findViewById<TextView>(R.id.tvDeltaL)
        val tvDeltaE = findViewById<TextView>(R.id.tvDeltaE)
        val tvTimestamp = findViewById<TextView>(R.id.tvTimestamp)
        val tvWristbandId = findViewById<TextView>(R.id.tvWristbandId)

        if (scanResult != null) {
            tvDose.text = if (scanResult.dosePpmHr != null) String.format("%.2f", scanResult.dosePpmHr) else "--"
            tvTwa.text = if (scanResult.twaPpm != null) String.format("%.2f", scanResult.twaPpm) else "--"
            tvDeltaL.text = String.format("%.2f", scanResult.deltaLStar ?: 0.0)
            tvDeltaE.text = String.format("%.2f", scanResult.deltaE00 ?: 0.0)
            tvTimestamp.text = scanResult.timestamp ?: "Unknown Time"
            tvWristbandId.text = scanResult.wristbandId ?: "Unknown ID" 
            val tvClassification = findViewById<TextView>(R.id.tvClassification)
            val dose = scanResult.dosePpmHr
            if (dose != null) {
                val status = com.mrpl.wristband.data.DemoExposureStatus.fromDose(dose)
                tvClassification.text = status.label
                val parsedColor = android.graphics.Color.parseColor(status.colorHex)
                tvClassification.setTextColor(parsedColor)
                tvDose.setTextColor(parsedColor)
                tvTwa.setTextColor(parsedColor)
            } else {
                tvClassification.visibility = android.view.View.GONE
            }
        } else {
            tvDose.text = "--"
            tvTwa.text = "--"
            tvDeltaL.text = "--"
            tvDeltaE.text = "--"
            tvTimestamp.text = "--"
            tvWristbandId.text = "--"
        }

        btnSaveResult.setOnClickListener {
            val selectedArea = spinnerArea.selectedItem as String
            if (scanResult != null) {
                val finalZone = if (selectedArea == "Unknown Area") null else selectedArea
                val updatedResult = scanResult.copy(zone = finalZone)
                com.mrpl.wristband.data.HistoryManager.saveRecord(this, updatedResult)
                
                // Sync to dashboard backend
                Thread {
                    try {
                        // Edit this IP if you are testing on a real physical phone instead of emulator!
                        // For physical phone, find your laptop's IPv4 address (e.g., 192.168.x.x)
                        val backendIp = "192.168.1.105" 
                        val url = java.net.URL("http://$backendIp:8000/api/measurements")
                        val conn = url.openConnection() as java.net.HttpURLConnection
                        conn.requestMethod = "POST"
                        conn.setRequestProperty("Content-Type", "application/json")
                        conn.doOutput = true
                        
                        val dose = updatedResult.dosePpmHr ?: 0.0
                        val twa = updatedResult.twaPpm ?: 0.0
                        // Default verdict safely to LOW/SAFE if null
                        val status = updatedResult.verdict ?: "SAFE"
                        val zoneStr = updatedResult.zone ?: "Unknown"
                        val wid = updatedResult.wristbandId
                        
                        val json = """{"worker_id": "$wid", "worker_name": "Test Worker", "zone": "$zoneStr", "dose_ppm_hr": $dose, "twa_ppm": $twa, "status": "$status"}"""
                        
                        conn.outputStream.use { it.write(json.toByteArray()) }
                        val code = conn.responseCode
                        android.util.Log.d("H2S_SYNC", "Synced to backend: $code")
                    } catch (e: Exception) {
                        android.util.Log.e("H2S_SYNC", "Failed to sync to dashboard: ${e.message}")
                    }
                }.start()

            }
            finish()
        }
    }
}
