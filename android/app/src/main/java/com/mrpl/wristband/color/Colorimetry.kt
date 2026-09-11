package com.mrpl.wristband.color

import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import kotlin.math.*

object Colorimetry {
    // Rec.709 luminance weights, applied to LINEAR RGB
    val LUMA = doubleArrayOf(0.2126, 0.7152, 0.0722)

    val SRGB_TO_XYZ = arrayOf(
        doubleArrayOf(0.4124564, 0.3575761, 0.1804375),
        doubleArrayOf(0.2126729, 0.7151522, 0.0721750),
        doubleArrayOf(0.0193339, 0.1191920, 0.9503041)
    )

    val D65_WHITE_XYZ = doubleArrayOf(95.047, 100.0, 108.883)
    const val LAB_EPS = 0.008856451679035631
    const val LAB_KAPPA = 903.2962962962963
    const val POW25_7 = 6103515625.0

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

    fun linearRgbToXyz(linear: DoubleArray): DoubleArray {
        val x = linear[0] * SRGB_TO_XYZ[0][0] + linear[1] * SRGB_TO_XYZ[0][1] + linear[2] * SRGB_TO_XYZ[0][2]
        val y = linear[0] * SRGB_TO_XYZ[1][0] + linear[1] * SRGB_TO_XYZ[1][1] + linear[2] * SRGB_TO_XYZ[1][2]
        val z = linear[0] * SRGB_TO_XYZ[2][0] + linear[1] * SRGB_TO_XYZ[2][1] + linear[2] * SRGB_TO_XYZ[2][2]
        return doubleArrayOf(x * 100.0, y * 100.0, z * 100.0)
    }

    fun xyzToLab(xyz: DoubleArray, white: DoubleArray = D65_WHITE_XYZ): DoubleArray {
        val r0 = xyz[0] / white[0]
        val r1 = xyz[1] / white[1]
        val r2 = xyz[2] / white[2]

        val f0 = if (r0 > LAB_EPS) max(r0, 0.0).pow(1.0 / 3.0) else (LAB_KAPPA * r0 + 16.0) / 116.0
        val f1 = if (r1 > LAB_EPS) max(r1, 0.0).pow(1.0 / 3.0) else (LAB_KAPPA * r1 + 16.0) / 116.0
        val f2 = if (r2 > LAB_EPS) max(r2, 0.0).pow(1.0 / 3.0) else (LAB_KAPPA * r2 + 16.0) / 116.0

        return doubleArrayOf(
            116.0 * f1 - 16.0,
            500.0 * (f0 - f1),
            200.0 * (f1 - f2)
        )
    }

    fun deltaECIEDE2000(lab1: DoubleArray, lab2: DoubleArray, kL: Double = 1.0, kC: Double = 1.0, kH: Double = 1.0): Double {
        val L1 = lab1[0]; val a1 = lab1[1]; val b1 = lab1[2]
        val L2 = lab2[0]; val a2 = lab2[1]; val b2 = lab2[2]

        val C1 = hypot(a1, b1)
        val C2 = hypot(a2, b2)
        val C_bar = 0.5 * (C1 + C2)
        val C_bar7 = C_bar.pow(7)
        val G = 0.5 * (1.0 - sqrt(C_bar7 / (C_bar7 + POW25_7)))

        val a1p = (1.0 + G) * a1
        val a2p = (1.0 + G) * a2
        val C1p = hypot(a1p, b1)
        val C2p = hypot(a2p, b2)

        var h1p = Math.toDegrees(atan2(b1, a1p)) % 360.0
        if (h1p < 0) h1p += 360.0
        var h2p = Math.toDegrees(atan2(b2, a2p)) % 360.0
        if (h2p < 0) h2p += 360.0
        
        if (C1p == 0.0) h1p = 0.0
        if (C2p == 0.0) h2p = 0.0

        val chroma_product_zero = (C1p * C2p) == 0.0

        val dLp = L2 - L1
        val dCp = C2p - C1p

        val dh = h2p - h1p
        val dhp = if (chroma_product_zero) 0.0 else {
            if (abs(dh) <= 180.0) dh
            else if (dh > 180.0) dh - 360.0
            else dh + 360.0
        }
        val dHp = 2.0 * sqrt(C1p * C2p) * sin(Math.toRadians(dhp) / 2.0)

        val L_bar = 0.5 * (L1 + L2)
        val C_barp = 0.5 * (C1p + C2p)

        val h_sum = h1p + h2p
        val h_absdiff = abs(h1p - h2p)
        val h_barp = if (chroma_product_zero) {
            h_sum
        } else {
            if (h_absdiff <= 180.0) 0.5 * h_sum
            else if (h_sum < 360.0) 0.5 * (h_sum + 360.0)
            else 0.5 * (h_sum - 360.0)
        }

        val T = 1.0 - 0.17 * cos(Math.toRadians(h_barp - 30.0)) +
                0.24 * cos(Math.toRadians(2.0 * h_barp)) +
                0.32 * cos(Math.toRadians(3.0 * h_barp + 6.0)) -
                0.20 * cos(Math.toRadians(4.0 * h_barp - 63.0))

        val dL50 = L_bar - 50.0
        val S_L = 1.0 + (0.015 * dL50 * dL50) / sqrt(20.0 + dL50 * dL50)
        val S_C = 1.0 + 0.045 * C_barp
        val S_H = 1.0 + 0.015 * C_barp * T

        val d_theta = 30.0 * exp(-(((h_barp - 275.0) / 25.0).pow(2)))
        val C_barp7 = C_barp.pow(7)
        val R_C = 2.0 * sqrt(C_barp7 / (C_barp7 + POW25_7))
        val R_T = -sin(Math.toRadians(2.0 * d_theta)) * R_C

        val tL = dLp / (kL * S_L)
        val tC = dCp / (kC * S_C)
        val tH = dHp / (kH * S_H)

        return sqrt(max(tL * tL + tC * tC + tH * tH + R_T * tC * tH, 0.0))
    }

    fun channelBalance(linearRgb: DoubleArray): Double {
        val y = linearRgb[0] * LUMA[0] + linearRgb[1] * LUMA[1] + linearRgb[2] * LUMA[2]
        if (y <= 0.0) return 1.0
        val norm = doubleArrayOf(linearRgb[0]/y, linearRgb[1]/y, linearRgb[2]/y)
        var maxDiff = 0.0
        for (i in 0..2) {
            for (j in i+1..2) {
                val d = abs(norm[i] - norm[j])
                if (d > maxDiff) maxDiff = d
            }
        }
        return max(1.0 - 0.5 * maxDiff, 0.0)
    }

    fun vonKriesGain(obsLinear: Array<DoubleArray>, refLinear: Array<DoubleArray>, eps: Double = 1e-6): DoubleArray {
        var obsR = 0.0; var obsG = 0.0; var obsB = 0.0
        var refR = 0.0; var refG = 0.0; var refB = 0.0
        val n = obsLinear.size
        for (i in 0 until n) {
            obsR += obsLinear[i][0]
            obsG += obsLinear[i][1]
            obsB += obsLinear[i][2]
            refR += refLinear[i][0]
            refG += refLinear[i][1]
            refB += refLinear[i][2]
        }
        return doubleArrayOf(
            (refR / n) / max(obsR / n, eps),
            (refG / n) / max(obsG / n, eps),
            (refB / n) / max(obsB / n, eps)
        )
    }

    fun ccmFeatureMatrix(linear: Array<DoubleArray>, mode: String = "root6"): Mat {
        val n = linear.size
        val cols = when (mode) {
            "linear" -> 3
            "affine" -> 4
            "root6" -> 6
            else -> throw IllegalArgumentException("Unknown CCM mode $mode")
        }
        val f = Mat(n, cols, CvType.CV_64F)
        for (i in 0 until n) {
            val r = linear[i][0]
            val g = linear[i][1]
            val b = linear[i][2]
            f.put(i, 0, r)
            f.put(i, 1, g)
            f.put(i, 2, b)
            if (mode == "affine") {
                f.put(i, 3, 1.0)
            } else if (mode == "root6") {
                f.put(i, 3, sqrt(max(r * g, 0.0)))
                f.put(i, 4, sqrt(max(g * b, 0.0)))
                f.put(i, 5, sqrt(max(r * b, 0.0)))
            }
        }
        return f
    }

    fun solveCcm(obsLinear: Array<DoubleArray>, refLinear: Array<DoubleArray>, mode: String = "root6", ridge: Double = 1e-4): Mat {
        val f = ccmFeatureMatrix(obsLinear, mode)
        val y = Mat(refLinear.size, 3, CvType.CV_64F)
        for (i in refLinear.indices) {
            y.put(i, 0, refLinear[i][0])
            y.put(i, 1, refLinear[i][1])
            y.put(i, 2, refLinear[i][2])
        }

        if (f.rows() != y.rows()) throw IllegalArgumentException("Patch count mismatch")
        if (f.rows() < f.cols()) throw IllegalArgumentException("CCM mode $mode needs >= ${f.cols()} patches")

        val ft = Mat()
        Core.transpose(f, ft)
        
        val ftf = Mat()
        Core.gemm(ft, f, 1.0, Mat(), 0.0, ftf)
        val I = Mat.eye(f.cols(), f.cols(), CvType.CV_64F)
        val ridgeI = Mat()
        Core.multiply(I, org.opencv.core.Scalar(ridge), ridgeI)
        val a = Mat()
        Core.add(ftf, ridgeI, a)

        val b = Mat()
        Core.gemm(ft, y, 1.0, Mat(), 0.0, b)

        val m = Mat()
        Core.solve(a, b, m, Core.DECOMP_CHOLESKY)
        
        ft.release()
        ftf.release()
        I.release()
        ridgeI.release()
        a.release()
        b.release()
        f.release()
        y.release()

        return m
    }

    fun applyCcm(linearRgb: Array<DoubleArray>, m: Mat, mode: String = "root6"): Array<DoubleArray> {
        val f = ccmFeatureMatrix(linearRgb, mode)
        val outMat = Mat()
        Core.gemm(f, m, 1.0, Mat(), 0.0, outMat)
        
        val out = Array(linearRgb.size) { DoubleArray(3) }
        val row = DoubleArray(m.cols())
        for (i in 0 until outMat.rows()) {
            outMat.get(i, 0, row)
            out[i][0] = row[0]
            out[i][1] = row[1]
            out[i][2] = row[2]
        }
        f.release()
        outMat.release()
        return out
    }
}
