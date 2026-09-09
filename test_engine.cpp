#include <iostream>
#include <fstream>
#include "BadgeEngine.hpp"
#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <image_path>" << std::endl;
        return 1;
    }

    std::string image_path = argv[1];
    cv::Mat image = cv::imread(image_path, cv::IMREAD_COLOR);
    if (image.empty()) {
        std::cerr << "Failed to load image: " << image_path << std::endl;
        return 1;
    }

    dosimeter::ScanConfig config;
    dosimeter::BadgeEngine engine(config);
    dosimeter::ScanResult result = engine.processImage(image);

    // Output as JSON for easy parsing
    std::cout << "{"
              << "\"ok\":" << (result.ok ? "true" : "false") << ","
              << "\"reason\":\"" << result.reason << "\","
              << "\"verdict\":\"" 
              << [&result]() {
                  switch (result.verdict) {
                      case dosimeter::Verdict::SAFE: return "SAFE";
                      case dosimeter::Verdict::WARNING: return "WARNING";
                      case dosimeter::Verdict::CRITICAL: return "CRITICAL";
                      case dosimeter::Verdict::SATURATED: return "SATURATED";
                      case dosimeter::Verdict::SUSPECT: return "SUSPECT";
                      case dosimeter::Verdict::INVALID: return "INVALID";
                      default: return "UNKNOWN";
                  }
              }() << "\","
              << "\"stage_failed\":\"" 
              << [&result]() {
                  switch (result.stage_failed) {
                      case dosimeter::StageFailed::NONE: return "NONE";
                      case dosimeter::StageFailed::PAD_GLARE: return "PAD_GLARE";
                      case dosimeter::StageFailed::PAD_UNDEREXPOSURE: return "PAD_UNDEREXPOSURE";
                      case dosimeter::StageFailed::SPATIAL_NON_UNIFORMITY: return "SPATIAL_NON_UNIFORMITY";
                      case dosimeter::StageFailed::NEUTRAL_MONOTONICITY: return "NEUTRAL_MONOTONICITY";
                      case dosimeter::StageFailed::NARROWBAND_LIGHT: return "NARROWBAND_LIGHT";
                      case dosimeter::StageFailed::CHROMA_RESIDUAL: return "CHROMA_RESIDUAL";
                      case dosimeter::StageFailed::SATURATION: return "SATURATION";
                      case dosimeter::StageFailed::TWA_EXCEEDS: return "TWA_EXCEEDS";
                      case dosimeter::StageFailed::STEL_EXCEEDS: return "STEL_EXCEEDS";
                      default: return "UNKNOWN";
                  }
              }() << "\","
              << "\"reproj_rmse_mm\":" << result.reproj_rmse_mm << ","
              << "\"delta_l_star\":" << result.delta_l_star << ","
              << "\"locus_projection\":" << result.locus_projection << ","
              << "\"chroma_residual\":" << result.chroma_residual << ","
              << "\"delta_e00\":" << result.delta_e00 << ","
              << "\"raw_dose_ppm_hr\":" << result.raw_dose_ppm_hr << ","
              << "\"final_dose_ppm_hr\":" << result.final_dose_ppm_hr << ","
              << "\"twa_ppm\":" << result.twa_ppm << ","
              << "\"channel_balance\":" << result.channel_balance << ","
              << "\"light_quality\":\"" << result.light_quality << "\","
              << "\"loo_residual_mean\":" << result.loo_residual_mean << ","
              << "\"gradient_percent\":" << result.gradient_percent
              << "}" << std::endl;

    return 0;
}
