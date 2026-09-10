package com.mrpl.wristband.color

import kotlin.math.pow

object Colorimetry {
    // Rec.709 luminance weights, applied to LINEAR RGB
    val LUMA = doubleArrayOf(0.2126, 0.7152, 0.0722)

    /**
     * Converts sRGB to linear-light RGB in 0..1.
     * Uses the exact piecewise sRGB EOTF, not a plain 2.2 gamma, because the linear toe matters.
     * @param rgb Encoded sRGB values (e.g. 0..255).
     * @param maxValue Full-scale encoding. Use 255.0 for 8-bit camera data.
     * @return Linear-light RGB array in 0..1.
     */
    fun srgbToLinear(rgb: DoubleArray, maxValue: Double = 255.0): DoubleArray {
        val out = DoubleArray(rgb.size)
        for (i in rgb.indices) {
            var a = rgb[i] / maxValue
            if (a < 0.0) a = 0.0
            if (a > 1.0) a = 1.0
            out[i] = if (a <= 0.04045) {
                a / 12.92
            } else {
                ((a + 0.055) / 1.055).pow(2.4)
            }
        }
        return out
    }
}
