#include "ColorimetryUtils.hpp"
#include <algorithm>
#include <numeric>
#include <cmath>
#include <limits>

namespace dosimeter {
namespace color {

float delta_e_ciede2000(const cv::Vec3f& lab1, const cv::Vec3f& lab2) {
    // CIEDE2000 implementation
    // Based on the formula from Sharma, Wu, and Dalal (2005)

    // L*a*b* values
    float L1 = lab1[0], a1 = lab1[1], b1 = lab1[2];
    float L2 = lab2[0], a2 = lab2[1], b2 = lab2[2];

    // Constants
    const float kL = 1.0f;
    const float kC = 1.0f;
    const float kH = 1.0f;

    // Calculate C1, C2
    float C1 = std::sqrt(a1*a1 + b1*b1);
    float C2 = std::sqrt(a2*a2 + b2*b2);

    // Calculate Cbar
    float Cbar = (C1 + C2) / 2.0f;

    // Calculate G
    float G = 0.5f * (1.0f - std::sqrt(std::pow(Cbar, 7.0f) / (std::pow(Cbar, 7.0f) + std::pow(25.0f, 7.0f))));

    // Calculate a1', a2'
    float a1p = (1.0f + G) * a1;
    float a2p = (1.0f + G) * a2;

    // Calculate C1', C2'
    float C1p = std::sqrt(a1p*a1p + b1*b1);
    float C2p = std::sqrt(a2p*a2p + b2*b2);

    // Calculate h1', h2'
    float h1p = std::atan2(b1, a1p);
    if (h1p < 0.0f) h1p += 2.0f * static_cast<float>(M_PI);

    float h2p = std::atan2(b2, a2p);
    if (h2p < 0.0f) h2p += 2.0f * static_cast<float>(M_PI);

    // Calculate delta L', delta C', delta H'
    float deltaLp = L2 - L1;
    float deltaCp = C2p - C1p;

    float deltaHp;
    if (C1p * C2p == 0.0f) {
        deltaHp = 0.0f;
    } else {
        if (std::abs(h2p - h1p) <= static_cast<float>(M_PI)) {
            deltaHp = h2p - h1p;
        } else if (h2p - h1p > static_cast<float>(M_PI)) {
            deltaHp = h2p - h1p - 2.0f * static_cast<float>(M_PI);
        } else {
            deltaHp = h2p - h1p + 2.0f * static_cast<float>(M_PI);
        }
        deltaHp = 2.0f * std::sqrt(C1p * C2p) * std::sin(deltaHp / 2.0f);
    }

    // Calculate Lbar, Cbar, hbar
    float Lbarp = (L1 + L2) / 2.0f;
    float Cbarp = (C1p + C2p) / 2.0f;

    float hbarp;
    if (C1p * C2p == 0.0f) {
        hbarp = h1p + h2p;
    } else {
        if (std::abs(h1p - h2p) <= static_cast<float>(M_PI)) {
            hbarp = (h1p + h2p) / 2.0f;
        } else if (h1p + h2p < 2.0f * static_cast<float>(M_PI)) {
            hbarp = (h1p + h2p + 2.0f * static_cast<float>(M_PI)) / 2.0f;
        } else {
            hbarp = (h1p + h2p - 2.0f * static_cast<float>(M_PI)) / 2.0f;
        }
    }

    // Calculate T
    float T = 1.0f
              - 0.17f * std::cos(hbarp - static_cast<float>(M_PI/6.0f))
              + 0.24f * std::cos(2.0f * hbarp)
              + 0.32f * std::cos(3.0f * hbarp + static_cast<float>(M_PI/30.0f))
              - 0.20f * std::cos(4.0f * hbarp - static_cast<float>(M_PI*7.0f/20.0f));

    // Calculate SL, SC, SH
    float SL = 1.0f + (0.015f * std::pow(Lbarp - 50.0f, 2.0f)) /
               std::sqrt(20.0f + std::pow(Lbarp - 50.0f, 2.0f));
    float SC = 1.0f + 0.045f * Cbarp;
    float SH = 1.0f + 0.015f * Cbarp * T;

    // Calculate delta theta
    float delta_theta = static_cast<float>(M_PI) / 6.0f * std::exp(-std::pow((180.0f / static_cast<float>(M_PI) * hbarp - 275.0f) / 25.0f, 2.0f));

    // Calculate RT
    float RC = 2.0f * std::sqrt(std::pow(Cbarp, 7.0f) / (std::pow(Cbarp, 7.0f) + std::pow(25.0f, 7.0f)));
    float RT = -std::sin(2.0f * delta_theta) * RC;

    // Calculate delta E
    float deltaE = std::sqrt(
        std::pow(deltaLp / (kL * SL), 2.0f) +
        std::pow(deltaCp / (kC * SC), 2.0f) +
        std::pow(deltaHp / (kH * SH), 2.0f) +
        RT * (deltaCp / (kC * SC)) * (deltaHp / (kH * SH))
    );

    return deltaE;
}

Eigen::Matrix<float, 3, Eigen::Dynamic> solve_ccm(
    const std::vector<cv::Vec3f>& observed,
    const std::vector<cv::Vec3f>& reference,
    int n_features,
    float lambda
) {
    if (observed.size() != reference.size()) {
        throw std::invalid_argument("Observed and reference vectors must have the same size");
    }

    int n_samples = observed.size();
    if (n_samples < n_features) {
        throw std::invalid_argument("Not enough samples for the number of features");
    }

    // Build design matrix F (n_samples x n_features)
    Eigen::MatrixXf F(n_samples, n_features);
    for (int i = 0; i < n_samples; ++i) {
        const cv::Vec3f& rgb = observed[i];
        if (n_features == 3) {
            // Linear: [R, G, B]
            F(i, 0) = rgb[0];
            F(i, 1) = rgb[1];
            F(i, 2) = rgb[2];
        } else if (n_features == 4) {
            // Affine: [1, R, G, B]
            F(i, 0) = 1.0f;
            F(i, 1) = rgb[0];
            F(i, 2) = rgb[1];
            F(i, 3) = rgb[2];
        } else if (n_features == 6) {
            // Root6: [R, G, B, sqrt(R*G), sqrt(G*B), sqrt(R*B)]
            F(i, 0) = rgb[0];
            F(i, 1) = rgb[1];
            F(i, 2) = rgb[2];
            F(i, 3) = std::sqrt(rgb[0] * rgb[1]);
            F(i, 4) = std::sqrt(rgb[1] * rgb[2]);
            F(i, 5) = std::sqrt(rgb[0] * rgb[2]);
        } else {
            throw std::invalid_argument("Unsupported number of features");
        }
    }

    // Build target matrix Y (n_samples x 3)
    Eigen::MatrixXf Y(n_samples, 3);
    for (int i = 0; i < n_samples; ++i) {
        const cv::Vec3f& rgb = reference[i];
        Y(i, 0) = rgb[0];
        Y(i, 1) = rgb[1];
        Y(i, 2) = rgb[2];
    }

    // Solve ridge regression: M = (F^T * F + lambda * I)^(-1) * F^T * Y
    Eigen::MatrixXf FtF = F.transpose() * F;
    Eigen::MatrixXf reg = lambda * Eigen::MatrixXf::Identity(n_features, n_features);
    Eigen::MatrixXf FtF_reg = FtF + reg;

    // Check if matrix is invertible
    if (FtF_reg.determinant() == 0.0f) {
        // Add small epsilon to diagonal if singular
        FtF_reg.diagonal().array() += 1e-8f;
    }

    Eigen::MatrixXf M = FtF_reg.ldlt().solve(F.transpose() * Y);

    // Transpose to get 3 x n_features matrix (each row is a color channel)
    return M.transpose().cast<float>();
}

std::tuple<std::string, float, std::string> narrowband_check(
    const std::vector<cv::Vec3f>& observed_mean_linear,
    float warn_threshold,
    float reject_threshold
) {
    if (observed_mean_linear.empty()) {
        return std::make_tuple("ok", 0.0f, "No data");
    }

    // Calculate average of R, G, B across all patches
    float avgR = 0.0f, avgG = 0.0f, avgB = 0.0f;
    for (const auto& rgb : observed_mean_linear) {
        avgR += rgb[0];
        avgG += rgb[1];
        avgB += rgb[2];
    }
    avgR /= observed_mean_linear.size();
    avgG /= observed_mean_linear.size();
    avgB /= observed_mean_linear.size();

    // Find min and max channel
    float minChan = std::min({avgR, avgG, avgB});
    float maxChan = std::max({avgR, avgG, avgB});

    // Avoid division by zero
    if (maxChan < 1e-10f) {
        return std::make_tuple("ok", 0.0f, "All channels near zero");
    }

    float balance = minChan / maxChan;
    std::string level = "ok";
    std::string message;

    if (balance < reject_threshold) {
        level = "reject";
        message = "Severe narrowband light detected - impossible to color correct";
    } else if (balance < warn_threshold) {
        level = "warn";
        message = "Narrowband light detected - consider turning on flashlight";
    } else {
        message = "Light quality OK";
    }

    return std::make_tuple(level, balance, message);
}

cv::Vec3f von_kries_gain(
    const std::vector<cv::Vec3f>& observed,
    const std::vector<cv::Vec3f>& reference
) {
    if (observed.empty() || reference.empty() || observed.size() != reference.size()) {
        return cv::Vec3f(1.0f, 1.0f, 1.0f); // Identity gain
    }

    // Calculate mean of observed and reference
    cv::Vec3f obsMean(0.0f, 0.0f, 0.0f);
    cv::Vec3f refMean(0.0f, 0.0f, 0.0f);

    for (size_t i = 0; i < observed.size(); ++i) {
        obsMean[0] += observed[i][0];
        obsMean[1] += observed[i][1];
        obsMean[2] += observed[i][2];

        refMean[0] += reference[i][0];
        refMean[1] += reference[i][1];
        refMean[2] += reference[i][2];
    }

    obsMean /= static_cast<float>(observed.size());
    refMean /= static_cast<float>(reference.size());

    // Calculate gain: reference / observed
    cv::Vec3f gain;
    gain[0] = (obsMean[0] > 1e-10f) ? refMean[0] / obsMean[0] : 1.0f;
    gain[1] = (obsMean[1] > 1e-10f) ? refMean[1] / obsMean[1] : 1.0f;
    gain[2] = (obsMean[2] > 1e-10f) ? refMean[2] / obsMean[2] : 1.0f;

    return gain;
}

} // namespace color
} // namespace dosimeter