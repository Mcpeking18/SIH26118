package com.mrpl.wristband.data

import android.graphics.Bitmap
import com.mrpl.wristband.cv.Detector
import com.mrpl.wristband.cv.Sampler
import com.mrpl.wristband.color.Normalizer
import com.mrpl.wristband.dosimetry.Dosimetry
import org.opencv.android.Utils
import org.opencv.core.Mat
import org.opencv.imgproc.Imgproc
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
            val rgbaMat = Mat()
            Utils.bitmapToMat(bitmap, rgbaMat)
            val mat = Mat()
            org.opencv.imgproc.Imgproc.cvtColor(rgbaMat, mat, org.opencv.imgproc.Imgproc.COLOR_RGBA2BGR)
            rgbaMat.release()
            // Detector.rectify() is the correct API entry point (not detect())
            val detection = detector.rectify(mat)

            if (detection.ok && detection.warped != null) {
                val badgeSamples = Sampler.sampleBadge(detection.warped)
                
                // Normalizer
                                val normalizedResult = Normalizer.normalizeBadge(badgeSamples)
                
                android.util.Log.d("H2S_AUDIT", "--- CAMERA/COLOR PIPELINE AUDIT ---")
                android.util.Log.d("H2S_AUDIT", "Warped Mat size: ${detection.warped?.cols()}x${detection.warped?.rows()}")
                                android.util.Log.d("H2S_AUDIT", "Pad Corrected (RGB): ${normalizedResult.padLinear?.contentToString()}")
                android.util.Log.d("H2S_AUDIT", "Pad Lab: ${normalizedResult.padLab?.contentToString()}")
                android.util.Log.d("H2S_AUDIT", "Baseline Lab: ${normalizedResult.baselineLab?.contentToString()}")
                android.util.Log.d("H2S_AUDIT", "CCM Mode used: ${normalizedResult.mode}")
                android.util.Log.d("H2S_AUDIT", "Delta L*: ${normalizedResult.deltaLStar}")
                android.util.Log.d("H2S_AUDIT", "Delta E00: ${normalizedResult.deltaE00}")
                
                if (normalizedResult.padLab == null) {
                    return ScanUiResult(
                        wristbandId = wristbandIdHint,
                        timestamp = now,
                        isMock = false,
                        scanState = ScanState.POOR_IMAGE_QUALITY,
                        errorMessage = "Color normalization failed (Glare/Shadow)"
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

                val debugStr = """
                    CCM: ${normalizedResult.mode}
                    Pad RGB: ${normalizedResult.padLinear?.map { "%.3f".format(it) }?.joinToString()}
                    Pad Lab: ${normalizedResult.padLab?.map { "%.2f".format(it) }?.joinToString()}
                    Base Lab: ${normalizedResult.baselineLab?.map { "%.2f".format(it) }?.joinToString()}
                """.trimIndent()

                return ScanUiResult(
                    wristbandId = wristbandIdHint,
                    refinery = null,
                    unit = null,
                    zone = null,
                    timestamp = now,
                    peakIntensityPpm = null,
                    cumulativeConcentrationPpm = null,
                    dosePpmHr = dResult.dosePpmHr,
                    twaPpm = dResult.twaPpm,
                    deltaLStar = normalizedResult.deltaLStar,
                    deltaE00 = normalizedResult.deltaE00,
                    verdict = dResult.verdict.name,
                    level = null,
                    lastCloudSync = null,
                    isMock = false,
                    debugInfo = debugStr
                )
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }

        // Fallback demo result for testing and simulation
        return ScanUiResult(
            wristbandId = wristbandIdHint,
            timestamp = now,
            isMock = false,
            scanState = ScanState.PROCESSING_ERROR,
            errorMessage = "Invalid Image or Lighting"
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
