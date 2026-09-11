package com.mrpl.wristband.cv

import com.mrpl.wristband.config.WristbandSpec
import org.opencv.geometry.Geometry
import org.opencv.core.Core
import org.opencv.core.CvType
import org.opencv.core.Mat
import org.opencv.core.MatOfPoint2f
import org.opencv.core.Point
import org.opencv.core.Size
import org.opencv.imgproc.Imgproc
import org.opencv.objdetect.ArucoDetector
import org.opencv.objdetect.DetectorParameters
import org.opencv.objdetect.Objdetect
import java.util.Locale
import kotlin.math.max
import kotlin.math.sqrt

data class DetectionResult(
    val ok: Boolean,
    val reason: String,
    val foundIds: List<Int>,
    val corners: Map<Int, Mat>,
    val homography: Mat?,
    val reprojRmseMm: Double,
    val warped: Mat?
) {
    val nMarkers: Int
        get() = foundIds.size
}

class Detector(private val spec: WristbandSpec = WristbandSpec()) {

    private val dictionary = Objdetect.getPredefinedDictionary(Objdetect.DICT_4X4_50)
    private val params = tunedParams()
    private val detector = ArucoDetector(dictionary, params)

    private fun tunedParams(): DetectorParameters {
        val p = DetectorParameters()
        p.set_cornerRefinementMethod(Objdetect.CORNER_REFINE_SUBPIX)
        p.set_cornerRefinementWinSize(5)
        p.set_cornerRefinementMaxIterations(50)
        p.set_cornerRefinementMinAccuracy(0.01)
        p.set_adaptiveThreshWinSizeMin(3)
        p.set_adaptiveThreshWinSizeMax(43)
        p.set_adaptiveThreshWinSizeStep(4)
        p.set_minMarkerPerimeterRate(0.01)
        p.set_maxMarkerPerimeterRate(4.0)
        p.set_polygonalApproxAccuracyRate(0.05)
        return p
    }

    private fun detectMarkers(image: Mat): Map<Int, Mat> {
        val gray = Mat()
        if (image.channels() == 3) {
            Imgproc.cvtColor(image, gray, Imgproc.COLOR_BGR2GRAY)
        } else {
            image.copyTo(gray)
        }

        val cornersList = mutableListOf<Mat>()
        val idsMat = Mat()
        detector.detectMarkers(gray, cornersList, idsMat)

        val out = mutableMapOf<Int, Mat>()
        if (idsMat.empty()) return out

        val wanted = spec.markerIds.toSet()
        val total = idsMat.total().toInt()
        val rows = idsMat.rows()
        val cols = idsMat.cols()
        for (i in 0 until total) {
            val r = if (rows > 1) i else 0
            val c = if (cols > 1) i else 0
            val id = idsMat.get(r, c)[0].toInt()
            if (id in wanted && !out.containsKey(id)) {
                val cornerMat = cornersList[i]
                val reshaped = cornerMat.reshape(2, 4)
                val converted = Mat()
                reshaped.convertTo(converted, CvType.CV_64F)
                out[id] = converted
            }
        }
        return out
    }

    private fun solveHomography(found: Map<Int, Mat>, minMarkers: Int): Pair<Mat?, Double> {
        if (found.size < minMarkers) return Pair(null, Double.NaN)

        val dstAllMm = spec.markerOuterCornersMm()
        val idToPos = spec.markerIds.mapIndexed { index, id -> id to index }.toMap()

        val srcPoints = mutableListOf<Point>()
        val dstPoints = mutableListOf<Point>()

        for ((mid, quad) in found) {
            val pos = idToPos[mid] ?: continue
            val pxQuad = spec.mmToPx(dstAllMm[pos])

            for (i in 0 until 4) {
                val pt = quad.get(i, 0)
                srcPoints.add(Point(pt[0], pt[1]))
                dstPoints.add(Point(pxQuad[i][0], pxQuad[i][1]))
            }
        }

        val srcMat = MatOfPoint2f(*srcPoints.toTypedArray())
        val dstMat = MatOfPoint2f(*dstPoints.toTypedArray())

        val H = Geometry.findHomography(srcMat, dstMat, 0)
        if (H.empty()) return Pair(null, Double.NaN)

        val proj = MatOfPoint2f()
        Core.perspectiveTransform(srcMat, proj, H)

        val projArray = proj.toArray()
        val dstArray = dstMat.toArray()
        var sumSq = 0.0
        for (i in projArray.indices) {
            val dx = projArray[i].x - dstArray[i].x
            val dy = projArray[i].y - dstArray[i].y
            sumSq += dx * dx + dy * dy
        }
        val rmsePx = sqrt(sumSq / projArray.size)
        return Pair(H, rmsePx / spec.pxPerMm)
    }

    private fun warpToCanonical(image: Mat, H: Mat): Mat {
        val n = spec.canonicalPx
        val h = image.rows()
        val w = image.cols()
        val srcSpan = max(h, w)
        val flags = if (srcSpan > n * 1.2) Imgproc.INTER_AREA else Imgproc.INTER_LINEAR

        val warped = Mat()
        Imgproc.warpPerspective(
            image, warped, H, Size(n.toDouble(), n.toDouble()),
            flags, Core.BORDER_CONSTANT, org.opencv.core.Scalar(0.0, 0.0, 0.0)
        )
        return warped
    }

    fun rectify(image: Mat, minMarkers: Int = 2, maxReprojMm: Double = 0.35): DetectionResult {
        val found = detectMarkers(image)
        val foundIds = found.keys.sorted()

        if (found.size < minMarkers) {
            return DetectionResult(
                ok = false,
                reason = "found ${found.size} of ${spec.markerIds.size} fiducials, need $minMarkers - move closer, wipe the badge, or add light",
                foundIds = foundIds,
                corners = found,
                homography = null,
                reprojRmseMm = Double.NaN,
                warped = null
            )
        }

        val (H, rmseMm) = solveHomography(found, minMarkers)
        if (H == null) {
            return DetectionResult(
                ok = false,
                reason = "degenerate marker geometry, homography could not be solved",
                foundIds = foundIds,
                corners = found,
                homography = null,
                reprojRmseMm = Double.NaN,
                warped = null
            )
        }

        if (rmseMm.isNaN() || rmseMm > maxReprojMm) {
            return DetectionResult(
                ok = false,
                reason = String.format(Locale.US, "geometry unstable: %.3f mm reprojection RMSE exceeds %.2f mm - hold the camera steadier / flatter", rmseMm, maxReprojMm),
                foundIds = foundIds,
                corners = found,
                homography = H,
                reprojRmseMm = rmseMm,
                warped = null
            )
        }

        val warped = warpToCanonical(image, H)
        return DetectionResult(
            ok = true,
            reason = "ok",
            foundIds = foundIds,
            corners = found,
            homography = H,
            reprojRmseMm = rmseMm,
            warped = warped
        )
    }
}
