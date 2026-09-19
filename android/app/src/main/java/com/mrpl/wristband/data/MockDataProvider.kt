package com.mrpl.wristband.data

object MockDataProvider {

    val defaultScanResult = ScanUiResult(
        wristbandId = "H2S-G4-9982",
        refinery = "ABC Refinery",
        unit = "Hydrodesulfurization Unit",
        zone = "HDS-04",
        timestamp = "12 NOV 2024 - 14:22:04",
        peakIntensityPpm = 1.42,
        cumulativeConcentrationPpm = 0.34,
        dosePpmHr = 5.8,
        twaPpm = 0.72,
        darkeningPercent = 34.0,
        e0 = 0.91,
        verdict = "WITHIN LIMITS",
        level = "LOW",
        lastCloudSync = "12 NOV 2024 - 14:22:04",
        isMock = true
    )

    val exposureRecords = listOf(
        ExposureRecord(
            recordId = "REC-9021",
            timestamp = "2024-05-22 14:30",
            location = "SULFUR RECOVERY",
            peakLevelPpm = 14.2,
            duration = "12m",
            status = "EVACUATION",
            severity = ExposureSeverity.EVACUATION
        ),
        ExposureRecord(
            recordId = "REC-8944",
            timestamp = "2024-05-22 10:15",
            location = "DISTILLATION UNIT A",
            peakLevelPpm = 4.8,
            duration = "45m",
            status = "PPE REQ",
            severity = ExposureSeverity.PPE_REQ
        ),
        ExposureRecord(
            recordId = "REC-8812",
            timestamp = "2024-05-21 16:20",
            location = "CATALYTIC CRACKER",
            peakLevelPpm = 8.5,
            duration = "08m",
            status = "LIMIT REACHED",
            severity = ExposureSeverity.LIMIT_REACHED
        ),
        ExposureRecord(
            recordId = "REC-8700",
            timestamp = "2024-05-21 08:00",
            location = "STORAGE TANK FARM",
            peakLevelPpm = 1.2,
            duration = "8h 00m",
            status = "NORMAL",
            severity = ExposureSeverity.NORMAL
        )
    )

    val activePersonnelHds04 = listOf(
        WorkerDose("Marcus Chen", "Safety Lead", 0.12),
        WorkerDose("Sarah Jenkins", "Maintenance", 0.45),
        WorkerDose("Robert Miller", "Technician", 0.08)
    )

    val sulfurRecoveryZone = RefineryZone(
        zoneId = "HDS-04",
        unitName = "SULFUR RECOVERY UNIT",
        sector = "REFINERY SECTOR 04",
        status = ZoneStatus.HIGH,
        cumulativePpm = 8.4,
        oneHrPeakPpm = 12.1,
        zoneAveragePpm = 4.2,
        uptimePercent = 99.8,
        activePersonnelCount = 3,
        totalPersonnelCapacity = 12,
        alertMessage = "Elevated H2S concentrations detected at sensor HDS-04-B.",
        warningThreshold = 5.0,
        activePersonnel = activePersonnelHds04
    )

    val refineryZones = listOf(
        sulfurRecoveryZone,
        RefineryZone(
            zoneId = "DIST-01",
            unitName = "DISTILLATION UNIT A",
            sector = "REFINERY SECTOR 01",
            status = ZoneStatus.ELEVATED,
            cumulativePpm = 4.8,
            oneHrPeakPpm = 5.6,
            zoneAveragePpm = 2.1,
            uptimePercent = 99.9,
            activePersonnelCount = 5,
            totalPersonnelCapacity = 15,
            alertMessage = "Monitoring advisory: Moderate vapor activity.",
            warningThreshold = 5.0,
            activePersonnel = listOf(
                WorkerDose("Priya Patel", "Operator", 0.32),
                WorkerDose("Amit Roy", "Field Tech", 0.18)
            )
        ),
        RefineryZone(
            zoneId = "FCCU-03",
            unitName = "CATALYTIC CRACKER",
            sector = "REFINERY SECTOR 03",
            status = ZoneStatus.HIGH,
            cumulativePpm = 8.5,
            oneHrPeakPpm = 9.2,
            zoneAveragePpm = 3.9,
            uptimePercent = 98.4,
            activePersonnelCount = 2,
            totalPersonnelCapacity = 8,
            alertMessage = "PPE Tier-2 enforcement active.",
            warningThreshold = 5.0,
            activePersonnel = listOf(
                WorkerDose("Vikram Rao", "Inspection", 0.65)
            )
        ),
        RefineryZone(
            zoneId = "TANK-08",
            unitName = "STORAGE TANK FARM",
            sector = "REFINERY SECTOR 02",
            status = ZoneStatus.LOW,
            cumulativePpm = 1.2,
            oneHrPeakPpm = 1.5,
            zoneAveragePpm = 0.4,
            uptimePercent = 100.0,
            activePersonnelCount = 4,
            totalPersonnelCapacity = 10,
            alertMessage = "All atmospheric readings within baseline.",
            warningThreshold = 5.0,
            activePersonnel = listOf(
                WorkerDose("Rajesh Kumar", "Security Lead", 0.05)
            )
        ),
        RefineryZone(
            zoneId = "FLARE-02",
            unitName = "ACID GAS FLARE STACK",
            sector = "REFINERY SECTOR 05",
            status = ZoneStatus.CRITICAL,
            cumulativePpm = 14.8,
            oneHrPeakPpm = 18.2,
            zoneAveragePpm = 7.1,
            uptimePercent = 95.2,
            activePersonnelCount = 1,
            totalPersonnelCapacity = 4,
            alertMessage = "CRITICAL: Automated flare purge cycle in progress.",
            warningThreshold = 5.0,
            activePersonnel = listOf(
                WorkerDose("Sunil Nair", "Specialist", 0.88)
            )
        )
    )
}
