#include "Rectifier.hpp"

namespace dosimeter {

Rectifier::Rectifier() {}

cv::aruco::Dictionary Rectifier::get_aruco_dictionary() {
    // Use DICT_4X4_50 as per typical badge design
    return cv::aruco::getPredefinedDictionary(cv::aruco::DICT_4X4_50);
}

cv::aruco::DetectorParameters Rectifier::get_detector_parameters() {
    // Create a DetectorParameters object using its constructor
    return cv::aruco::DetectorParameters();
}

std::map<int, std::vector<cv::Point2f>> Rectifier::detect_markers(const cv::Mat& gray) {
    std::map<int, std::vector<cv::Point2f>> markers;
    auto dict = get_aruco_dictionary();
    auto params = get_detector_parameters();
    
    // Create an ArucoDetector instance
    cv::aruco::ArucoDetector detector(dict, params);
    std::vector<int> ids;
    std::vector<std::vector<cv::Point2f>> corners;
    detector.detectMarkers(gray, corners, ids);
    
    for (size_t i = 0; i < ids.size(); ++i) {
        markers[ids[i]] = corners[i];
    }
    return markers;
}

std::tuple<cv::Mat, float> Rectifier::solve_homography(
    const std::map<int, std::vector<cv::Point2f>>& found) {
    // For now, return an identity matrix and zero error.
    // In a real implementation, we would compute homography from marker points.
    cv::Mat H = cv::Mat::eye(3, 3, CV_64F);
    float rmse_mm = 0.0f;
    return std::make_tuple(H, rmse_mm);
}

cv::Mat Rectifier::warp_to_canonical(const cv::Mat& image, const cv::Mat& H) {
    cv::Mat warped;
    cv::warpPerspective(image, warped, H, cv::Size(600, 600));
    return warped;
}

void Rectifier::validate_and_set_result(
    const std::map<int, std::vector<cv::Point2f>>& found,
    const cv::Mat& H, float rmse_mm,
    const cv::Mat& bgr_frame,
    dosimeter::DetectionResult& result) {
    result.warped = warp_to_canonical(bgr_frame, H);
    result.reproj_rmse_mm = rmse_mm;
    result.ok = (found.size() >= static_cast<size_t>(min_markers_) && rmse_mm <= max_reproj_mm_);
    if (!result.ok) {
        if (found.size() < static_cast<size_t>(min_markers_)) {
            result.reason = "Not enough markers";
        } else {
            result.reason = "Reprojection error too high";
        }
    } else {
        result.reason = "";
    }
}

dosimeter::DetectionResult Rectifier::rectify(const cv::Mat& bgr_frame) {
    DetectionResult result;
    result.ok = false;
    result.reason = "";

    if (bgr_frame.empty()) {
        result.reason = "Empty image";
        return result;
    }

    cv::Mat gray;
    cv::cvtColor(bgr_frame, gray, cv::COLOR_BGR2GRAY);

    auto found = detect_markers(gray);
    auto [H, rmse_mm] = solve_homography(found);
    validate_and_set_result(found, H, rmse_mm, bgr_frame, result);

    return result;
}

} // namespace dosimeter
