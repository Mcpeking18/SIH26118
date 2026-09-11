package com.mrpl.wristband.config

import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.hypot

data class Patch(
    val name: String,
    val srgb: IntArray,
    val role: String,
    val note: String = ""
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as Patch
        if (name != other.name) return false
        if (!srgb.contentEquals(other.srgb)) return false
        if (role != other.role) return false
        return true
    }
    override fun hashCode(): Int {
        var result = name.hashCode()
        result = 31 * result + srgb.contentHashCode()
        result = 31 * result + role.hashCode()
        return result
    }
}

/**
 * Physical geometry and constants for the H2S dosimeter wristband.
 * This class is a direct Kotlin port of reference/python/engine/badge_spec.py.
 * It provides identical coordinate generation to guarantee that OpenCV sampling
 * exactly matches the golden Python reference.
 */
data class WristbandSpec(
    val headMm: Double = 30.0,
    val strapWidthMm: Double = 22.0,
    val strapLengthMm: Double = 240.0,
    val strapThicknessMm: Double = 3.5,

    val wellDiameterMm: Double = 12.0,
    val wellDepthMm: Double = 2.2,
    val padDiameterMm: Double = 10.0,
    val membraneDiameterMm: Double = 11.5,
    val scrubberDiameterMm: Double = 11.5,
    val padSubstrate: String = "silica / borosilicate glass-fibre (acid-stable)",

    val markerMm: Double = 4.5,
    val markerInsetMm: Double = 3.5,
    val markerQuietZoneMm: Double = 1.25,
    val arucoDict: String = "DICT_4X4_50",
    val markerIds: IntArray = intArrayOf(0, 1, 2, 3),

    val patchMm: Double = 2.2,
    val patchRingRadiusMm: Double = 8.6,
    val patchStartDeg: Double = -90.0,
    val nPatches: Int = 12,

    val padSampleFraction: Double = 0.75,
    val patchSampleFraction: Double = 0.70,

    val whiteProbeInnerMm: Double = 0.9,
    val whiteProbeOuterMm: Double = 2.0,
    val pxPerMm: Double = 20.0
) {
    val canonicalPx: Int
        get() = Math.round(headMm * pxPerMm).toInt()

    val centreMm: DoubleArray
        get() = doubleArrayOf(headMm / 2.0, headMm / 2.0)

    fun markerCentresMm(): Array<DoubleArray> {
        val lo = markerInsetMm
        val hi = headMm - markerInsetMm
        return arrayOf(
            doubleArrayOf(lo, lo),
            doubleArrayOf(hi, lo),
            doubleArrayOf(hi, hi),
            doubleArrayOf(lo, hi)
        )
    }

    fun markerOuterCornersMm(): Array<Array<DoubleArray>> {
        val h = markerMm / 2.0
        val centres = markerCentresMm()
        return Array(centres.size) { i ->
            val cx = centres[i][0]
            val cy = centres[i][1]
            arrayOf(
                doubleArrayOf(cx - h, cy - h),
                doubleArrayOf(cx + h, cy - h),
                doubleArrayOf(cx + h, cy + h),
                doubleArrayOf(cx - h, cy + h)
            )
        }
    }

    fun patchCentresMm(): Array<DoubleArray> {
        val (cx, cy) = centreMm
        val r = patchRingRadiusMm
        val step = 360.0 / nPatches
        return Array(nPatches) { i ->
            val th = Math.toRadians(patchStartDeg + i * step)
            doubleArrayOf(cx + r * cos(th), cy + r * sin(th))
        }
    }

    fun whiteFieldProbesMm(): Array<DoubleArray> {
        val (cx, cy) = centreMm
        val out = mutableListOf<DoubleArray>()
        
        val rIn = (wellDiameterMm / 2.0 + (patchRingRadiusMm - patchMm / 2.0)) / 2.0
        for (k in 0 until 8) {
            val th = Math.toRadians(patchStartDeg + 22.5 + k * 45.0)
            out.add(doubleArrayOf(cx + rIn * cos(th), cy + rIn * sin(th), whiteProbeInnerMm))
        }

        val rOut = headMm / 2.0 - whiteProbeOuterMm / 2.0 - 0.8
        val dx = intArrayOf(0, 1, 0, -1)
        val dy = intArrayOf(-1, 0, 1, 0)
        for (i in 0 until 4) {
            out.add(doubleArrayOf(cx + dx[i] * rOut, cy + dy[i] * rOut, whiteProbeOuterMm))
        }

        return out.toTypedArray()
    }

    fun mmToPx(ptsMm: Array<DoubleArray>): Array<DoubleArray> {
        return Array(ptsMm.size) { i ->
            DoubleArray(ptsMm[i].size) { j ->
                ptsMm[i][j] * pxPerMm
            }
        }
    }

    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as WristbandSpec
        return headMm == other.headMm // simplified equals for data class
    }

    override fun hashCode(): Int {
        return headMm.hashCode()
    }

    companion object {
        val BADGE = WristbandSpec()

        // SUBSTRATE_SRGB from Python
        val SUBSTRATE_SRGB = intArrayOf(232, 230, 226)

        val PATCHES = arrayOf(
            Patch("WHITE",       intArrayOf(243, 243, 242), "neutral",   "paper white, near D65"),
            Patch("CYAN",        intArrayOf(22, 163, 218),  "chroma",    "-a*, -b* axis"),
            Patch("SUBSTRATE_A", SUBSTRATE_SRGB, "substrate", "baseline, paired with SUBSTRATE_B"),
            Patch("MAGENTA",     intArrayOf(200, 24, 124),  "chroma",    "+a* axis"),
            Patch("GREY_50",     intArrayOf(119, 119, 119), "neutral",   "18% reflectance, L* ~ 50"),
            Patch("YELLOW",      intArrayOf(243, 214, 26),  "chroma",    "+b* axis, brightest chroma"),
            Patch("BLACK",       intArrayOf(35, 35, 35),    "neutral",   "printable black, not 0/0/0"),
            Patch("RED",         intArrayOf(196, 48, 43),   "chroma",    "+a*, +b* quadrant"),
            Patch("SUBSTRATE_B", SUBSTRATE_SRGB, "substrate", "baseline, opposite SUBSTRATE_A"),
            Patch("GREEN",       intArrayOf(60, 140, 78),   "chroma",    "-a*, +b* quadrant"),
            Patch("GREY_20",     intArrayOf(75, 75, 75),    "neutral",   "shadow tone"),
            Patch("BLUE",        intArrayOf(46, 62, 148),   "chroma",    "-b* axis")
        )

        /**
         * PROVISIONAL CONSTANTS: These LAB and SRGB values are mathematically deterministic 
         * outputs of Python's colorimetry.py (D65 whitepoint, gamma expansions). 
         * To guarantee exact equivalence while minimizing unnecessary cross-dependencies 
         * at this stage, they are hardcoded from a JSON dump of the Python reference engine.
         * When Colorimetry.kt is fully implemented, these can be re-calculated dynamically if needed.
         */
        val REFERENCE_LAB = arrayOf(
            doubleArrayOf(95.8167475513481, -0.17623349882350814, 0.4806251140541562),
            doubleArrayOf(62.86349751018284, -15.030732850105643, -37.466186024057514),
            doubleArrayOf(91.12305389504576, -3.980714054478862, -1.380188017347983),
            doubleArrayOf(44.78927309518522, 69.82064995280696, -9.594951915972615),
            doubleArrayOf(50.034440993686104, -9.48770639830343e-06, 3.795082559321372e-06),
            doubleArrayOf(85.61779301165993, -6.25252342818311, 82.82491328331378),
            doubleArrayOf(13.713784788853026, -4.269221670627488e-06, 1.707688668250995e-06),
            doubleArrayOf(44.27292806273366, 57.37316868174081, 39.0494857719704),
            doubleArrayOf(91.12305389504576, -3.980714054478862, -1.380188017347983),
            doubleArrayOf(52.13637471710075, -38.63882365964805, 25.898373978346555),
            doubleArrayOf(31.888747393429796, -6.880566671974009e-06, 2.7522266687896035e-06),
            doubleArrayOf(29.821116176000125, 23.36432759155066, -49.33517713160715)
        )

        val PAD_STAGE_SRGB = arrayOf(
            intArrayOf(220, 232, 232),
            intArrayOf(184, 184, 160),
            intArrayOf(122, 88, 50),
            intArrayOf(56, 35, 21),
            intArrayOf(13, 12, 12)
        )
    }
}
