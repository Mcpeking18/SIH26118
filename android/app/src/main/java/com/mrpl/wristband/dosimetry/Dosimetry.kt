package com.mrpl.wristband.dosimetry

import com.mrpl.wristband.config.WristbandSpec
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.sqrt

data class DoseAssessment(
    val observable: Double = Double.NaN,
    val observableName: String = "delta_l",
    val dosePpmHr: Double = 0.0,
    val shiftHours: Double = 8.0,
    val twaPpm: Double = 0.0,
    val verdict: Verdict = Verdict.INVALID,
    val deltaE00: Double = Double.NaN,
    val chromaResidual: Double = Double.NaN,
    val chromaResidualLimit: Double = Double.NaN,
    val integrityOk: Boolean = true,
    val limits: ExposureLimits = ACGIH_OSHA_NIOSH,
    val stelDeterminable: Boolean = false,
    val saturated: Boolean = false,
    val belowNoiseFloor: Boolean = false,
    val extrapolated: Boolean = false,
    val environmentFactor: Double = 1.0,
    val messages: List<String> = emptyList()
)

data class IntervalExposure(
    val tStartHours: Double,
    val tEndHours: Double,
    val durationHours: Double,
    val doseIncrementPpmHr: Double,
    val meanPpm: Double,
    val exceedsStel: Boolean,
    val exceedsNioshCeiling: Boolean
)

data class SeriesAssessment(
    val intervals: List<IntervalExposure> = emptyList(),
    val totalDosePpmHr: Double = 0.0,
    val totalHours: Double = 0.0,
    val twaPpm: Double = 0.0,
    val worstInterval: IntervalExposure? = null,
    val stelUpperBoundPpm: Double = Double.NaN,
    val stelDeterminable: Boolean = false,
    val verdict: Verdict = Verdict.SAFE,
    val messages: List<String> = emptyList()
)

object Dosimetry {
    val CHROMA_LIMIT_FLOOR = 5.0
    val CHROMA_LIMIT_SLOPE = 0.4
    val PAD_LOCUS_UNIT = doubleArrayOf(-0.99621391, 0.07134013, 0.0496833)
    val PAD_STAGE_ANCHORS_LAB: Array<DoubleArray> by lazy {
        Array(com.mrpl.wristband.config.WristbandSpec.PAD_STAGE_SRGB.size) { i ->
            val rgb = DoubleArray(3) { j -> com.mrpl.wristband.config.WristbandSpec.PAD_STAGE_SRGB[i][j].toDouble() }
            com.mrpl.wristband.color.Colorimetry.xyzToLab(com.mrpl.wristband.color.Colorimetry.linearRgbToXyz(com.mrpl.wristband.color.Colorimetry.srgbToLinear(rgb)))
        }
    }
    val UNEXPOSED_PAD_LAB: DoubleArray by lazy { PAD_STAGE_ANCHORS_LAB.first() }
    val FULLY_REACTED_PAD_LAB: DoubleArray by lazy { PAD_STAGE_ANCHORS_LAB.last() }


    fun locusLabForLightness(lStar: Double, anchors: Array<DoubleArray>? = null): DoubleArray {
        val A = anchors ?: PAD_STAGE_ANCHORS_LAB
        // A is sorted by decreasing L*. We need increasing L* for interpolation, so we reverse it manually.
        val n = A.size
        
        var minL = A[n - 1][0]
        var maxL = A[0][0]
        val clampedL = lStar.coerceIn(minL, maxL)

        // Find the interval
        for (i in 0 until n - 1) {
            val l0 = A[i][0] // Higher L
            val l1 = A[i + 1][0] // Lower L
            if (clampedL <= l0 && clampedL >= l1) {
                val t = if (l0 == l1) 0.0 else (clampedL - l1) / (l0 - l1)
                val aStar = A[i + 1][1] + t * (A[i][1] - A[i + 1][1])
                val bStar = A[i + 1][2] + t * (A[i][2] - A[i + 1][2])
                return doubleArrayOf(clampedL, aStar, bStar)
            }
        }
        return doubleArrayOf(clampedL, A[n - 1][1], A[n - 1][2])
    }

    fun locusProjection(padLab: DoubleArray, baselineLab: DoubleArray, unit: DoubleArray? = null): Double {
        val u = unit ?: PAD_LOCUS_UNIT
        val d0 = padLab[0] - baselineLab[0]
        val d1 = padLab[1] - baselineLab[1]
        val d2 = padLab[2] - baselineLab[2]
        return d0 * u[0] + d1 * u[1] + d2 * u[2]
    }

    fun locusChromaResidual(padLab: DoubleArray, baselineLab: DoubleArray? = null, unit: DoubleArray? = null, anchors: Array<DoubleArray>? = null): Double {
        val expected = locusLabForLightness(padLab[0], anchors)
        val d1 = padLab[1] - expected[1]
        val d2 = padLab[2] - expected[2]
        return sqrt(d1 * d1 + d2 * d2)
    }

    fun chromaLimit(deltaLStar: Double, floor: Double = CHROMA_LIMIT_FLOOR, slope: Double = CHROMA_LIMIT_SLOPE): Double {
        if (deltaLStar.isNaN()) return floor
        return max(floor, slope * abs(deltaLStar))
    }

    private fun verdictFor(twa: Double, dose: Double, limits: ExposureLimits): Verdict {
        if (twa > limits.twaPpm * limits.twaCriticalMultiple || dose >= limits.doseCriticalPpmHr) {
            return Verdict.CRITICAL
        }
        if (twa > limits.twaPpm) {
            return Verdict.WARNING
        }
        return Verdict.SAFE
    }

    fun assessScan(
        observable: Double,
        shiftHours: Double,
        calibration: CalibrationModel = DEFAULT_CALIBRATION,
        limits: ExposureLimits = ACGIH_OSHA_NIOSH,
        tempC: Double? = null,
        rhFraction: Double? = null,
        deltaE00: Double = Double.NaN,
        chromaResidual: Double = Double.NaN,
        deltaLStar: Double = Double.NaN,
        chromaLimitFloor: Double = CHROMA_LIMIT_FLOOR,
        chromaLimitSlope: Double = CHROMA_LIMIT_SLOPE
    ): DoseAssessment {
        require(shiftHours > 0) { "shiftHours must be positive" }

        val env = calibration.environmentFactor(tempC, rhFraction)
        val dose = calibration.dose(observable, tempC, rhFraction)
        val twa = dose / shiftHours
        val name = calibration.observable

        val msgs = mutableListOf<String>()
        val saturated = observable >= calibration.obsSaturation
        val belowFloor = observable < calibration.obsNoiseFloor
        val extrapolated = observable > calibration.obsMax || observable < calibration.obsMin

        if (saturated) {
            msgs.add("pad optically saturated at $name $observable (>= ${calibration.obsSaturation}); reported dose is a LOWER BOUND - treat as a confirmed overexposure and use a shorter badge interval")
        }
        if (belowFloor) {
            msgs.add("$name $observable is below the ${calibration.obsNoiseFloor} noise floor; report as 'no detectable exposure', not as a precise number")
        }
        if (extrapolated && !saturated) {
            msgs.add("$name $observable lies outside the validated range [${calibration.obsMin}, ${calibration.obsMax}]; extrapolated")
        }
        if (observable < -abs(calibration.obsNoiseFloor)) {
            msgs.add("$name is $observable - the pad reads LIGHTER than its own baseline. CuS formation is irreversible, so this is a badge mix-up, a soiled reference patch, or a failed rectification. Do not log this as zero exposure.")
        }
        if (env != 1.0) {
            msgs.add("environmental correction factor $env applied (T=${tempC ?: calibration.refTempC} C, RH=${(rhFraction ?: calibration.refRhFraction) * 100}%)")
        }

        val dl = if (deltaLStar.isNaN() && name == "delta_l") observable else deltaLStar
        val limit = chromaLimit(dl, chromaLimitFloor, chromaLimitSlope)

        var integrityOk = true
        if (!chromaResidual.isNaN() && chromaResidual > limit) {
            integrityOk = false
            msgs.add("INTEGRITY: pad sits $chromaResidual L*a*b* units off the CuS reaction path (limit $limit for a lightness change of ${abs(dl)}). It has changed colour in a direction H2S does not produce - suspect a contaminated or time-expired reagent, a damaged pad, or the wrong badge. Quarantine it and send for lab analysis; the dose below is reported for the record, not for compliance.")
        }

        var verdict = if (saturated) {
            Verdict.SATURATED
        } else if (!integrityOk) {
            Verdict.SUSPECT
        } else {
            verdictFor(twa, dose, limits)
        }

        if (saturated) {
            msgs.add("verdict forced to SATURATED; escalate as CRITICAL operationally")
        }

        msgs.add("STEL not determinable from a single cumulative reading - use mid-shift kiosk scans (assess_scan_series) to bound short-term peaks")

        return DoseAssessment(
            observable = observable,
            observableName = name,
            dosePpmHr = dose,
            shiftHours = shiftHours,
            twaPpm = twa,
            verdict = verdict,
            deltaE00 = deltaE00,
            chromaResidual = chromaResidual,
            chromaResidualLimit = limit,
            integrityOk = integrityOk,
            limits = limits,
            stelDeterminable = false,
            saturated = saturated,
            belowNoiseFloor = belowFloor,
            extrapolated = extrapolated,
            environmentFactor = env,
            messages = msgs
        )
    }

    fun assessScanSeries(
        readings: List<Pair<Double, Double>>, // Pair(elapsedHours, observable)
        calibration: CalibrationModel = DEFAULT_CALIBRATION,
        limits: ExposureLimits = ACGIH_OSHA_NIOSH,
        tempC: Double? = null,
        rhFraction: Double? = null,
        stelWindowHours: Double = 0.25
    ): SeriesAssessment {
        val pts = readings.sortedBy { it.first }
        val outMsgs = mutableListOf<String>()

        if (pts.size < 2) {
            outMsgs.add("need at least two readings to bound short-term exposure; a single scan yields dose and TWA only")
            if (pts.isNotEmpty()) {
                val single = assessScan(pts[0].second, max(pts[0].first, 1e-6), calibration, limits, tempC, rhFraction)
                return SeriesAssessment(
                    totalDosePpmHr = single.dosePpmHr,
                    totalHours = single.shiftHours,
                    twaPpm = single.twaPpm,
                    verdict = single.verdict,
                    messages = outMsgs
                )
            }
            return SeriesAssessment(messages = outMsgs)
        }

        val doses = pts.map { calibration.dose(it.second, tempC, rhFraction) }.toMutableList()

        for (i in 1 until doses.size) {
            if (doses[i] < doses[i - 1] - 1e-9) {
                outMsgs.add("reading at t=${pts[i].first} h shows dose falling ${doses[i - 1]} -> ${doses[i]} ppm*hr; the reaction is irreversible, so this is noise or a badge mix-up. Clamped.")
                doses[i] = doses[i - 1]
            }
        }

        var worst: IntervalExposure? = null
        val intervals = mutableListOf<IntervalExposure>()

        for (i in 1 until pts.size) {
            val t0 = pts[i - 1].first
            val t1 = pts[i].first
            val dur = t1 - t0
            if (dur <= 0) {
                outMsgs.add("skipped non-positive interval at t=$t1 h")
                continue
            }
            val inc = doses[i] - doses[i - 1]
            val meanPpm = inc / dur
            val iv = IntervalExposure(
                tStartHours = t0,
                tEndHours = t1,
                durationHours = dur,
                doseIncrementPpmHr = inc,
                meanPpm = meanPpm,
                exceedsStel = meanPpm > limits.stelPpm,
                exceedsNioshCeiling = meanPpm > limits.nioshCeilingPpm
            )
            intervals.add(iv)
            if (worst == null || meanPpm > worst.meanPpm) {
                worst = iv
            }
        }

        if (intervals.isEmpty()) {
            outMsgs.add("no valid intervals; check reading timestamps")
            return SeriesAssessment(messages = outMsgs)
        }

        val totalDosePpmHr = doses.last() - doses.first()
        val totalHours = pts.last().first - pts.first().first
        val twaPpm = if (totalHours > 0) totalDosePpmHr / totalHours else 0.0

        val bound = intervals.maxOf { it.doseIncrementPpmHr / stelWindowHours }
        val stelDeterminable = true

        if (bound <= limits.stelPpm) {
            outMsgs.add("STEL provably compliant: even in the worst case all dose in one interval fell inside a single ${stelWindowHours * 60}-minute window, giving at most $bound ppm vs the ${limits.stelPpm} ppm limit")
        } else {
            val maxDur = intervals.maxOf { it.durationHours }
            outMsgs.add("STEL cannot be excluded: worst-case ${stelWindowHours * 60}-minute average could reach $bound ppm (limit ${limits.stelPpm} ppm). Longest interval is $maxDur h - shorten the scan interval to tighten this bound.")
        }

        var verdict = verdictFor(twaPpm, totalDosePpmHr, limits)
        if (worst != null && worst.exceedsNioshCeiling) {
            verdict = Verdict.CRITICAL
            outMsgs.add("interval ${worst.tStartHours}-${worst.tEndHours} h averaged ${worst.meanPpm} ppm, above the NIOSH ${limits.nioshCeilingPpm} ppm ceiling - this is an incident, not a trend")
        }

        return SeriesAssessment(
            intervals = intervals,
            totalDosePpmHr = totalDosePpmHr,
            totalHours = totalHours,
            twaPpm = twaPpm,
            worstInterval = worst,
            stelUpperBoundPpm = bound,
            stelDeterminable = stelDeterminable,
            verdict = verdict,
            messages = outMsgs
        )
    }
}
