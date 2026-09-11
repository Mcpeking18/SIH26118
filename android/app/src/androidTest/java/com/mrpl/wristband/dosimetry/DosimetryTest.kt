package com.mrpl.wristband.dosimetry

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.abs

class DosimetryTest {
    private val EPS = 1e-4

    @Test
    fun testNormalDose() {
        val res = Dosimetry.assessScan(4.5, 8.0)
        assertEquals(7.534132520750368, res.dosePpmHr, EPS)
        assertEquals(0.941766565093796, res.twaPpm, EPS)
        assertEquals(Verdict.SAFE, res.verdict)
        assertFalse(res.saturated)
        assertFalse(res.belowNoiseFloor)
    }

    @Test
    fun testZeroNearZero() {
        val res = Dosimetry.assessScan(0.1, 8.0)
        assertEquals(0.16624885998031122, res.dosePpmHr, EPS)
        assertTrue(res.belowNoiseFloor)
        assertEquals(Verdict.SAFE, res.verdict)
        
        val resNeg = Dosimetry.assessScan(-1.5, 8.0)
        assertEquals(0.0, resNeg.dosePpmHr, EPS)
        // verify irreversible warning flag fired
        assertTrue(resNeg.messages.any { it.contains("reads LIGHTER than its own baseline") })
    }

    @Test
    fun testWarningCriticalBoundaries() {
        val warn = Dosimetry.assessScan(15.0, 8.0)
        assertEquals(Verdict.CRITICAL, warn.verdict)

        val crit = Dosimetry.assessScan(35.0, 8.0)
        assertEquals(Verdict.CRITICAL, crit.verdict)
    }

    @Test
    fun testSuspectCondition() {
        val res = Dosimetry.assessScan(10.0, 8.0, chromaResidual = 6.0, deltaLStar = 10.0)
        assertEquals(Verdict.SUSPECT, res.verdict)
        assertFalse(res.integrityOk)
        assertEquals(5.0, res.chromaResidualLimit, EPS)
    }

    @Test
    fun testSaturatedCondition() {
        val res = Dosimetry.assessScan(100.0, 8.0)
        assertEquals(Verdict.SATURATED, res.verdict)
        assertTrue(res.saturated)
    }

    @Test
    fun testScanSeries() {
        val readings = listOf(
            Pair(0.0, 0.0),
            Pair(4.0, 2.4125230329197365), // ~1 ppm
            Pair(8.0, 4.7600607268102095)  // ~1 ppm
        )
        val res = Dosimetry.assessScanSeries(readings)
        assertEquals(8.0, res.totalDosePpmHr, 1.0)
        assertTrue(res.stelDeterminable)
        assertFalse(res.intervals[0].exceedsStel)
    }

    @Test
    fun testLocusRejectionLogic() {
        val limit1 = Dosimetry.chromaLimit(5.0)
        assertEquals(5.0, limit1, EPS) // hits floor

        val limit2 = Dosimetry.chromaLimit(20.0)
        assertEquals(8.0, limit2, EPS) // 20 * 0.4 = 8.0

        val cr = Dosimetry.locusChromaResidual(
            doubleArrayOf(70.0, 5.0, 5.0),
            doubleArrayOf(95.0, 0.0, 0.0) // baseline ignored
        )
        // We know Python calculates this explicitly
        val pyCr = 11.78459885
        assertEquals(pyCr, cr, EPS)
    }
}
