package com.mrpl.wristband.cv

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mrpl.wristband.config.WristbandSpec
import com.mrpl.wristband.color.Colorimetry
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.opencv.android.OpenCVLoader
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Point
import org.opencv.core.Scalar
import org.opencv.imgproc.Imgproc
import kotlin.math.abs
import kotlin.math.roundToInt

@RunWith(AndroidJUnit4::class)
class SamplerTest {

    @Before
    fun setUp() {
        assertTrue("OpenCV failed to load!", OpenCVLoader.initLocal())
    }

    @Test
    fun testSamplerExtractsLinearRGB() {
        val spec = WristbandSpec.BADGE
        val n = spec.canonicalPx
        val frame = Mat(n, n, CvType.CV_8UC3, Scalar(255.0, 255.0, 255.0)) // White frame

        // Fill pad with a specific color: e.g., R=100, G=150, B=200
        val centrePx = spec.mmToPx(arrayOf(spec.centreMm))[0]
        val padRPx = spec.mmToPx(arrayOf(doubleArrayOf(spec.padDiameterMm / 2.0)))[0][0]
        Imgproc.circle(
            frame,
            Point(centrePx[0], centrePx[1]),
            padRPx.roundToInt(),
            Scalar(200.0, 150.0, 100.0), // BGR
            -1
        )

        // Draw the grey ramp so the monotonicity check passes perfectly
        // Patch indices: 4 (GREY_50), 10 (GREY_20), 6 (BLACK)
        // Values in sRGB:
        // GREY_50: 119, 119, 119
        // GREY_20: 75, 75, 75
        // BLACK: 35, 35, 35
        val patchCentres = spec.mmToPx(spec.patchCentresMm())
        val sidePx = spec.mmToPx(arrayOf(doubleArrayOf(spec.patchMm)))[0][0]
        val h = sidePx / 2.0
        
        fun drawPatch(idx: Int, r: Double, g: Double, b: Double) {
            val c = patchCentres[idx]
            Imgproc.rectangle(
                frame,
                Point(c[0] - h, c[1] - h),
                Point(c[0] + h, c[1] + h),
                Scalar(b, g, r),
                -1
            )
        }

        drawPatch(4, 119.0, 119.0, 119.0)
        drawPatch(10, 75.0, 75.0, 75.0)
        drawPatch(6, 35.0, 35.0, 35.0)

        // Run sampler
        val samples = Sampler.sampleBadge(frame, spec)
        
        // Assertions
        assertTrue(samples.warnings.joinToString(", "), samples.ok)
        
        // Pad checks
        assertNotNull(samples.pad)
        val pad = samples.pad!!
        
        // Expected linear conversion for (100, 150, 200)
        val expectedLinearPad = Colorimetry.srgbToLinear(doubleArrayOf(100.0, 150.0, 200.0))
        
        assertEquals(expectedLinearPad[0], pad.meanLinear[0], 0.005)
        assertEquals(expectedLinearPad[1], pad.meanLinear[1], 0.005)
        assertEquals(expectedLinearPad[2], pad.meanLinear[2], 0.005)

        // Grey ramp checks
        val p50 = samples.patch("GREY_50")!!
        val p20 = samples.patch("GREY_20")!!
        val pBlack = samples.patch("BLACK")!!
        
        assertTrue("Monotonicity check failed", p50.luminance > p20.luminance)
        assertTrue("Monotonicity check failed", p20.luminance > pBlack.luminance)
        
        // Verify clip fraction for white field is very high
        val w0 = samples.whiteField[0]
        assertEquals(1.0, w0.clipFraction, 0.05)
    }
}
