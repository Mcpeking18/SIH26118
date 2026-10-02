#ifndef RECTIFIER_HPP
#define RECTIFIER_HPP

#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>
#include <opencv2/objdetect/aruco_detector.hpp>
#include <opencv2/objdetect/aruco_dictionary.hpp>
#include <tuple>
#include <string>
#include <vector>
#include <array>
#include <map>
#include "DosimeterTypes.hpp"

namespace dosimeter {

class Rectifier {
public:
    Rectifier();

    // Detect ArUco markers and compute homography to canonical badge plane
    // Returns DetectionResult with warped image and reprojection error
    dosimeter::DetectionResult rectify(const cv::Mat& bgr_frame);

private:
    // Parameters
    const int min_markers_ = 2;
    const float max_reproj_mm_ = 0.35f; // from spec

    // Helper functions
    cv::aruco::Dictionary get_aruco_dictionary();
    cv::aruco::DetectorParameters get_detector_parameters();
    std::map<int, std::vector<cv::Point2f>> detect_markers(const cv::Mat& gray);
    std::tuple<cv::Mat, float> solve_homography(
        const std::map<int, std::vector<cv::Point2f>>& found);
    cv::Mat warp_to_canonical(const cv::Mat& image, const cv::Mat& H);
    void validate_and_set_result(
        const std::map<int, std::vector<cv::Point2f>>& found,
        const cv::Mat& H, float rmse_mm,
        const cv::Mat& bgr_frame,
        dosimeter::DetectionResult& result);
};

} // namespace dosimeter

#endif // RECTIFIER_HPP
