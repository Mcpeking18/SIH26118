package com.mrpl.wristband.config

import org.junit.Assert.*
import org.junit.Test

class BadgeV2SpecTest {

    private val spec = BadgeV2Spec.BADGE

    @Test
    fun testDimensions() {
        assertEquals(30.0, spec.widthMm, 1e-6)
        assertEquals(40.0, spec.heightMm, 1e-6)
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
        for (r in rects) {
            assertTrue(r[0] >= 0 && r[0] + r[2] <= spec.widthMm)
            assertTrue(r[1] >= 0 && r[1] + r[3] <= spec.heightMm)
        }
    }

    @Test
    fun testNoOverlaps() {
        val patches = spec.patchRectsMm()
        val fiducials = spec.markerOuterCornersMm().map { corners -> 
            val x = corners[0][0]
            val y = corners[0][1]
            val w = corners[2][0] - x
            val h = corners[2][1] - y
            arrayOf(x, y, w, h)
        }.toTypedArray()
        val sensor = spec.sensingRegionMm()
        
        fun overlap(r1: Array<Double>, r2: Array<Double>): Boolean {
            val x1 = r1[0]; val y1 = r1[1]; val w1 = r1[2]; val h1 = r1[3]
            val x2 = r2[0]; val y2 = r2[1]; val w2 = r2[2]; val h2 = r2[3]
            return !(x1 + w1 <= x2 + 1e-6 || x2 + w2 <= x1 + 1e-6 || y1 + h1 <= y2 + 1e-6 || y2 + h2 <= y1 + 1e-6)
        }
        
        for (p in patches) {
            for (f in fiducials) {
                assertFalse("Patch overlaps fiducial", overlap(p, f))
            }
            assertFalse("Patch overlaps sensor", overlap(p, sensor))
        }
        for (f in fiducials) {
            assertFalse("Fiducial overlaps sensor", overlap(f, sensor))
        }
        for (i in 0 until patches.size) {
            for (j in i+1 until patches.size) {
                assertFalse("Patch overlaps patch", overlap(patches[i], patches[j]))
            }
        }
    }

    @Test
    fun testOrientationAndCrossShape() {
        val rects = spec.patchRectsMm()
        
        // All patches should be square (4.0 x 4.0)
        for (i in rects.indices) {
            val w = rects[i][2]
            val h = rects[i][3]
            assertEquals("Patch $i should be a perfect square", w, h, 1e-6)
            assertEquals("Patch $i should be 4.0 mm", 4.0, w, 1e-6)
        }
        
        // Top arm (P1, P2) - indices 0, 1
        for (i in 0..1) {
            assertTrue("Top patch $i should be above sensor center", rects[i][1] < 20.0)
        }
        
        // Right arm (P3, P4, P5, P6) - indices 2, 3, 4, 5
        for (i in 2..5) {
            assertTrue("Right patch $i should be right of sensor center", rects[i][0] > 15.0)
        }

        // Bottom arm (P7, P8) - indices 6, 7
        for (i in 6..7) {
            assertTrue("Bottom patch $i should be below sensor center", rects[i][1] > 20.0)
        }

        // Left arm (P9, P10, P11, P12) - indices 8, 9, 10, 11
        for (i in 8..11) {
            assertTrue("Left patch $i should be left of sensor center", rects[i][0] < 15.0)
        }
    }
}
