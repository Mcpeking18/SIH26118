package com.mrpl.wristband.config

import org.junit.Assert.assertEquals
import org.junit.Test
import kotlin.math.abs

class WristbandSpecTest {

    private val epsilon = 1e-6

    private fun assertDoubleArrayEquals(expected: DoubleArray, actual: DoubleArray) {
        assertEquals("Array lengths differ", expected.size, actual.size)
        for (i in expected.indices) {
            assertEquals("Value at index $i differs", expected[i], actual[i], epsilon)
        }
    }

    private fun assertArrayOfDoubleArrayEquals(expected: Array<DoubleArray>, actual: Array<DoubleArray>) {
        assertEquals("Outer array lengths differ", expected.size, actual.size)
        for (i in expected.indices) {
            assertDoubleArrayEquals(expected[i], actual[i])
        }
    }

    @Test
    fun testMarkerCentresMm() {
        val spec = WristbandSpec.BADGE
        val expected = arrayOf(
            doubleArrayOf(3.5, 3.5),
            doubleArrayOf(26.5, 3.5),
            doubleArrayOf(26.5, 26.5),
            doubleArrayOf(3.5, 26.5)
        )
        assertArrayOfDoubleArrayEquals(expected, spec.markerCentresMm())
    }

    @Test
    fun testPatchCentresMm() {
        val spec = WristbandSpec.BADGE
        val expected = arrayOf(
            doubleArrayOf(15.0, 6.4),
            doubleArrayOf(19.3, 7.552181527453828),
            doubleArrayOf(22.447818472546174, 10.700000000000001),
            doubleArrayOf(23.6, 15.0),
            doubleArrayOf(22.447818472546174, 19.299999999999997),
            doubleArrayOf(19.3, 22.44781847254617),
            doubleArrayOf(15.0, 23.6),
            doubleArrayOf(10.700000000000003, 22.447818472546174),
            doubleArrayOf(7.552181527453827, 19.299999999999997),
            doubleArrayOf(6.4, 15.000000000000002),
            doubleArrayOf(7.552181527453828, 10.7),
            doubleArrayOf(10.699999999999996, 7.552181527453829)
        )
        assertArrayOfDoubleArrayEquals(expected, spec.patchCentresMm())
    }

    @Test
    fun testWhiteFieldProbesMm() {
        val spec = WristbandSpec.BADGE
        val expected = arrayOf(
            doubleArrayOf(17.583113168464358, 8.763813155548814, 0.9),
            doubleArrayOf(21.236186844451186, 12.416886831535644, 0.9),
            doubleArrayOf(21.236186844451186, 17.583113168464358, 0.9),
            doubleArrayOf(17.583113168464358, 21.236186844451186, 0.9),
            doubleArrayOf(12.416886831535644, 21.236186844451186, 0.9),
            doubleArrayOf(8.763813155548814, 17.583113168464358, 0.9),
            doubleArrayOf(8.763813155548814, 12.416886831535646, 0.9),
            doubleArrayOf(12.416886831535646, 8.763813155548814, 0.9),
            doubleArrayOf(15.0, 1.8000000000000007, 2.0),
            doubleArrayOf(28.2, 15.0, 2.0),
            doubleArrayOf(15.0, 28.2, 2.0),
            doubleArrayOf(1.8000000000000007, 15.0, 2.0)
        )
        assertArrayOfDoubleArrayEquals(expected, spec.whiteFieldProbesMm())
    }

    @Test
    fun testReferenceLabConstants() {
        // Assert that the first Reference LAB constant exactly matches the Python golden output.
        // This validates our hardcoding strategy.
        val expectedFirstLab = doubleArrayOf(95.8167475513481, -0.17623349882350814, 0.4806251140541562)
        assertDoubleArrayEquals(expectedFirstLab, WristbandSpec.REFERENCE_LAB[0])
    }
}
