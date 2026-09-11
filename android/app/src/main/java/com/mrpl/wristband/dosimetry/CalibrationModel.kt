package com.mrpl.wristband.dosimetry

import kotlin.math.max
import kotlin.math.pow
import kotlin.math.abs

open class CalibrationModel(
    val observable: String = "delta_l",
    val coeffs: DoubleArray = doubleArrayOf(),
    val obsMin: Double = 0.0,
    val obsMax: Double = Double.POSITIVE_INFINITY,
    val obsSaturation: Double = Double.POSITIVE_INFINITY,
    val obsNoiseFloor: Double = 1.0,
    val tempCoeffPerC: Double = 0.0035,
    val rhCoeffPerFraction: Double = 0.12,
    val refTempC: Double = 25.0,
    val refRhFraction: Double = 0.50,
    val rSquared: Double? = null,
    val relErrorRmsPercent: Double? = null,
    val relErrorMaxPercent: Double? = null,
    val nCalibrationPoints: Int? = null,
    val notes: String = "uninitialised - fit with cli/fit_calibration.py"
) {
    fun environmentFactor(tempC: Double?, rhFraction: Double?): Double {
        val t = tempC ?: refTempC
        val rh = rhFraction ?: refRhFraction
        val f = (1.0 + tempCoeffPerC * (t - refTempC)) * (1.0 + rhCoeffPerFraction * (rh - refRhFraction))
        return f.coerceIn(0.5, 2.0)
    }

    protected open fun rawDose(value: Double): Double {
        if (coeffs.isEmpty()) {
            throw IllegalArgumentException("CalibrationModel has no coefficients.")
        }
        var res = 0.0
        val deg = coeffs.size - 1
        for (i in coeffs.indices) {
            res += coeffs[i] * value.pow(deg - i)
        }
        return res
    }

    fun dose(value: Double, tempC: Double? = null, rhFraction: Double? = null): Double {
        val raw = rawDose(value)
        val d = raw / environmentFactor(tempC, rhFraction)
        return max(d, 0.0)
    }
}

val SATURATION_EPS = 1e-3

class SaturationCalibration(
    observable: String = "delta_l",
    val k: Double = 1.0,
    val m: Double = 1.0,
    val lMax: Double = 78.2,
    obsMin: Double = 0.0,
    obsMax: Double = Double.POSITIVE_INFINITY,
    obsSaturation: Double = Double.POSITIVE_INFINITY,
    obsNoiseFloor: Double = 1.0,
    tempCoeffPerC: Double = 0.0035,
    rhCoeffPerFraction: Double = 0.12,
    refTempC: Double = 25.0,
    refRhFraction: Double = 0.50,
    rSquared: Double? = null,
    relErrorRmsPercent: Double? = null,
    relErrorMaxPercent: Double? = null,
    nCalibrationPoints: Int? = null,
    notes: String = "uninitialised"
) : CalibrationModel(
    observable, doubleArrayOf(), obsMin, obsMax, obsSaturation, obsNoiseFloor,
    tempCoeffPerC, rhCoeffPerFraction, refTempC, refRhFraction, rSquared,
    relErrorRmsPercent, relErrorMaxPercent, nCalibrationPoints, notes
) {
    override fun rawDose(value: Double): Double {
        if (lMax <= 0) throw IllegalArgumentException("lMax must be positive")
        val ceiling = lMax * (1.0 - SATURATION_EPS)
        val xc = value.coerceIn(0.0, ceiling)
        return k * (xc.pow(m)) / ((lMax - xc).pow(m))
    }
}

val SYNTHETIC_CALIBRATION = CalibrationModel(
    observable = "delta_l",
    coeffs = doubleArrayOf(3.513163172983686e-07, -3.1005607337275386e-05, 0.001058569444019896, -0.0015866092548736455, 1.662636706004635, 0.0),
    obsMin = 0.0,
    obsMax = 60.28905559244769,
    obsSaturation = 59.806191822478866,
    obsNoiseFloor = 1.0,
    tempCoeffPerC = 0.0035,
    rhCoeffPerFraction = 0.12,
    refTempC = 25.0,
    refRhFraction = 0.5,
    rSquared = 0.99983799420662,
    relErrorRmsPercent = 0.5173538371936779,
    relErrorMaxPercent = 1.680566906590002,
    nCalibrationPoints = 400,
    notes = "derived from ReactionModel(d_char=55.0) over 0-200 ppm*hr in delta_l; synthetic, replace with chamber data"
)

val DEFAULT_CALIBRATION = SYNTHETIC_CALIBRATION

val SATURATION_CALIBRATION_MODEL = SaturationCalibration(
    observable = "delta_l",
    k = 105.09665026213906,
    m = 0.9480188292916774,
    lMax = 78.2,
    obsMin = 0.0,
    obsMax = 21.344202606117328,
    obsSaturation = 59.76619066372162,
    obsNoiseFloor = 1.0,
    tempCoeffPerC = 0.0035,
    rhCoeffPerFraction = 0.12,
    refTempC = 25.0,
    refRhFraction = 0.5,
    rSquared = null,
    relErrorRmsPercent = 2.10561385408134,
    relErrorMaxPercent = 9.838462530208982,
    nCalibrationPoints = 790,
    notes = "Hill saturation form K*x^m/(l_max-x)^m fitted to ReactionModel(d_char=55.0) over 0.5-40 ppm*hr (K=105.1, m=0.9480); in-band rel err 2.1% rms / 9.8% max, but 66% max out to 200 ppm*hr - do NOT quote this model above obs_max. Synthetic; replace with chamber data."
)
