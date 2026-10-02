package com.mrpl.wristband.data

import java.io.Serializable

enum class ExposureSeverity {
    NORMAL,
    PPE_REQ,
    LIMIT_REACHED,
    EVACUATION
}

enum class DemoExposureStatus(val label: String, val colorHex: String) {
    NORMAL("Normal", "#10B981"),
    ATTENTION("Attention", "#F59E0B"),
    REVIEW("Review", "#F97316"),
    EXPERIMENTAL_HIGH("Experimental High", "#EA580C"),
    EXPERIMENTAL_EXTREME("Experimental Extreme", "#EF4444");

    companion object {
        fun fromDose(dose: Double?): DemoExposureStatus {
            if (dose == null) return NORMAL
            return when {
                dose < 8.0 -> NORMAL
                dose < 16.0 -> ATTENTION
                dose < 32.0 -> REVIEW
                dose < 50.0 -> EXPERIMENTAL_HIGH
                else -> EXPERIMENTAL_EXTREME
            }
        }
    }
}

object DemoAreas {
    val AREAS = listOf("Plant Area A", "Unit 1", "Storage Area", "Process Area", "Workshop")
}

enum class ScanState {
    SUCCESS,
    BADGE_NOT_DETECTED,
    POOR_IMAGE_QUALITY,
    INVALID_GEOMETRY,
    PROCESSING_ERROR,
    CALIBRATION_UNAVAILABLE
}

data class ScanUiResult(
    val wristbandId: String = "H2S-G4-9982",
    val refinery: String? = null,
    val unit: String? = null,
    val zone: String? = null,
    val timestamp: String = "",
    val peakIntensityPpm: Double? = null,
    val cumulativeConcentrationPpm: Double? = null,
    val dosePpmHr: Double? = null,
    val twaPpm: Double? = null,
    val deltaLStar: Double? = null,
    val deltaE00: Double? = null,
    val verdict: String? = null,
    val level: String? = null,
    val lastCloudSync: String? = null,
    val isMock: Boolean = true,
    val scanState: ScanState = ScanState.SUCCESS,
    val errorMessage: String? = null,
    val debugInfo: String? = null
) : Serializable

data class ExposureRecord(
    val recordId: String,
    val timestamp: String,
    val location: String,
    val peakLevelPpm: Double,
    val duration: String,
    val status: String,
    val severity: ExposureSeverity
) : Serializable

data class WorkerDose(
    val name: String,
    val role: String,
    val dosePpmHr: Double,
    val avatarRes: Int? = null
) : Serializable

data class RefineryZone(
    val zoneId: String,
    val unitName: String,
    val sector: String,
    val status: DemoExposureStatus,
    val cumulativeDosePpmHr: Double,
    val oneHrPeakPpm: Double,
    val zoneAveragePpm: Double,
    val uptimePercent: Double,
    val activePersonnelCount: Int,
    val totalPersonnelCapacity: Int,
    val alertMessage: String,
    val warningThreshold: Double = 5.0,
    val activePersonnel: List<WorkerDose> = emptyList()
) : Serializable
