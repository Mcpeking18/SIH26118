#ifndef COLORIMETRY_UTILS_HPP
#define COLORIMETRY_UTILS_HPP

#define _USE_MATH_DEFINES
#define _USE_MATH_DEFINES
#include <cmath>
#include <vector>
#include <array>
#include <limits>
#include <stdexcept>
#include <opencv2/core.hpp>
#include <Eigen/Dense>

namespace dosimeter {
namespace color {

// sRGB <-> linear light conversion (IEC 61966-2-1)
inline float srgb_to_linear(float c) {
    if (c <= 0.04045f) {
        return c / 12.92f;
    }
    return std::pow((c + 0.055f) / 1.055f, 2.4f);
}

inline float linear_to_srgb(float c) {
    if (c <= 0.0031308f) {
        return 12.92f * c;
    }
    return 1.055f * std::pow(c, 1.0f/2.4f) - 0.055f;
}

// Apply srgb_to_linear to a cv::Vec3b (BGR order) and return cv::Vec3f (RGB)
inline cv::Vec3f bgr_to_linear_rgb(const cv::Vec3b& bgr) {
    // Convert BGR to RGB then to linear
    cv::Vec3f rgb;
    rgb[2] = srgb_to_linear(bgr[2] / 255.0f); // R
    rgb[1] = srgb_to_linear(bgr[1] / 255.0f); // G
    rgb[0] = srgb_to_linear(bgr[0] / 255.0f); // B
    return rgb; // Note: returns RGB order
}

// Apply linear_to_srgb to a cv::Vec3f (RGB) and return cv::Vec3b (BGR)
inline cv::Vec3b linear_rgb_to_bgr(const cv::Vec3f& rgb) {
    cv::Vec3b bgr;
    bgr[2] = static_cast<uint8_t>(std::round(std::min(std::max(linear_to_srgb(rgb[2]), 0.0f), 1.0f) * 255.0f));
    bgr[1] = static_cast<uint8_t>(std::round(std::min(std::max(linear_to_srgb(rgb[1]), 0.0f), 1.0f) * 255.0f));
    bgr[0] = static_cast<uint8_t>(std::round(std::min(std::max(linear_to_srgb(rgb[0]), 0.0f), 1.0f) * 255.0f));
    return bgr; // BGR order
}

// Convert linear RGB [0,1] to XYZ (D65, 2deg)
inline cv::Vec3f linear_rgb_to_xyz(const cv::Vec3f& rgb) {
    // sRGB to XYZ D65 matrix (for D65 white point)
    // [X]   [0.4124564 0.3575761 0.1804375] [R]
    // [Y] = [0.2126729 0.7151522 0.0721750] [G]
    // [Z]   [0.0193339 0.1191920 0.9503041] [B]
    const float X = 0.4124564f * rgb[0] + 0.3575761f * rgb[1] + 0.1804375f * rgb[2];
    const float Y = 0.2126729f * rgb[0] + 0.7151522f * rgb[1] + 0.0721750f * rgb[2];
    const float Z = 0.0193339f * rgb[0] + 0.1191920f * rgb[1] + 0.9503041f * rgb[2];
    return cv::Vec3f(X, Y, Z);
}

// Convert XYZ (D65, 2deg) to linear RGB [0,1]
inline cv::Vec3f xyz_to_linear_rgb(const cv::Vec3f& xyz) {
    // Inverse of the above matrix
    // [R]   [ 3.2404542 -1.5371385 -0.4985314] [X]
    // [G] = [-0.9692660  1.8760108  0.0415560] [Y]
    // [B]   [ 0.0556434 -0.2040259  1.0572252] [Z]
    const float R =  3.2404542f * xyz[0] - 1.5371385f * xyz[1] - 0.4985314f * xyz[2];
    const float G = -0.9692660f * xyz[0] + 1.8760108f * xyz[1] + 0.0415560f * xyz[2];
    const float B =  0.0556434f * xyz[0] - 0.2040259f * xyz[1] + 1.0572252f * xyz[2];
    return cv::Vec3f(
        std::min(std::max(R, 0.0f), 1.0f),
        std::min(std::max(G, 0.0f), 1.0f),
        std::min(std::max(B, 0.0f), 1.0f)
    );
}

// Convert XYZ to CIE L*a*b* (D65, 2deg)
inline cv::Vec3f xyz_to_lab(const cv::Vec3f& xyz) {
    // Reference white point D65
    const float Xn = 0.95047f;
    const float Yn = 1.0f;
    const float Zn = 1.08883f;

    float x = xyz[0] / Xn;
    float y = xyz[1] / Yn;
    float z = xyz[2] / Zn;

    auto f = [](float t) -> float {
        if (t > std::pow(6.0f/29.0f, 3)) {
            return std::cbrt(t);
        }
        return (1.0f/3.0f) * std::pow(29.0f/6.0f, 2) * t + 4.0f/29.0f;
    };

    float L = 116.0f * f(y) - 16.0f;
    float a = 500.0f * (f(x) - f(y));
    float b = 200.0f * (f(y) - f(z));

    return cv::Vec3f(L, a, b);
}

// Convert CIE L*a*b* (D65, 2deg) to XYZ
inline cv::Vec3f lab_to_xyz(const cv::Vec3f& lab) {
    const float Xn = 0.95047f;
    const float Yn = 1.0f;
    const float Zn = 1.08883f;

    float fy = (lab[0] + 16.0f) / 116.0f;
    float fx = lab[1] / 500.0f + fy;
    float fz = fy - lab[2] / 200.0f;

    auto f_inv = [](float t) -> float {
        if (t > std::pow(6.0f/29.0f, 3)) {
            return t * t * t;
        }
        return (29.0f/6.0f) * (3.0f * t - 4.0f);
    };

    float X = Xn * f_inv(fx);
    float Y = Yn * f_inv(fy);
    float Z = Zn * f_inv(fz);

    return cv::Vec3f(X, Y, Z);
}

// Delta E CIE 2000
// Implementation based on the formula from https://www.easyrgb.com/en/math.php
// Note: This is a simplified version that assumes D65 illuminant and 2deg observer.
// For production, consider using a more accurate implementation or OpenCV's ximgproc if available.
float delta_e_ciede2000(const cv::Vec3f& lab1, const cv::Vec3f& lab2);

// Finlayson root-6 feature expansion
// Input: linear RGB (3x1)
// Output: root-6 features (6x1): [R, G, B, sqrt(R*G), sqrt(G*B), sqrt(R*B)]
inline Eigen::Matrix<float, 6, 1> root6_features(const cv::Vec3f& rgb) {
    Eigen::Matrix<float, 6, 1> f;
    f(0) = rgb[0]; // R
    f(1) = rgb[1]; // G
    f(2) = rgb[2]; // B
    f(3) = std::sqrt(rgb[0] * rgb[1]); // sqrt(R*G)
    f(4) = std::sqrt(rgb[1] * rgb[2]); // sqrt(G*B)
    f(5) = std::sqrt(rgb[0] * rgb[2]); // sqrt(R*B)
    return f;
}

// Solve for color correction matrix M (size: 3 x n_features) using ridge regression
// M = (F^T * F + lambda * I)^(-1) * F^T * Y
// where F is the design matrix (n_samples x n_features), Y is the target (n_samples x 3)
// Returns M as Eigen::Matrix<float, 3, Eigen::Dynamic> (each row is a color channel)
Eigen::Matrix<float, 3, Eigen::Dynamic> solve_ccm(
    const std::vector<cv::Vec3f>& observed,   // n_samples x 3 (linear RGB)
    const std::vector<cv::Vec3f>& reference,  // n_samples x 3 (linear RGB)
    int n_features,                           // 3 (linear), 4 (affine), 6 (root6)
    float lambda = 1e-4f                      // ridge parameter
);

// Apply CCM: M * f(x) where f(x) is the feature vector of x
// x: linear RGB (3x1)
// Returns corrected linear RGB (3x1)
inline cv::Vec3f apply_ccm(
    const Eigen::Matrix<float, 3, Eigen::Dynamic>& M,
    const cv::Vec3f& rgb,
    int n_features
) {
    Eigen::Matrix<float, Eigen::Dynamic, 1> f;
    if (n_features == 3) {
        f.resize(3);
        f << rgb[0], rgb[1], rgb[2];
    } else if (n_features == 4) {
        // affine: [1, R, G, B]
        f.resize(4);
        f << 1.0f, rgb[0], rgb[1], rgb[2];
    } else if (n_features == 6) {
        // root6: [R, G, B, sqrt(R*G), sqrt(G*B), sqrt(R*B)]
        f = root6_features(rgb);
    } else {
        throw std::invalid_argument("Unsupported number of features");
    }
    Eigen::Matrix<float, 3, 1> result = M * f;
    return cv::Vec3f(result(0), result(1), result(2));
}

// Narrowband light check: returns (level, balance, message)
// level: "ok", "warn", "reject"
// balance: min(R,G,B)/max(R,G,B) of the observed patch means
// message: descriptive string
std::tuple<std::string, float, std::string> narrowband_check(
    const std::vector<cv::Vec3f>& observed_mean_linear, // n x 3 (linear RGB)
    float warn_threshold = 0.30f,
    float reject_threshold = 0.0f
);

// Von Kries gain: diagonal gain vector to transform observed to reference
// gain = reference_mean / observed_mean (elementwise)
// Returns gain as cv::Vec3f (RGB)
cv::Vec3f von_kries_gain(
    const std::vector<cv::Vec3f>& observed,
    const std::vector<cv::Vec3f>& reference
);

} // namespace color
} // namespace dosimeter

#endif // COLORIMETRY_UTILS_HPP
