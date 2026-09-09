#include <jni.h>
#include <string>
#include <vector>
#include <opencv2/core.hpp>
#include <opencv2/imgcodecs.hpp>
#include "BadgeEngine.hpp"
#include "DosimeterTypes.hpp"

extern "C" {

// Helper function to convert ScanResult to Java-friendly format
// In a real implementation, this would populate a Java object via JNI
// For now, we'll return a JSON string that can be parsed by Java

std::string scanResultToJson(const dosimeter::ScanResult& result) {
    std::string json = "{";
    json += "\"ok\":" + std::string(result.ok ? "true" : "false") + ",";
    json += "\"reason\":\"" + result.reason + "\",";
    json += "\"verdict\":\"" +
        [&result]() {
            switch (result.verdict) {
                case dosimeter::Verdict::SAFE: return "SAFE";
                case dosimeter::Verdict::WARNING: return "WARNING";
                case dosimeter::Verdict::CRITICAL: return "CRITICAL";
                case dosimeter::Verdict::SATURATED: return "SATURATED";
                case dosimeter::Verdict::SUSPECT: return "SUSPECT";
                case dosimeter::Verdict::INVALID: return "INVALID";
                default: return "UNKNOWN";
            }
        }() + "\",";
    json += "\"stage_failed\":\"" +
        [&result]() {
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
        }() + "\",";
    json += "\"reproj_rmse_mm\":" + std::to_string(result.reproj_rmse_mm) + ",";
    json += "\"delta_L_star\":" + std::to_string(result.delta_L_star) + ",";
    json += "\"locus_projection\":" + std::to_string(result.locus_projection) + ",";
    json += "\"chroma_residual\":" + std::to_string(result.chroma_residual) + ",";
    json += "\"delta_e00\":" + std::to_string(result.delta_e00) + ",";
    json += "\"raw_dose_ppm_hr\":" + std::to_string(result.raw_dose_ppm_hr) + ",";
    json += "\"final_dose_ppm_hr\":" + std::to_string(result.final_dose_ppm_hr) + ",";
    json += "\"twa_ppm\":" + std::to_string(result.twa_ppm) + ",";
    json += "\"channel_balance\":" + std::to_string(result.channel_balance) + ",";
    json += "\"light_quality\":\"" + result.light_quality + "\",";
    json += "\"loo_residual_mean\":" + std::to_string(result.loo_residual_mean) + ",";
    json += "\"gradient_percent\":" + std::to_string(result.gradient_percent) + "}";

    return json;
}

// JNI function to process a byte array (JPEG image)
JNIEXPORT jstring JNICALL
Java_com_example_dosimeter_DosometerNative_processImage(
        JNIEnv* env,
        jobject /* this */,
        jbyteArray imageData,
        jint width,
        jint height,
        jint format) { // 0 = JPEG, 1 = NV21, etc.

    // Convert byte array to OpenCV Mat
    jbyte* data = env->GetByteArrayElements(imageData, nullptr);
    jsize length = env->GetArrayLength(imageData);

    cv::Mat image;
    if (format == 0) { // JPEG
        image = cv::imdecode(cv::Mat(length, 1, CV_8UC1, data), cv::IMREAD_COLOR);
    } else if (format == 1) { // NV21
        cv::Mat yuv(height + height/2, width, CV_8UC1, data);
        cv::cvtColor(yuv, image, cv::COLOR_YUV2BGR_NV21);
    } else {
        // Default to grayscale
        image = cv::Mat(height, width, CV_8UC1, data);
    }

    env->ReleaseByteArrayElements(imageData, data, JNI_ABORT);

    if (image.empty()) {
        return env->NewStringUTF("{\"ok\":false,\"reason\":\"Failed to decode image\"}");
    }

    // Process the image
    dosimeter::ScanConfig config;
    dosimeter::BadgeEngine engine(config);
    dosimeter::ScanResult result = engine.processImage(image);

    // Convert to JSON and return
    std::string json = scanResultToJson(result);
    return env->NewStringUTF(json.c_str());
}

// JNI function to process an image file path
JNIEXPORT jstring JNICALL
Java_com_example_dosimeter_DosometerNative_processImageFile(
        JNIEnv* env,
        jobject /* this */,
        jstring filePath) {

    const char* nativePath = env->GetStringUTFChars(filePath, nullptr);
    std::string path(nativePath);
    env->ReleaseStringUTFChars(filePath, nativePath);

    dosimeter::ScanConfig config;
    dosimeter::BadgeEngine engine(config);
    dosimeter::ScanResult result = engine.processImageFile(path);

    std::string json = scanResultToJson(result);
    return env->NewStringUTF(json.c_str());
}

} // extern "C"