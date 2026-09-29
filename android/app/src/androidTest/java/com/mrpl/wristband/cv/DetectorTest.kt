package com.mrpl.wristband.cv

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.mrpl.wristband.config.BadgeV2Spec
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.opencv.android.OpenCVLoader
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.Scalar
import org.opencv.objdetect.Objdetect

@RunWith(AndroidJUnit4::class)
class DetectorTest {

    @Before
    fun setUp() {
        assertTrue("OpenCV failed to load!", OpenCVLoader.initLocal())
    }

    @Test
    fun testRectifySyntheticImage() {
        val spec = BadgeV2Spec.BADGE
        val dict = Objdetect.getPredefinedDictionary(Objdetect.DICT_4X4_50)
        
        val frame = Mat(1000, 1000, CvType.CV_8UC1, Scalar(255.0))
        
        val scale = 15.0
        val center = org.opencv.core.Point(500.0, 500.0)
        
        for (i in spec.markerIds.indices) {
            val id = spec.markerIds[i]
            val markerSizeMm = spec.fiducialSizeMm
            val sidePx = (markerSizeMm * scale).toInt()
            val markerImg = Mat()
            Objdetect.generateImageMarker(dict, id, sidePx, markerImg, 1)
            
            val corners = spec.markerOuterCornersMm()[i]
            val tlX = center.x + corners[0][0] * scale
            val tlY = center.y + corners[0][1] * scale
            
            val rTarget = org.opencv.core.Rect(tlX.toInt(), tlY.toInt(), sidePx, sidePx)
            val submat = frame.submat(rTarget)
            markerImg.copyTo(submat)
        }
        
        val detector = Detector(spec)
        val res = detector.rectify(frame)
        
        assertTrue(res.reason, res.ok)
        assertEquals("ok", res.reason)
        assertEquals(4, res.foundIds.size)
        assertNotNull(res.homography)
        assertTrue(res.reprojRmseMm < 0.35)
        
        assertNotNull(res.warped)
        assertEquals(spec.widthPx, res.warped!!.cols())
        assertEquals(spec.heightPx, res.warped!!.rows())
    }
}
