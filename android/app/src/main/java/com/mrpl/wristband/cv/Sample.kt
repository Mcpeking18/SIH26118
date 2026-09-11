package com.mrpl.wristband.cv

import com.mrpl.wristband.color.Colorimetry

data class Sample(
    val name: String,
    val meanLinear: DoubleArray,
    val medianLinear: DoubleArray,
    val stdLinear: DoubleArray,
    val nPixels: Int = 0,
    val nTotal: Int = 0,
    val clipFraction: Double = 0.0,
    val blackFraction: Double = 0.0
) {
    val luminance: Double
        get() = meanLinear[0] * Colorimetry.LUMA[0] +
                meanLinear[1] * Colorimetry.LUMA[1] +
                meanLinear[2] * Colorimetry.LUMA[2]

    val cvPercent: Double
        get() {
            val m = luminance
            if (m <= 1e-9) return Double.POSITIVE_INFINITY
            val stdLuma = stdLinear[0] * Colorimetry.LUMA[0] +
                          stdLinear[1] * Colorimetry.LUMA[1] +
                          stdLinear[2] * Colorimetry.LUMA[2]
            return 100.0 * stdLuma / m
        }
}

data class BadgeSamples(
    var pad: Sample? = null,
    val patches: MutableList<Sample> = mutableListOf(),
    val whiteField: MutableList<Sample> = mutableListOf(),
    val whiteFieldXy: MutableList<DoubleArray> = mutableListOf(),
    val warnings: MutableList<String> = mutableListOf(),
    var ok: Boolean = true
) {
    fun patch(name: String): Sample? {
        return patches.find { it.name == name }
    }
}
