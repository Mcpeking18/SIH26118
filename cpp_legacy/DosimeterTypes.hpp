#ifndef DOSIMETER_TYPES_HPP
#define DOSIMETER_TYPES_HPP

#include <cstdint>
#include <string>
#include <vector>
#include <array>
#include <opencv2/core.hpp>

namespace dosimeter {

// Enums
enum class Verdict {
    SAFE,
    WARNING,
    CRITICAL,
    SATURATED,
    SUSPECT,
    INVALID
};

enum class StageFailed {
    NONE,
    PAD_GLARE,
    PAD_UNDEREXPOSURE,
    SPATIAL_NON_UNIFORMITY,
    NEUTRAL_MONOTONICITY,
    NARROWBAND_LIGHT,
    CHROMA_RESIDUAL,
    SATURATION,
    TWA_EXCEEDS,
    STEL_EXCEEDS
};

// Structs
struct LabColor {
    float L;
    float a;
    float b;

    LabColor() : L(0), a(0), b(0) {}
    LabColor(float L, float a, float b) : L(L), a(a), b(b) {}
};

struct PatchMetrics {
    std::string name;
    cv::Vec3f mean_linear;   // RGB in [0,1] linear light
    cv::Vec3f median_linear;
    cv::Vec3f std_linear;
    int n_pixels;
    int n_total;
    float clip_fraction;    // fraction at/near 255 (glare)
    float black_fraction;   // fraction at/near 0 (shadow)
    float luminance;        // Rec.709 luminance of mean_linear
    LabColor lab;           // CIE L*a*b* of mean_linear
    float cv_percent;       // coefficient of variation (%)

    PatchMetrics() : n_pixels(0), n_total(0), clip_fraction(0), black_fraction(0), luminance(0), cv_percent(0) {}
};

struct ScanConfig {
    float pad_sample_fraction = 0.70f;    // fraction of pad radius to sample
    float patch_sample_fraction = 0.70f;  // fraction of patch side to sample
    float trim_fraction = 0.20f;          // luminance trimming (keep central 60%)
    int clip_threshold = 254;             // sRGB threshold for glare detection
    int black_threshold = 2;              // sRGB threshold for shadow detection
    float max_clip_fraction = 0.15f;      // reject if >15% of pad pixels clipped
    float max_pad_cv_percent = 25.0f;     // reject if pad CV% > 25%
    float max_reproj_mm = 0.35f;          // max homography reprojection error (mm)
    float warn_loo_residual = 8.0f;       // warn if mean leave-one-out residual > 8 dE00
    float warn_locus_residual = 2.0f;     // warn if locus-weighted residual > 2 dE00
    float warn_channel_balance = 0.30f;   // warn if channel balance < 0.30 (narrowband light)
    float reject_channel_balance = 0.0f;  // reject if channel balance < 0.0 (disabled by default)
    float flat_field_gradient_limit = 35.0f; // reject if illumination gradient > 35%
    float chroma_limit_floor = 5.0f;      // absolute chroma residual floor (dE00)
    float chroma_limit_slope = 0.40f;     // chroma limit slope vs delta_L*
    float shift_hours = 8.0f;             // shift length for TWA calculation (hours)
    float temp_c = 25.0f;                 // temperature for environmental compensation (°C)
    float rh_fraction = 0.50f;            // relative humidity for environmental compensation (0-1)

    ScanConfig() = default;
};

struct ScanResult {
    bool ok;
    std::string reason;
    Verdict verdict;
    StageFailed stage_failed;

    // Geometry
    cv::Mat warped_image;                 // rectified canonical image (600x600)
    float reproj_rmse_mm;                 // homography reprojection error (mm)

    // Photometry
    LabColor pad_lab;                     // corrected pad CIE L*a*b*
    LabColor baseline_lab;                // baseline CIE L*a*b* (from substrate patches)
    float delta_l_star;                   // baseline_L - pad_L (positive = darkening)
    float locus_projection;               // signed displacement along reaction path
    float chroma_residual;                // off-locus chroma displacement
    float delta_e00;                      // CIEDE2000 between pad and baseline

    // Dose
    float raw_dose_ppm_hr;                // dose before environmental compensation
    float final_dose_ppm_hr;              // dose after environmental compensation
    float twa_ppm;                        // time-weighted average concentration

    // Quality metrics
    float pad_clip_fraction;              // fraction of pad pixels clipped
    float pad_black_fraction;             // fraction of pad pixels black
    float pad_cv_percent;                 // pad coefficient of variation (%)
    float channel_balance;                // min(R,G,B)/max(R,G,B) of patch means
    std::string light_quality;            // "ok", "warn", "reject" for narrowband light
    float loo_residual_mean;              // mean leave-one-out residual (dE00)
    float loo_residual_max;               // max leave-one-out residual (dE00)
    float locus_residual;                 // locus-weighted leave-one-out residual (dE00)
    float locus_l_bias;                   // locus-weighted signed L* bias (L* units)
    float condition_number;               // condition number of CCM design matrix
    float gradient_percent;               // peak-to-peak illumination variation (%)

    // Reference patch data (for debugging)
    std::vector<PatchMetrics> patches;    // 12 patches in order P0..P11
    std::vector<PatchMetrics> white_field; // white-field probe measurements

    ScanResult() :
        ok(false),
        reason(""),
        verdict(Verdict::INVALID),
        stage_failed(StageFailed::NONE),
        reproj_rmse_mm(0),
        delta_l_star(0),
        locus_projection(0),
        chroma_residual(0),
        delta_e00(0),
        raw_dose_ppm_hr(0),
        final_dose_ppm_hr(0),
        twa_ppm(0),
        pad_clip_fraction(0),
        pad_black_fraction(0),
        pad_cv_percent(0),
        channel_balance(0),
        light_quality("ok"),
        loo_residual_mean(0),
        loo_residual_max(0),
        locus_residual(0),
        locus_l_bias(0),
        condition_number(0),
        gradient_percent(0) {}
};

// Internal pipeline structs
struct DetectionResult {
    cv::Mat warped;                 // rectified canonical image (600x600)
    float reproj_rmse_mm;           // homography reprojection error (mm)
    bool ok;
    std::string reason;
};

struct BadgeSamples {
    PatchMetrics pad;
    std::vector<PatchMetrics> patches;   // 12 patches in order P0..P11
    std::vector<PatchMetrics> white_field; // white-field probe measurements
};

struct NormalizationResult {
    LabColor pad_lab;
    LabColor baseline_lab;
    float delta_l_star;         // baseline_L - pad_L
    float locus_projection;     // signed displacement along reaction path
    float chroma_residual;      // off-locus chroma displacement
    float delta_e00;            // CIEDE2000 between pad and baseline
    float condition_number;     // condition number of CCM design matrix
    float channel_balance;      // min(R,G,B)/max(R,G,B) of patch means
    std::string light_quality;  // "ok", "warn", "reject" for narrowband light
    float loo_residual_mean;    // mean leave-one-out residual (dE00)
    float loo_residual_max;     // max leave-one-out residual (dE00)
    float locus_residual;       // locus-weighted leave-one-out residual (dE00)
    float locus_l_bias;         // locus-weighted signed L* bias (L* units)
    float gradient_percent;     // peak-to-peak illumination variation (%)
    bool ok;
    std::string reason;
};

struct DoseAssessment {
    Verdict verdict;
    float dose_ppm_hr;          // final dose in ppm*hr (after environmental compensation)
    float twa_ppm;              // time-weighted average concentration (ppm)
};

} // namespace dosimeter

#endif // DOSIMETER_TYPES_HPP