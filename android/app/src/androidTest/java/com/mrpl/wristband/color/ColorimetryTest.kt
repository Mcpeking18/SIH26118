package com.mrpl.wristband.color

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.opencv.android.OpenCVLoader
import org.junit.Before

@RunWith(AndroidJUnit4::class)
class ColorimetryTest {

    @Before
    fun setUp() {
        if (!OpenCVLoader.initDebug()) {
            throw Exception("OpenCV failed to load!")
        }
    }

    @Test
    fun testCIEDE2000() {
        val lab1 = doubleArrayOf(50.0, 2.0, -3.0)
        val lab2 = doubleArrayOf(52.0, 1.5, -4.0)
        val dE1 = Colorimetry.deltaECIEDE2000(lab1, lab2)
        assertEquals(2.3213996689487, dE1, 1e-6)

        val lab3 = doubleArrayOf(2.0, 50.0, -50.0)
        val lab4 = doubleArrayOf(1.5, 52.0, -52.0)
        val dE2 = Colorimetry.deltaECIEDE2000(lab3, lab4)
        assertEquals(0.7268265196363484, dE2, 1e-6)
    }

    @Test
    fun testSolveCcmRoot6() {
        val obs = arrayOf(
            doubleArrayOf(0.399632, 0.860571, 0.685595),
            doubleArrayOf(0.578927, 0.224815, 0.224796),
            doubleArrayOf(0.146467, 0.792941, 0.580892),
            doubleArrayOf(0.666458, 0.116468, 0.875928),
            doubleArrayOf(0.765954, 0.269871, 0.24546 ),
            doubleArrayOf(0.246724, 0.343394, 0.519805),
            doubleArrayOf(0.445556, 0.332983, 0.589482),
            doubleArrayOf(0.211595, 0.333716, 0.393089),
            doubleArrayOf(0.464856, 0.728141, 0.259739),
            doubleArrayOf(0.511388, 0.573932, 0.13716 ),
            doubleArrayOf(0.586036, 0.236419, 0.152041),
            doubleArrayOf(0.859108, 0.872506, 0.746718)
        )
        val ref = arrayOf(
            doubleArrayOf(0.343691, 0.178138, 0.647386),
            doubleArrayOf(0.452122, 0.197631, 0.496142),
            doubleArrayOf(0.127511, 0.827456, 0.307024),
            doubleArrayOf(0.630018, 0.349369, 0.516054),
            doubleArrayOf(0.537368, 0.247884, 0.875668),
            doubleArrayOf(0.720106, 0.851599, 0.815862),
            doubleArrayOf(0.57832 , 0.837499, 0.170794),
            doubleArrayOf(0.256786, 0.136182, 0.360264),
            doubleArrayOf(0.410942, 0.317079, 0.76299 ),
            doubleArrayOf(0.385403, 0.324748, 0.534157),
            doubleArrayOf(0.212739, 0.741758, 0.159641),
            doubleArrayOf(0.88951 , 0.717796, 0.258973)
        )

        val M = Colorimetry.solveCcm(obs, ref, "root6", 1e-4)

        val expected = arrayOf(
            doubleArrayOf(-0.2269966243182744, 2.1322401836989138, 1.8663368495267847),
            doubleArrayOf(-1.771203326270122, -2.5802435781059727, 0.0926849770854363),
            doubleArrayOf(1.899589518863592, 5.630738545814589, 3.7974738905350702),
            doubleArrayOf(3.497099561537528, 4.447018806032012, 1.9058728680090093),
            doubleArrayOf(-0.2571343745943176, 0.36928009793164185, -1.7078367162172396),
            doubleArrayOf(-2.0279107672614476, -9.186592601577846, -5.274644901054124)
        )

        val row = DoubleArray(3)
        for (i in 0 until 6) {
            M.get(i, 0, row)
            for (j in 0 until 3) {
                assertEquals("Mismatch at row \$i, col \$j", expected[i][j], row[j], 1e-4)
            }
        }
        M.release()
    }
}
