package com.mrpl.wristband.config

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.abs

class BadgeV2SpecTest {

    private val spec = BadgeV2Spec.BADGE

    @Test
    fun testDimensions() {
        assertEquals(40.0, spec.widthMm, 1e-6)
        assertEquals(30.0, spec.heightMm, 1e-6)
        assertTrue(spec.widthPx > 0)
        assertTrue(spec.heightPx > 0)
    }

    @Test
    fun testFiducials() {
        val centres = spec.markerCentresMm()
        assertEquals(4, centres.size)
        // TL
        assertEquals(spec.fiducialInsetMm, centres[0][0], 1e-6)
        assertEquals(spec.fiducialInsetMm, centres[0][1], 1e-6)
        // TR
        assertEquals(spec.widthMm - spec.fiducialInsetMm, centres[1][0], 1e-6)
        assertEquals(spec.fiducialInsetMm, centres[1][1], 1e-6)
    }

    @Test
    fun testPatches() {
        val rects = spec.patchRectsMm()
        assertEquals(12, rects.size)
        assertEquals(12, BadgeV2Spec.PATCHES.size)
        // All patches must be inside the badge
        for (r in rects) {
            assertTrue(r[0] >= 0 && r[0] + r[2] <= spec.widthMm)
            assertTrue(r[1] >= 0 && r[1] + r[3] <= spec.heightMm)
        }
    }

    @Test
    fun testSensingRegion() {
        val sr = spec.sensingRegionMm()
        assertTrue(sr[0] >= 0 && sr[0] + sr[2] <= spec.widthMm)
        assertTrue(sr[1] >= 0 && sr[1] + sr[3] <= spec.heightMm)
    }
}