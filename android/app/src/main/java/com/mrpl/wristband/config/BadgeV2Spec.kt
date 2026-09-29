package com.mrpl.wristband.config

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

data class BadgeV2Spec(
    val widthMm: Double = 40.0,
    val heightMm: Double = 30.0,
    val pxPerMm: Double = 20.0,
    val fiducialSizeMm: Double = 6.0,
    val fiducialInsetMm: Double = 4.0
) {
    val widthPx: Int get() = (widthMm * pxPerMm).toInt()
    val heightPx: Int get() = (heightMm * pxPerMm).toInt()

    val markerIds: IntArray = intArrayOf(0, 1, 2, 3)

    fun markerCentresMm(): Array<DoubleArray> {
        val insetX = fiducialInsetMm
        val insetY = fiducialInsetMm
        return arrayOf(
            doubleArrayOf(insetX, insetY), // TL (0)
            doubleArrayOf(widthMm - insetX, insetY), // TR (1)
            doubleArrayOf(widthMm - insetX, heightMm - insetY), // BR (2)
            doubleArrayOf(insetX, heightMm - insetY) // BL (3)
        )
    }

    fun markerOuterCornersMm(): Array<Array<DoubleArray>> {
        val h = fiducialSizeMm / 2.0
        val centres = markerCentresMm()
        return Array(centres.size) { i ->
            val cx = centres[i][0]
            val cy = centres[i][1]
            arrayOf(
                doubleArrayOf(cx - h, cy - h), // TL
                doubleArrayOf(cx + h, cy - h), // TR
                doubleArrayOf(cx + h, cy + h), // BR
                doubleArrayOf(cx - h, cy + h)  // BL
            )
        }
    }

    // 4 cols x 3 rows. Swatches ~ 8 x 4.5 mm
    fun patchRectsMm(): Array<Array<Double>> {
        val cols = 4
        val rows = 3
        val w = 8.0
        val h = 4.5
        val startX = (widthMm - (cols * w)) / 2.0
        val startY = 8.0
        val rects = mutableListOf<Array<Double>>()
        for (r in 0 until rows) {
            for (c in 0 until cols) {
                rects.add(arrayOf(startX + c * w, startY + r * h, w, h))
            }
        }
        return rects.toTypedArray()
    }

    fun patchCentresMm(): Array<DoubleArray> {
        val rects = patchRectsMm()
        return Array(rects.size) { i ->
            val r = rects[i]
            doubleArrayOf(r[0] + r[2]/2.0, r[1] + r[3]/2.0)
        }
    }

    // Sensing region in bottom center
    fun sensingRegionMm(): Array<Double> {
        val w = 12.0
        val h = 6.0
        val cx = widthMm / 2.0
        val cy = heightMm - fiducialInsetMm - h/2.0
        return arrayOf(cx - w/2.0, cy - h/2.0, w, h)
    }

    fun mmToPx(ptsMm: Array<DoubleArray>): Array<DoubleArray> {
        return Array(ptsMm.size) { i ->
            DoubleArray(ptsMm[i].size) { j -> ptsMm[i][j] * pxPerMm }
        }
    }

    companion object {
        val BADGE = BadgeV2Spec()
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
