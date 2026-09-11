package com.mrpl.wristband.color

import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.opencv.android.OpenCVLoader
import org.opencv.core.CvType
import org.opencv.core.Mat

@RunWith(AndroidJUnit4::class)
class NormalizerTest {

    @Before
    fun setUp() {
        if (!OpenCVLoader.initDebug()) {
            throw Exception("OpenCV failed to load!")
        }
    }

    @Test
    fun testRobustLstsq() {
        val aArray = arrayOf(
            doubleArrayOf(0.37454 , 0.950714, 0.731994),
            doubleArrayOf(0.598658, 0.156019, 0.155995),
            doubleArrayOf(0.058084, 0.866176, 0.601115),
            doubleArrayOf(0.708073, 0.020584, 0.96991 ),
            doubleArrayOf(0.832443, 0.212339, 0.181825),
            doubleArrayOf(0.183405, 0.304242, 0.524756),
            doubleArrayOf(0.431945, 0.291229, 0.611853),
            doubleArrayOf(0.139494, 0.292145, 0.366362),
            doubleArrayOf(0.45607 , 0.785176, 0.199674),
            doubleArrayOf(0.514234, 0.592415, 0.04645 )
        )
        val lArray = doubleArrayOf(
            1.21085, 1.135688, 0.452669, 14.412707, 1.454356, 1.521793, 2.206809, 0.896641, -0.179163, -0.263109
        )

        val A = Mat(10, 3, CvType.CV_64F)
        val L = Mat(10, 1, CvType.CV_64F)
        for (i in 0 until 10) {
            A.put(i, 0, *aArray[i])
            L.put(i, 0, lArray[i])
        }

        val (coef, nEx) = Normalizer.robustLstsq(A, L, 5)

        assertEquals(0, nEx)
        
        val row = DoubleArray(1)
        coef.get(0, 0, row); assertEquals(3.290611, row[0], 1e-4)
        coef.get(1, 0, row); assertEquals(-6.572214, row[0], 1e-4)
        coef.get(2, 0, row); assertEquals(9.138769, row[0], 1e-4)

        A.release()
        L.release()
        coef.release()
    }
}