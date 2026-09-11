package com.mrpl.wristband.dosimetry

enum class Verdict {
    SAFE,
    WARNING,
    CRITICAL,
    SATURATED,
    SUSPECT,
    INVALID
}

data class ExposureLimits(
    val twaPpm: Double = 1.0,
    val stelPpm: Double = 5.0,
    val nioshCeilingPpm: Double = 10.0,
    val oshaCeilingPpm: Double = 20.0,
    val doseCriticalPpmHr: Double = 20.0,
    val twaCriticalMultiple: Double = 5.0,
    val source: String = "ACGIH TLV 2023 / NIOSH REL / OSHA 29 CFR 1910.1000 Table Z-2"
)

val ACGIH_OSHA_NIOSH = ExposureLimits()
