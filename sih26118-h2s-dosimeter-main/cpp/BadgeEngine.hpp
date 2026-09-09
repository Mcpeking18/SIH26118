#ifndef BADGE_ENGINE_HPP
#define BADGE_ENGINE_HPP

#define _USE_MATH_DEFINES
#define _USE_MATH_DEFINES
#include <string>
#include <vector>
#include <opencv2/core.hpp>
#include <opencv2/objdetect/aruco_detector.hpp>
#include <opencv2/objdetect/aruco_dictionary.hpp>
#include "DosimeterTypes.hpp"
#include "ColorimetryUtils.hpp"
#include "Rectifier.hpp"

namespace dosimeter {

class BadgeEngine {
public:
    explicit BadgeEngine(const ScanConfig& config = ScanConfig());

    // Process a camera frame (BGR format)
    ScanResult processImage(const cv::Mat& bgr_frame);

    // Process an image file
    ScanResult processImageFile(const std::string& filepath);

private:
    ScanConfig config_;
    Rectifier rectifier_;

    // Internal processing steps
    DetectionResult detectAndRectify(const cv::Mat& bgr_frame);
    BadgeSamples sampleRegions(const cv::Mat& warped_bgr);
    PatchMetrics samplePadRegion(const cv::Mat& linear_rgb_image);
    std::vector<PatchMetrics> sampleReferencePatches(const cv::Mat& linear_rgb_image);
    std::vector<PatchMetrics> sampleWhiteFieldProbes(const cv::Mat& linear_rgb_image);
    NormalizationResult normalizeAndComputeObservables(const BadgeSamples& samples);
    DoseAssessment computeDoseAndVerdict(const NormalizationResult& norm_result);
};

} // namespace dosimeter

#endif // BADGE_ENGINE_HPP