package com.mrpl.wristband.color

import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import kotlin.math.*
import com.mrpl.wristband.config.WristbandSpec
import com.mrpl.wristband.cv.BadgeSamples

data class NormalizationResult(
    var mode: String = "none",
    var matrix: Mat? = null,
    var padLinear: DoubleArray? = null,
    var padLab: DoubleArray? = null,
    var baselineLab: DoubleArray? = null,
    var baselineSource: String = "",

    var deltaLStar: Double = Double.NaN,
    var locusProjection: Double = Double.NaN,
    var chromaResidual: Double = Double.NaN,
    var deltaE00: Double = Double.NaN,

    var looResidualMean: Double = Double.NaN,
    var looResidualMax: Double = Double.NaN,
    var locusResidual: Double = Double.NaN,
    var locusLBias: Double = Double.NaN,
    var fitResidualMean: Double = Double.NaN,
    var conditionNumber: Double = Double.NaN,
    val patchResiduals: MutableMap<String, Pair<Double, Double>> = mutableMapOf(),
    val locusWeights: MutableMap<String, Pair<Double, Double>> = mutableMapOf(),

    var usedPatches: List<String> = emptyList(),
    val warnings: MutableList<String> = mutableListOf(),
    var ok: Boolean = false,
    var reason: String = "",

    var flatFieldMode: String = "none",
    var flatFieldSource: String = "none",
    var gradientPercent: Double = 0.0,

    var channelBalance: Double = Double.NaN,
    var lightQuality: String = "ok"
)

object Normalizer {

    val PAD_LOCUS_UNIT = doubleArrayOf(-0.99621391, 0.07134013, 0.0496833)

    val PAD_STAGE_ANCHORS_LAB: Array<DoubleArray> by lazy {
        Array(WristbandSpec.PAD_STAGE_SRGB.size) { i ->
            val rgb = DoubleArray(3) { j -> WristbandSpec.PAD_STAGE_SRGB[i][j].toDouble() }
            Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(Colorimetry.srgbToLinear(rgb)))
        }
    }
    
    val UNEXPOSED_PAD_LAB: DoubleArray by lazy {
        val rgb = DoubleArray(3) { j -> WristbandSpec.PAD_STAGE_SRGB[0][j].toDouble() }
        Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(Colorimetry.srgbToLinear(rgb)))
    }
    
    val FULLY_REACTED_PAD_LAB: DoubleArray by lazy {
        val rgb = DoubleArray(3) { j -> WristbandSpec.PAD_STAGE_SRGB[WristbandSpec.PAD_STAGE_SRGB.size-1][j].toDouble() }
        Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(Colorimetry.srgbToLinear(rgb)))
    }

    fun robustLstsq(A: Mat, L: Mat, minKeep: Int): Pair<Mat, Int> {
        val coef = Mat()
        Core.solve(A, L, coef, Core.DECOMP_SVD)
        
        val pred = Mat()
        Core.gemm(A, coef, 1.0, Mat(), 0.0, pred)
        
        val resid = DoubleArray(L.rows())
        val lRow = DoubleArray(L.cols())
        val pRow = DoubleArray(L.cols())
        
        for (i in 0 until L.rows()) {
            L.get(i, 0, lRow)
            pred.get(i, 0, pRow)
            var maxDiff = 0.0
            for (j in lRow.indices) {
                val diff = abs(lRow[j] - pRow[j])
                if (diff > maxDiff) maxDiff = diff
            }
            resid[i] = maxDiff
        }
        
        val sortedResid = resid.sortedArray()
        val med = if (sortedResid.isEmpty()) 0.0 else if (sortedResid.size % 2 == 0) {
            (sortedResid[sortedResid.size / 2 - 1] + sortedResid[sortedResid.size / 2]) / 2.0
        } else {
            sortedResid[sortedResid.size / 2]
        }
        
        val dev = DoubleArray(resid.size) { abs(resid[it] - med) }
        val sortedDev = dev.sortedArray()
        val madRaw = if (sortedDev.isEmpty()) 0.0 else if (sortedDev.size % 2 == 0) {
            (sortedDev[sortedDev.size / 2 - 1] + sortedDev[sortedDev.size / 2]) / 2.0
        } else {
            sortedDev[sortedDev.size / 2]
        }
        val mad = madRaw * 1.4826
        
        if (mad > 1e-9) {
            val limit = med + 3.0 * mad
            val keepList = mutableListOf<Int>()
            for (i in resid.indices) {
                if (resid[i] <= limit) keepList.add(i)
            }
            val nKeep = keepList.size
            if (nKeep in minKeep until A.rows()) {
                val Akeep = Mat(nKeep, A.cols(), A.type())
                val Lkeep = Mat(nKeep, L.cols(), L.type())
                val aRow = DoubleArray(A.cols())
                for (i in 0 until nKeep) {
                    val idx = keepList[i]
                    A.get(idx, 0, aRow)
                    for(c in aRow.indices) Akeep.put(i, c, aRow[c])
                    L.get(idx, 0, lRow)
                    for(c in lRow.indices) Lkeep.put(i, c, lRow[c])
                }
                
                val coefKeep = Mat()
                Core.solve(Akeep, Lkeep, coefKeep, Core.DECOMP_SVD)
                
                Akeep.release()
                Lkeep.release()
                coef.release()
                pred.release()
                return Pair(coefKeep, A.rows() - nKeep)
            }
        }
        
        pred.release()
        return Pair(coef, 0)
    }

    private fun usablePatchMask(samples: BadgeSamples, maxClip: Double = 0.02): BooleanArray {
        val mask = BooleanArray(samples.patches.size)
        for (i in samples.patches.indices) {
            val p = samples.patches[i]
            mask[i] = p.nPixels >= 5 && p.clipFraction <= maxClip && p.blackFraction <= 0.5 &&
                    p.meanLinear.all { !it.isNaN() && !it.isInfinite() }
        }
        return mask
    }

    private fun usableProbeMask(samples: BadgeSamples, maxClip: Double = 0.02): BooleanArray {
        val mask = BooleanArray(samples.whiteField.size)
        for (i in samples.whiteField.indices) {
            val w = samples.whiteField[i]
            mask[i] = w.nPixels >= 5 && w.clipFraction <= maxClip && w.blackFraction <= 0.02 &&
                    w.meanLinear.all { !it.isNaN() && !it.isInfinite() } &&
                    (w.meanLinear[0]*Colorimetry.LUMA[0] + w.meanLinear[1]*Colorimetry.LUMA[1] + w.meanLinear[2]*Colorimetry.LUMA[2] > 1e-4)
        }
        return mask
    }

    private fun normXy(spec: WristbandSpec, ptsMm: Array<DoubleArray>): Array<DoubleArray> {
        val cx = spec.centreMm[0]
        val cy = spec.centreMm[1]
        val half = spec.headMm / 2.0
        return Array(ptsMm.size) { i ->
            doubleArrayOf((ptsMm[i][0] - cx) / half, (ptsMm[i][1] - cy) / half)
        }
    }

    private fun patchXy(spec: WristbandSpec): Array<DoubleArray> = normXy(spec, spec.patchCentresMm())
    private fun probeXy(spec: WristbandSpec): Array<DoubleArray> = normXy(spec, spec.whiteFieldProbesMm())

    private fun design(xy: Array<DoubleArray>, kind: String): Mat {
        val cols = if (kind == "quad") 6 else 3
        val A = Mat(xy.size, cols, CvType.CV_64F)
        for (i in xy.indices) {
            val x = xy[i][0]
            val y = xy[i][1]
            A.put(i, 0, 1.0)
            A.put(i, 1, x)
            A.put(i, 2, y)
            if (kind == "quad") {
                A.put(i, 3, x * x)
                A.put(i, 4, y * y)
                A.put(i, 5, x * y)
            }
        }
        return A
    }

    private fun flatFieldGains(model: Pair<String, Mat>?, xy: Array<DoubleArray>): Array<DoubleArray> {
        if (model == null) {
            return Array(xy.size) { doubleArrayOf(1.0) }
        }
        val (kind, slopes) = model
        val A = design(xy, kind)
        val nSlopes = slopes.rows() / (A.cols() - 1)
        val nFeatures = A.cols() - 1
        
        val A1 = A.submat(0, A.rows(), 1, A.cols())
        val slT = Mat()
        Core.transpose(slopes, slT)
        val dot = Mat()
        Core.gemm(A1, slopes, 1.0, Mat(), 0.0, dot)
        
        val gains = Array(xy.size) { DoubleArray(dot.cols()) }
        val row = DoubleArray(dot.cols())
        for (i in 0 until dot.rows()) {
            dot.get(i, 0, row)
            for (j in row.indices) gains[i][j] = exp(row[j])
        }
        
        A.release()
        A1.release()
        slT.release()
        dot.release()
        return gains
    }

    private fun gradientPercent(model: Pair<String, Mat>?, xyEval: Array<DoubleArray>): Double {
        val gains = flatFieldGains(model, xyEval)
        var minVal = Double.MAX_VALUE
        var maxVal = -Double.MAX_VALUE
        var sum = 0.0
        for (i in gains.indices) {
            val row = gains[i]
            val lum = if (row.size == 3) row[0]*Colorimetry.LUMA[0] + row[1]*Colorimetry.LUMA[1] + row[2]*Colorimetry.LUMA[2] else row[0]
            if (lum < minVal) minVal = lum
            if (lum > maxVal) maxVal = lum
            sum += lum
        }
        val mean = sum / gains.size
        return 100.0 * (maxVal - minVal) / max(mean, 1e-9)
    }

    private fun starved(obs: Array<DoubleArray>, floor: Double = 0.02): Boolean {
        if (obs.isEmpty()) return true
        val r = DoubleArray(obs.size) { obs[it][0] }.sortedArray()
        val g = DoubleArray(obs.size) { obs[it][1] }.sortedArray()
        val b = DoubleArray(obs.size) { obs[it][2] }.sortedArray()
        val medR = if (r.size % 2 == 0) (r[r.size/2-1]+r[r.size/2])/2.0 else r[r.size/2]
        val medG = if (g.size % 2 == 0) (g[g.size/2-1]+g[g.size/2])/2.0 else g[g.size/2]
        val medB = if (b.size % 2 == 0) (b[b.size/2-1]+b[b.size/2])/2.0 else b[b.size/2]
        val maxM = max(medR, max(medG, medB))
        val minM = min(medR, min(medG, medB))
        return maxM <= 0.0 || (minM / max(maxM, 1e-12)) < floor
    }

    private fun fitWhiteField(obs: Array<DoubleArray>, xy: Array<DoubleArray>, modeIn: String = "luma"): Pair<Pair<String, Mat>?, String> {
        var mode = modeIn
        var note = ""
        if (obs.size < 9) return Pair(null, "")
        if (mode == "rgb" && starved(obs)) {
            mode = "luma"
            note = "white-field fell back to achromatic: one colour channel is starved (narrow-band light), so a per-channel profile cannot be estimated"
        }
        
        val L = Mat(obs.size, if (mode == "rgb") 3 else 1, CvType.CV_64F)
        for (i in obs.indices) {
            if (mode == "rgb") {
                L.put(i, 0, max(obs[i][0], 1e-6))
                L.put(i, 1, max(obs[i][1], 1e-6))
                L.put(i, 2, max(obs[i][2], 1e-6))
            } else {
                L.put(i, 0, max(obs[i][0]*Colorimetry.LUMA[0] + obs[i][1]*Colorimetry.LUMA[1] + obs[i][2]*Colorimetry.LUMA[2], 1e-6))
            }
        }
        Core.log(L, L)
        
        val A = design(xy, "quad")
        
        val w = Mat()
        Core.SVDecomp(A, w, Mat(), Mat(), Core.SVD_NO_UV)
        val wRow = DoubleArray(1)
        w.get(0, 0, wRow); val sMax = wRow[0]
        w.get(w.rows()-1, 0, wRow); val sMin = wRow[0]
        w.release()
        if (sMin == 0.0 || sMax / sMin > 1e6) {
            A.release(); L.release()
            return Pair(null, "white-field probe layout is degenerate; using the patch-ring plane")
        }
        
        val (coef, nExc) = robustLstsq(A, L, 8)
        if (nExc > 0) {
            val p = "white-field fit excluded ${nExc} probe(s) as outliers"
            note = if (note.isEmpty()) p else "${note}; ${p}"
        }
        A.release(); L.release()
        
        val slopes = coef.submat(1, coef.rows(), 0, coef.cols()).clone()
        coef.release()
        return Pair(Pair("quad", slopes), note)
    }

    private fun fitPatchPlane(obs: Array<DoubleArray>, ref: Array<DoubleArray>, xy: Array<DoubleArray>, modeIn: String = "luma"): Pair<Pair<String, Mat>?, String> {
        var mode = modeIn
        var note = ""
        if (obs.size < 5) return Pair(null, "")
        if (mode == "rgb" && starved(obs)) {
            mode = "luma"
            note = "flat-field fell back to achromatic: one colour channel is starved (narrow-band light), so a per-channel gradient cannot be estimated"
        }
        
        val L = Mat(obs.size, if (mode == "rgb") 3 else 1, CvType.CV_64F)
        for (i in obs.indices) {
            if (mode == "rgb") {
                L.put(i, 0, max(obs[i][0], 1e-6) / max(ref[i][0], 1e-6))
                L.put(i, 1, max(obs[i][1], 1e-6) / max(ref[i][1], 1e-6))
                L.put(i, 2, max(obs[i][2], 1e-6) / max(ref[i][2], 1e-6))
            } else {
                val num = max(obs[i][0]*Colorimetry.LUMA[0] + obs[i][1]*Colorimetry.LUMA[1] + obs[i][2]*Colorimetry.LUMA[2], 1e-6)
                val den = max(ref[i][0]*Colorimetry.LUMA[0] + ref[i][1]*Colorimetry.LUMA[1] + ref[i][2]*Colorimetry.LUMA[2], 1e-6)
                L.put(i, 0, num / den)
            }
        }
        Core.log(L, L)
        val A = design(xy, "plane")
        val (coef, nExc) = robustLstsq(A, L, 4)
        if (nExc > 0) {
            val p = "flat-field fit excluded ${nExc} patch(es) as spatial outliers"
            note = if (note.isEmpty()) p else "${note}; ${p}"
        }
        A.release(); L.release()
        val slopes = coef.submat(1, coef.rows(), 0, coef.cols()).clone()
        coef.release()
        return Pair(Pair("plane", slopes), note)
    }

    private fun padLocusLab(n: Int = 33): Array<DoubleArray> {
        val a = UNEXPOSED_PAD_LAB
        val b = FULLY_REACTED_PAD_LAB
        return Array(n) { i ->
            val t = i.toDouble() / (n - 1)
            doubleArrayOf(a[0] + t*(b[0]-a[0]), a[1] + t*(b[1]-a[1]), a[2] + t*(b[2]-a[2]))
        }
    }

    private fun locusWeights(refLab: Array<DoubleArray>, sigma: Double = 18.0): Pair<DoubleArray, DoubleArray> {
        val locus = padLocusLab()
        val dist = DoubleArray(refLab.size)
        val weights = DoubleArray(refLab.size)
        for (i in refLab.indices) {
            var minDist = Double.MAX_VALUE
            for (p in locus) {
                val d = Colorimetry.deltaECIEDE2000(refLab[i], p)
                if (d < minDist) minDist = d
            }
            dist[i] = minDist
            weights[i] = if (sigma > 0 && !sigma.isInfinite() && !sigma.isNaN()) {
                exp(-0.5 * (minDist / sigma) * (minDist / sigma))
            } else {
                1.0
            }
        }
        return Pair(weights, dist)
    }

    private fun looResiduals(obs: Array<DoubleArray>, ref: Array<DoubleArray>, mode: String, ridge: Double): Pair<DoubleArray, DoubleArray> {
        val n = obs.size
        val res = DoubleArray(n) { Double.NaN }
        val resL = DoubleArray(n) { Double.NaN }
        val nFeat = if (mode == "linear") 3 else if (mode == "affine") 4 else 6
        if (n - 1 < nFeat + 1) return Pair(res, resL)
        
        for (i in 0 until n) {
            val keepObs = Array(n - 1) { DoubleArray(3) }
            val keepRef = Array(n - 1) { DoubleArray(3) }
            var k = 0
            for (j in 0 until n) {
                if (i != j) {
                    keepObs[k] = obs[j]
                    keepRef[k] = ref[j]
                    k++
                }
            }
            try {
                val M = Colorimetry.solveCcm(keepObs, keepRef, mode, ridge)
                val pred = Colorimetry.applyCcm(arrayOf(obs[i]), M, mode)[0]
                val labPred = Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(pred))
                val labRef = Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(ref[i]))
                res[i] = Colorimetry.deltaECIEDE2000(labPred, labRef)
                resL[i] = labPred[0] - labRef[0]
                M.release()
            } catch (e: Exception) {
            }
        }
        return Pair(res, resL)
    }

    private fun locusProjection(padLab: DoubleArray, baselineLab: DoubleArray): Double {
        val d0 = padLab[0] - baselineLab[0]
        val d1 = padLab[1] - baselineLab[1]
        val d2 = padLab[2] - baselineLab[2]
        return d0 * PAD_LOCUS_UNIT[0] + d1 * PAD_LOCUS_UNIT[1] + d2 * PAD_LOCUS_UNIT[2]
    }

    private fun locusLabForLightness(lStar: Double): DoubleArray {
        val A = PAD_STAGE_ANCHORS_LAB
        val L_asc = DoubleArray(A.size) { A[A.size - 1 - it][0] }
        val cL = max(L_asc[0], min(lStar, L_asc[L_asc.size - 1]))
        
        var idx = 0
        while (idx < L_asc.size - 1 && L_asc[idx+1] < cL) {
            idx++
        }
        if (idx >= L_asc.size - 1) idx = L_asc.size - 2
        val t = if (L_asc[idx+1] == L_asc[idx]) 0.0 else (cL - L_asc[idx]) / (L_asc[idx+1] - L_asc[idx])
        
        val a1 = A[A.size - 1 - idx][1]
        val a2 = A[A.size - 1 - (idx+1)][1]
        val b1 = A[A.size - 1 - idx][2]
        val b2 = A[A.size - 1 - (idx+1)][2]
        
        return doubleArrayOf(cL, a1 + t*(a2-a1), b1 + t*(b2-b1))
    }

    private fun locusChromaResidual(padLab: DoubleArray): Double {
        val expected = locusLabForLightness(padLab[0])
        val da = padLab[1] - expected[1]
        val db = padLab[2] - expected[2]
        return hypot(da, db)
    }

    fun normalizeBadge(
        samples: BadgeSamples,
        spec: WristbandSpec = WristbandSpec.BADGE,
        referenceSrgb: Array<IntArray>? = null,
        mode: String = "root6",
        ridge: Double = 1e-4,
        baselineMode: String = "onbadge",
        warnLooResidual: Double = 8.0,
        flatField: String = "luma",
        maxGradientPercent: Double = 35.0,
        warnLocusResidual: Double = 2.0
    ): NormalizationResult {
        val out = NormalizationResult()
        if (flatField != "luma" && flatField != "rgb" && flatField != "none") {
            out.reason = "unknown flat_field mode ${flatField}; expected luma, rgb, none"
            return out
        }

        val refSrgbSource = referenceSrgb ?: WristbandSpec.PATCHES.map { it.srgb }.toTypedArray()
        val refAll = Array(refSrgbSource.size) { i ->
            Colorimetry.srgbToLinear(DoubleArray(3) { j -> refSrgbSource[i][j].toDouble() })
        }
        
        val obsRaw = Array(samples.patches.size) { i -> samples.patches[i].meanLinear }
        if (obsRaw.size != refAll.size) {
            out.reason = "patch count mismatch: sampled ${obsRaw.size}, reference ${refAll.size}"
            return out
        }

        val usable = usablePatchMask(samples)
        var nUsable = 0
        val dropped = mutableListOf<String>()
        for (i in usable.indices) {
            if (usable[i]) nUsable++ else dropped.add(WristbandSpec.PATCHES[i].name)
        }
        if (nUsable < obsRaw.size) {
            out.warnings.add("dropped unusable patches: ${dropped.joinToString(", ")}")
        }

        val xy = patchXy(spec)
        var model: Pair<String, Mat>? = null
        var note = ""

        if (flatField != "none") {
            val probeXy = probeXy(spec)
            val probes = Array(samples.whiteField.size) { i -> samples.whiteField[i].meanLinear }
            val pmask = usableProbeMask(samples)
            var pUsable = 0
            for (m in pmask) if (m) pUsable++
            
            if (probes.size == probeXy.size && pUsable >= 9) {
                val probesClean = Array(pUsable) { DoubleArray(3) }
                val probeXyClean = Array(pUsable) { DoubleArray(2) }
                var k = 0
                for (i in pmask.indices) {
                    if (pmask[i]) {
                        probesClean[k] = probes[i]
                        probeXyClean[k] = probeXy[i]
                        k++
                    }
                }
                val res = fitWhiteField(probesClean, probeXyClean, flatField)
                model = res.first
                note = res.second
                if (model != null) out.flatFieldSource = "whitefield"
            }

            if (model == null) {
                if (probes.size != probeXy.size) {
                    out.warnings.add("white-field probes were not sampled (stale BadgeSamples?); falling back to the patch-ring plane, which cannot see vignetting")
                } else if (pUsable < 9) {
                    out.warnings.add("only ${pUsable} of ${probes.size} white-field probes usable (clipped or shadowed); falling back to the patch-ring plane, which cannot see lens vignetting - the reading may understate the dose")
                } else if (note.isNotEmpty()) {
                    out.warnings.add(note)
                    note = ""
                }

                if (nUsable >= 5) {
                    val achrom = mutableListOf<Int>()
                    for (i in usable.indices) {
                        val role = WristbandSpec.PATCHES[i].role
                        if (usable[i] && (role == "neutral" || role == "substrate")) {
                            achrom.add(i)
                        }
                    }
                    if (achrom.size >= 5) {
                        val obsAchrom = Array(achrom.size) { obsRaw[achrom[it]] }
                        val refAchrom = Array(achrom.size) { refAll[achrom[it]] }
                        val xyAchrom = Array(achrom.size) { xy[achrom[it]] }
                        val res = fitPatchPlane(obsAchrom, refAchrom, xyAchrom, flatField)
                        model = res.first
                        val planeNote = res.second
                        note = if (note.isEmpty()) planeNote else if (planeNote.isNotEmpty()) "${note}; ${planeNote}" else note
                        if (model != null) out.flatFieldSource = "patches"
                    } else {
                        val n = "only ${achrom.size} usable achromatic patches (needs 5); no spatial correction is possible from the ring either"
                        note = if (note.isEmpty()) n else "${note}; ${n}"
                    }
                }
            }

            if (note.isNotEmpty()) out.warnings.add(note)

            if (model == null) {
                out.warnings.add("only ${nUsable} usable patches and no usable white field; skipped the flat-field correction entirely - any illumination gradient or vignetting will bias the reading")
            } else {
                out.flatFieldMode = flatField
                val xyEval = Array(1 + xy.size + probeXy.size) { DoubleArray(2) }
                xyEval[0] = doubleArrayOf(0.0, 0.0)
                for (i in xy.indices) xyEval[1 + i] = xy[i]
                for (i in probeXy.indices) xyEval[1 + xy.size + i] = probeXy[i]
                out.gradientPercent = gradientPercent(model, xyEval)
                if (out.gradientPercent > maxGradientPercent) {
                    out.reason = "illumination varies ${out.gradientPercent.toInt()}% across the badge (limit ${maxGradientPercent.toInt()}%) - that is a shadow edge or a specular streak, not a smooth gradient. Move out of the hard light and retake."
                    return out
                }
            }
        }

        val gains = flatFieldGains(model, xy)
        val obsAll = Array(obsRaw.size) { DoubleArray(3) }
        for (i in obsRaw.indices) {
            val g = gains[i]
            val g0 = max(g[0], 1e-6)
            val g1 = max(if(g.size>1) g[1] else g[0], 1e-6)
            val g2 = max(if(g.size>2) g[2] else g[0], 1e-6)
            obsAll[i] = doubleArrayOf(obsRaw[i][0] / g0, obsRaw[i][1] / g1, obsRaw[i][2] / g2)
        }

        val obs = Array(nUsable) { DoubleArray(3) }
        val ref = Array(nUsable) { DoubleArray(3) }
        var kIdx = 0
        for (i in usable.indices) {
            if (usable[i]) {
                obs[kIdx] = obsAll[i]
                ref[kIdx] = refAll[i]
                kIdx++
            }
        }

        val ladder = mapOf("root6" to 6, "affine" to 4, "linear" to 3)
        val order = listOf("root6", "affine", "linear").filter { ladder[it]!! <= (ladder[mode] ?: 6) }.ifEmpty { listOf("linear") }
        var chosen: String? = null
        for (cand in order) {
            if (nUsable >= ladder[cand]!! + 1) {
                chosen = cand
                break
            }
        }

        val padLinearRaw = samples.pad?.meanLinear ?: DoubleArray(3)

        var padCorrected: DoubleArray
        var patchesCorrected: Array<DoubleArray>

        if (chosen != null) {
            val M = Colorimetry.solveCcm(obs, ref, chosen, ridge)
            val F = Colorimetry.ccmFeatureMatrix(obs, chosen)
            
            val Ft = Mat()
            Core.transpose(F, Ft)
            val FtF = Mat()
            Core.gemm(Ft, F, 1.0, Mat(), 0.0, FtF)
            val I = Mat.eye(F.cols(), F.cols(), CvType.CV_64F)
            val ridgeI = Mat()
            Core.multiply(I, org.opencv.core.Scalar(ridge), ridgeI)
            val Acond = Mat()
            Core.add(FtF, ridgeI, Acond)
            
            val wCond = Mat()
            Core.SVDecomp(Acond, wCond, Mat(), Mat(), Core.SVD_NO_UV)
            val wRow = DoubleArray(1)
            wCond.get(0, 0, wRow); val sMax = wRow[0]
            wCond.get(wCond.rows()-1, 0, wRow); val sMin = wRow[0]
            out.conditionNumber = if (sMin == 0.0) Double.MAX_VALUE else sMax / sMin
            
            Ft.release(); FtF.release(); I.release(); ridgeI.release(); Acond.release(); wCond.release(); F.release()

            out.mode = chosen
            out.matrix = M

            val pred = Colorimetry.applyCcm(obs, M, chosen)
            val fitRes = DoubleArray(nUsable)
            var fitSum = 0.0
            for (i in 0 until nUsable) {
                fitRes[i] = Colorimetry.deltaECIEDE2000(
                    Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(pred[i])),
                    Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(ref[i]))
                )
                fitSum += fitRes[i]
            }
            out.fitResidualMean = fitSum / nUsable

            val (loo, looL) = looResiduals(obs, ref, chosen, ridge)
            var hasNan = false
            for (v in loo) if (v.isNaN()) hasNan = true
            
            if (hasNan) {
                out.warnings.add("too few patches for leave-one-out validation; reporting training residual instead")
                for (i in loo.indices) {
                    loo[i] = fitRes[i]
                    looL[i] = Double.NaN
                }
                out.looResidualMean = out.fitResidualMean
                out.looResidualMax = fitRes.maxOrNull() ?: Double.NaN
            } else {
                var s = 0.0; var c = 0
                for (v in loo) if (!v.isNaN()) { s += v; c++ }
                out.looResidualMean = s / c
                out.looResidualMax = loo.filter { !it.isNaN() }.maxOrNull() ?: Double.NaN
            }

            val refLab = Array(nUsable) { Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(ref[it])) }
            val (weights, locusDist) = locusWeights(refLab)
            
            var wSum = 0.0
            var wLooSum = 0.0
            for (i in loo.indices) {
                if (!loo[i].isNaN()) {
                    wSum += weights[i]
                    wLooSum += weights[i] * loo[i]
                }
            }
            if (wSum > 1e-9) out.locusResidual = wLooSum / wSum

            var wlSum = 0.0
            var wlSumL = 0.0
            for (i in looL.indices) {
                if (!looL[i].isNaN()) {
                    wlSum += weights[i]
                    wlSumL += weights[i] * looL[i]
                }
            }
            if (wlSum > 1e-9) out.locusLBias = wlSumL / wlSum

            val names = mutableListOf<String>()
            for (i in usable.indices) if (usable[i]) names.add(WristbandSpec.PATCHES[i].name)
            out.usedPatches = names

            for (i in names.indices) {
                out.patchResiduals[names[i]] = Pair(fitRes[i], loo[i])
                out.locusWeights[names[i]] = Pair((weights[i] * 10000).roundToInt() / 10000.0, (locusDist[i] * 100).roundToInt() / 100.0)
            }

            padCorrected = Colorimetry.applyCcm(arrayOf(padLinearRaw), M, chosen)[0]
            patchesCorrected = Colorimetry.applyCcm(obsAll, M, chosen)

        } else {
            val neutrals = mutableListOf<Int>()
            for (i in usable.indices) {
                if (usable[i] && WristbandSpec.PATCHES[i].role == "neutral") neutrals.add(i)
            }
            if (neutrals.isEmpty()) {
                out.reason = "only ${nUsable} usable reference patches and no readable neutral - cannot correct illumination; reject scan"
                return out
            }
            val obsNeutrals = Array(neutrals.size) { obsAll[neutrals[it]] }
            val refNeutrals = Array(neutrals.size) { refAll[neutrals[it]] }
            val gain = Colorimetry.vonKriesGain(obsNeutrals, refNeutrals)
            
            val gainMat = Mat(1, 3, CvType.CV_64F)
            gainMat.put(0, 0, gain[0], gain[1], gain[2])
            out.mode = "vonkries"
            out.matrix = gainMat
            out.warnings.add("degraded to von Kries grey balance on ${neutrals.size} neutral patch(es); colour cast removed but sensor cross-talk uncorrected")
            
            padCorrected = doubleArrayOf(padLinearRaw[0]*gain[0], padLinearRaw[1]*gain[1], padLinearRaw[2]*gain[2])
            patchesCorrected = Array(obsAll.size) { i -> doubleArrayOf(obsAll[i][0]*gain[0], obsAll[i][1]*gain[1], obsAll[i][2]*gain[2]) }
            out.usedPatches = neutrals.map { WristbandSpec.PATCHES[it].name }
        }

        out.padLinear = padCorrected
        out.padLab = Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(padCorrected))

        val subs = mutableListOf<Int>()
        for (i in usable.indices) {
            if (usable[i] && WristbandSpec.PATCHES[i].role == "substrate") subs.add(i)
        }

        if (baselineMode == "onbadge" && subs.isNotEmpty()) {
            var sum0 = 0.0; var sum1 = 0.0; var sum2 = 0.0
            for (idx in subs) {
                sum0 += patchesCorrected[idx][0]
                sum1 += patchesCorrected[idx][1]
                sum2 += patchesCorrected[idx][2]
            }
            out.baselineLab = Colorimetry.xyzToLab(Colorimetry.linearRgbToXyz(doubleArrayOf(sum0/subs.size, sum1/subs.size, sum2/subs.size)))
            out.baselineSource = "onbadge:" + subs.map { WristbandSpec.PATCHES[it].name }.joinToString("+")
            
            var totalSubs = 0
            for (p in WristbandSpec.PATCHES) if (p.role == "substrate") totalSubs++
            if (subs.size < totalSubs) {
                out.warnings.add("only ${subs.size} of ${totalSubs} substrate patches usable; the opposite-pair cancellation of illumination gradients is lost, so the reading carries whatever ramp the flat field did not remove")
            }
        } else {
            out.baselineLab = UNEXPOSED_PAD_LAB.clone()
            out.baselineSource = "constant:UNEXPOSED_PAD_LAB"
            if (baselineMode == "onbadge") {
                out.reason = "the reference patches the reading is measured against are unusable, so the pad has nothing in this photograph to be compared with. Almost always blown-out highlights: move out of the direct glare, or step away from the sodium lamp and use the torch as the main light. Passing baseline_mode='constant' explicitly will read it anyway, but the result is not defensible as an exposure record."
                return out
            }
        }

        out.deltaLStar = out.baselineLab!![0] - out.padLab!![0]
        out.locusProjection = locusProjection(out.padLab!!, out.baselineLab!!)
        out.chromaResidual = locusChromaResidual(out.padLab!!)
        out.deltaE00 = Colorimetry.deltaECIEDE2000(out.baselineLab!!, out.padLab!!)

        if (out.deltaLStar.isNaN() || out.deltaLStar.isInfinite()) {
            out.reason = "the pad's lightness change is not finite; corrupt sample"
            return out
        }

        if (!out.looResidualMean.isNaN() && out.looResidualMean > warnLooResidual) {
            out.warnings.add("colour correction is poor: mean leave-one-out residual ${String.format("%.1f", out.looResidualMean)} dE00 > ${String.format("%.0f", warnLooResidual)}. The light is narrow-band or strongly tinted. The reading stands - it is a difference against patches in the same frame, so most of this error cancels - but switch the torch on if you want a defensible number.")
        }

        if (!out.locusResidual.isNaN() && out.locusResidual > warnLocusResidual) {
            out.warnings.add("colour correction is weak near the pad's own tone: locus-weighted residual ${String.format("%.2f", out.locusResidual)} dE00 > ${String.format("%.1f", warnLocusResidual)}. The reading stands, but even light or a rescan would make it more defensible.")
        }

        out.ok = true
        out.reason = "ok"
        return out
    }
}
