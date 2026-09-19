package com.mrpl.wristband.data

import java.io.Serializable

enum class ExposureSeverity {
    NORMAL,
    PPE_REQ,
    LIMIT_REACHED,
    EVACUATION
}

enum class ZoneStatus {
    LOW,
    ELEVATED,
    HIGH,
    CRITICAL
}

data class ScanUiResult(
    val wristbandId: String = "H2S-G4-9982",
    val refinery: String = "ABC Refinery",
    val unit: String = "Hydrodesulfurization Unit",
    val zone: String = "HDS-04",
    val timestamp: String = "12 NOV 2024 - 14:22:04",
    val peakIntensityPpm: Double = 1.42,
    val cumulativeConcentrationPpm: Double = 0.34,
    val dosePpmHr: Double = 5.8,
    val twaPpm: Double = 0.72,
    val darkeningPercent: Double = 34.0,
    val e0: Double = 0.91,
    val verdict: String = "WITHIN LIMITS",
    val level: String = "LOW",
    val batteryPercent: Int = 88,
    val calibrationDaysLeft: Int = 18,
    val isEncrypted: Boolean = true,
    val lastCloudSync: String = "12 NOV 2024 - 14:22:04",
    val systemProtocol: String = "OSHA-H2S-v4.1.0",
    val firmwareVersion: String = "X-TREAD_2.8.4",
    val isMock: Boolean = true
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
    val status: ZoneStatus,
    val cumulativePpm: Double,
    val oneHrPeakPpm: Double,
    val zoneAveragePpm: Double,
    val uptimePercent: Double,
    val activePersonnelCount: Int,
    val totalPersonnelCapacity: Int,
    val alertMessage: String,
    val warningThreshold: Double = 5.0,
    val activePersonnel: List<WorkerDose> = emptyList()
) : Serializable
