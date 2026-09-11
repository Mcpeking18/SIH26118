package com.mrpl.wristband.cv

import com.mrpl.wristband.color.Colorimetry
import com.mrpl.wristband.config.WristbandSpec
import org.opencv.core.Mat
import org.opencv.core.Point
import org.opencv.imgproc.Imgproc
import kotlin.math.max
import kotlin.math.roundToInt
import kotlin.math.sqrt

object Sampler {

    fun discMask(size: Int, centrePx: DoubleArray, radiusPx: Double): Mat {
        val m = Mat.zeros(size, size, org.opencv.core.CvType.CV_8UC1)
        Imgproc.circle(
            m,
            Point(centrePx[0].roundToInt().toDouble(), centrePx[1].roundToInt().toDouble()),
            max(1, radiusPx.roundToInt()),
            org.opencv.core.Scalar(255.0),
            -1
        )
        return m
    }

    fun squareMask(size: Int, centrePx: DoubleArray, sidePx: Double): Mat {
        val m = Mat.zeros(size, size, org.opencv.core.CvType.CV_8UC1)
        val h = sidePx / 2.0
        val x0 = (centrePx[0] - h).roundToInt()
        val y0 = (centrePx[1] - h).roundToInt()
        val x1 = (centrePx[0] + h).roundToInt()
        val y1 = (centrePx[1] + h).roundToInt()
        Imgproc.rectangle(
            m,
            Point(x0.toDouble(), y0.toDouble()),
            Point(x1.toDouble(), y1.toDouble()),
            org.opencv.core.Scalar(255.0),
            -1
        )
        return m
    }

    private fun quantile(sorted: DoubleArray, q: Double): Double {
        if (sorted.isEmpty()) return 0.0
        if (sorted.size == 1) return sorted[0]
        val pos = q * (sorted.size - 1)
        val i = pos.toInt()
        val g = pos - i
        if (i >= sorted.size - 1) return sorted.last()
        return sorted[i] + g * (sorted[i + 1] - sorted[i])
    }

    private fun median(sorted: DoubleArray): Double {
        val n = sorted.size
        if (n == 0) return 0.0
        return if (n % 2 == 0) {
            (sorted[n / 2 - 1] + sorted[n / 2]) / 2.0
        } else {
            sorted[n / 2]
        }
    }

    private fun std(arr: DoubleArray, mean: Double): Double {
        if (arr.isEmpty()) return 0.0
        var sumSq = 0.0
        for (v in arr) {
            val d = v - mean
            sumSq += d * d
        }
        return sqrt(sumSq / arr.size)
    }

    fun sampleRegion(
        warpedBgr: Mat,
        mask: Mat,
        name: String = "",
        trim: Double = 0.20,
        clipThreshold: Int = 254,
        blackThreshold: Int = 2
    ): Sample {
        val h = warpedBgr.rows()
        val w = warpedBgr.cols()
        
        // Fast pixel extraction
        val imgArray = ByteArray(h * w * warpedBgr.channels())
        val maskArray = ByteArray(h * w)
        warpedBgr.get(0, 0, imgArray)
        mask.get(0, 0, maskArray)

        val pixels = mutableListOf<DoubleArray>()
        var clipCount = 0
        var blackCount = 0

        for (i in 0 until h * w) {
            if (maskArray[i].toInt() != 0) {
                val b = imgArray[i * 3].toInt() and 0xFF
                val g = imgArray[i * 3 + 1].toInt() and 0xFF
                val r = imgArray[i * 3 + 2].toInt() and 0xFF
                
                if (r >= clipThreshold || g >= clipThreshold || b >= clipThreshold) clipCount++
                if (r <= blackThreshold && g <= blackThreshold && b <= blackThreshold) blackCount++
                
                pixels.add(doubleArrayOf(r.toDouble(), g.toDouble(), b.toDouble()))
            }
        }

        val nTotal = pixels.size
        if (nTotal == 0) {
            val z = DoubleArray(3)
            return Sample(name, z.clone(), z.clone(), z.clone(), 0, 0, 0.0, 0.0)
        }

        val clipFraction = clipCount.toDouble() / nTotal
        val blackFraction = blackCount.toDouble() / nTotal

        val linearPixels = Array(nTotal) { i ->
            Colorimetry.srgbToLinear(pixels[i])
        }

        val lumas = DoubleArray(nTotal)
        for (i in 0 until nTotal) {
            val p = linearPixels[i]
            lumas[i] = p[0] * Colorimetry.LUMA[0] + p[1] * Colorimetry.LUMA[1] + p[2] * Colorimetry.LUMA[2]
        }

        var keepIndices = IntArray(nTotal) { it }
        if (trim > 0.0 && trim < 0.5 && nTotal >= 20) {
            val sortedLumas = lumas.clone()
            sortedLumas.sort()
            val lo = quantile(sortedLumas, trim)
            val hi = quantile(sortedLumas, 1.0 - trim)
            
            val kept = mutableListOf<Int>()
            for (i in 0 until nTotal) {
                if (lumas[i] in lo..hi) {
                    kept.add(i)
                }
            }
            if (kept.size >= 5) {
                keepIndices = kept.toIntArray()
            }
        }

        val nKept = keepIndices.size
        val rKept = DoubleArray(nKept)
        val gKept = DoubleArray(nKept)
        val bKept = DoubleArray(nKept)

        for (i in 0 until nKept) {
            val p = linearPixels[keepIndices[i]]
            rKept[i] = p[0]
            gKept[i] = p[1]
            bKept[i] = p[2]
        }

        val meanLinear = doubleArrayOf(rKept.average(), gKept.average(), bKept.average())
        
        rKept.sort()
        gKept.sort()
        bKept.sort()
        val medianLinear = doubleArrayOf(median(rKept), median(gKept), median(bKept))
        val stdLinear = doubleArrayOf(std(rKept, meanLinear[0]), std(gKept, meanLinear[1]), std(bKept, meanLinear[2]))

        return Sample(
            name = name,
            meanLinear = meanLinear,
            medianLinear = medianLinear,
            stdLinear = stdLinear,
            nPixels = nKept,
            nTotal = nTotal,
            clipFraction = clipFraction,
            blackFraction = blackFraction
        )
    }

    fun sampleBadge(
        warpedBgr: Mat,
        spec: WristbandSpec = WristbandSpec.BADGE,
        trim: Double = 0.20,
        maxClipFraction: Double = 0.15,
        maxPadCvPercent: Double = 25.0
    ): BadgeSamples {
        val n = spec.canonicalPx
        require(warpedBgr.rows() == n && warpedBgr.cols() == n) {
            "expected a ${n}x${n} rectified image, got ${warpedBgr.rows()}x${warpedBgr.cols()}"
        }

        val out = BadgeSamples()
        val centrePx = spec.mmToPx(arrayOf(spec.centreMm))[0]
        val padRPx = spec.mmToPx(arrayOf(doubleArrayOf(spec.padDiameterMm / 2.0)))[0][0] * spec.padSampleFraction
        out.pad = sampleRegion(warpedBgr, discMask(n, centrePx, padRPx), "PAD", trim)

        val patchSide = spec.mmToPx(arrayOf(doubleArrayOf(spec.patchMm)))[0][0] * spec.patchSampleFraction
        val patchNames = WristbandSpec.PATCHES.map { it.name }
        val patchCentres = spec.mmToPx(spec.patchCentresMm())
        
        for (i in patchNames.indices) {
            val m = squareMask(n, patchCentres[i], patchSide)
            out.patches.add(sampleRegion(warpedBgr, m, patchNames[i], trim))
        }

        val whiteProbes = spec.whiteFieldProbesMm()
        for (i in whiteProbes.indices) {
            val p = whiteProbes[i]
            val rPx = spec.mmToPx(arrayOf(doubleArrayOf(p[2] / 2.0)))[0][0] * 0.85
            val cPx = spec.mmToPx(arrayOf(doubleArrayOf(p[0], p[1])))[0]
            val m = discMask(n, cPx, rPx)
            out.whiteField.add(sampleRegion(warpedBgr, m, "W$i", 0.30))
            out.whiteFieldXy.add(doubleArrayOf(p[0], p[1]))
        }

        val pad = out.pad!!
        if (pad.clipFraction > maxClipFraction) {
            out.warnings.add("pad glare: ${pad.clipFraction * 100}% of pixels clipped - tilt away from light source")
        }
        if (pad.blackFraction > 0.5) {
            out.warnings.add("pad underexposed: ${pad.blackFraction * 100}% of pixels crushed to black")
        }
        if (pad.cvPercent > maxPadCvPercent) {
            out.warnings.add("pad non-uniform: CV ${pad.cvPercent}% - shadow, smear or lifted membrane")
        }

        val badPatches = out.patches.filter { it.clipFraction > maxClipFraction }.map { it.name }
        if (badPatches.isNotEmpty()) {
            out.warnings.add("reference patches clipped: ${badPatches.joinToString(", ")} - colour correction will be unreliable")
        }

        val neutralIndices = intArrayOf(4, 10, 6) // GREY_50, GREY_20, BLACK
        // In python: ramp = sorted(NEUTRAL_INDICES, key=lambda i: -luma)
        val sortedRamp = neutralIndices.sortedByDescending { idx ->
            val srgb = WristbandSpec.PATCHES[idx].srgb.map { it.toDouble() }.toDoubleArray()
            val linear = Colorimetry.srgbToLinear(srgb)
            linear[0] * Colorimetry.LUMA[0] + linear[1] * Colorimetry.LUMA[1] + linear[2] * Colorimetry.LUMA[2]
        }

        val lum = sortedRamp.map { out.patches[it].luminance }
        var monotonic = true
        for (i in 0 until lum.size - 1) {
            if (lum[i] < lum[i + 1] - 0.015) {
                monotonic = false
                break
            }
        }
        if (lum.size >= 3 && !monotonic) {
            out.warnings.add("printed grey ramp is not monotonic - possible rectification noise")
            if (lum[0] < lum.last()) {
                out.ok = false
            }
        }

        return out
    }
}
