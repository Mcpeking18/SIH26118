package com.mrpl.wristband.data

import android.graphics.Bitmap
import com.mrpl.wristband.cv.Detector
import com.mrpl.wristband.cv.Sampler
import com.mrpl.wristband.color.Normalizer
import com.mrpl.wristband.dosimetry.Dosimetry
import org.opencv.android.Utils
import org.opencv.core.Mat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Clean bridge between the UI layer and the scientific CV/dosimetry pipeline.
 * Keeps Activity/Fragment classes decoupled from OpenCV and matrix arithmetic.
 */
object DosimetryBridge {

    private val detector by lazy { Detector() }

    /**
     * Executes the CV & Dosimetry pipeline on a captured or uploaded Bitmap.
     * If OpenCV detection fails or image is not a dosimeter wristband, returns
     * either an error or falls back to demo data for UI presentation.
     */
    fun processBitmap(
        bitmap: Bitmap?,
        wristbandIdHint: String = "H2S-G4-9982"
    ): ScanUiResult {
        val now = SimpleDateFormat("dd MMM yyyy - HH:mm:ss", Locale.US).format(Date())

        if (bitmap == null) {
            return MockDataProvider.defaultScanResult.copy(
                wristbandId = wristbandIdHint,
                timestamp = now,
                isMock = true
            )
        }

        try {
            val mat = Mat()
            Utils.bitmapToMat(bitmap, mat)
            // Detector.rectify() is the correct API entry point (not detect())
            val detection = detector.rectify(mat)

            if (detection.ok && detection.warped != null) {
                val badgeSamples = Sampler.sampleBadge(detection.warped)
                
                // Normalizer
                                val normalizedResult = Normalizer.normalizeBadge(badgeSamples)
                if (normalizedResult.padLab == null) {
                    return MockDataProvider.defaultScanResult.copy(
                        wristbandId = wristbandIdHint,
                        timestamp = now,
                        verdict = "SCAN FAILED: Color Normalization Failed",
                        isMock = true
                    )
                }

                // Dosimetry
                val deltaL = normalizedResult.deltaLStar
                val dResult = Dosimetry.assessScan(
                    observable = deltaL,
                    shiftHours = 8.0,
                    deltaE00 = normalizedResult.deltaE00,
                    deltaLStar = normalizedResult.deltaLStar
                )

                return ScanUiResult(
                    wristbandId = wristbandIdHint,
                    refinery = "ABC Refinery",
                    unit = "Hydrodesulfurization Unit",
                    zone = "HDS-04",
                    timestamp = now,
                    peakIntensityPpm = dResult.dosePpmHr,
                    cumulativeConcentrationPpm = dResult.dosePpmHr,
                    dosePpmHr = dResult.dosePpmHr,
                    twaPpm = dResult.twaPpm,
                    darkeningPercent = deltaL * 100,
                    e0 = dResult.deltaE00,
                    verdict = dResult.verdict.name,
                    level = if(dResult.verdict.name == "SAFE" || dResult.verdict.name == "NORMAL") "LOW" else "CRITICAL",
                    lastCloudSync = now,
                    isMock = false
                )
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // Fallback demo result for testing and simulation
        return MockDataProvider.defaultScanResult.copy(
            wristbandId = wristbandIdHint,
            timestamp = now,
            isMock = true
        )
    }

    /**
     * Direct simulator method for demo scanning
     */
    fun getSimulatedResult(wristbandId: String = "H2S-G4-9982"): ScanUiResult {
        val now = SimpleDateFormat("dd MMM yyyy - HH:mm:ss", Locale.US).format(Date())
        return MockDataProvider.defaultScanResult.copy(
            wristbandId = wristbandId,
            timestamp = now,
            isMock = true
        )
    }
}
