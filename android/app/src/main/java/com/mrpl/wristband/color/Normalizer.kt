package com.mrpl.wristband.color

import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import kotlin.math.abs

object Normalizer {
    
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
        val med = if (sortedResid.size % 2 == 0) {
            (sortedResid[sortedResid.size / 2 - 1] + sortedResid[sortedResid.size / 2]) / 2.0
        } else {
            sortedResid[sortedResid.size / 2]
        }
        
        val dev = DoubleArray(resid.size) { abs(resid[it] - med) }
        val sortedDev = dev.sortedArray()
        val madRaw = if (sortedDev.size % 2 == 0) {
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
            if (nKeep >= minKeep && nKeep < A.rows()) {
                val Akeep = Mat(nKeep, A.cols(), A.type())
                val Lkeep = Mat(nKeep, L.cols(), L.type())
                val aRow = DoubleArray(A.cols())
                for (i in 0 until nKeep) {
                    val idx = keepList[i]
                    A.get(idx, 0, aRow)
                    Akeep.put(i, 0, *aRow)
                    L.get(idx, 0, lRow)
                    Lkeep.put(i, 0, *lRow)
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
}
