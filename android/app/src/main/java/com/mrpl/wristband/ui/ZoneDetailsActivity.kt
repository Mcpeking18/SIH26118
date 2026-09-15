package com.mrpl.wristband.ui

import android.graphics.Color
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.mrpl.wristband.R
import com.mrpl.wristband.data.RefineryZone
import com.mrpl.wristband.data.ZoneStatus
import com.mrpl.wristband.ui.view.TrendLineChartView

class ZoneDetailsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_zone_details)

        @Suppress("DEPRECATION")
        val zone = intent.getSerializableExtra("ZONE_DATA") as? RefineryZone
            ?: return

        val statusColor = when (zone.status) {
            ZoneStatus.LOW -> Color.parseColor("#10B981")
            ZoneStatus.ELEVATED -> Color.parseColor("#F59E0B")
            ZoneStatus.HIGH -> Color.parseColor("#F97316")
            ZoneStatus.CRITICAL -> Color.parseColor("#EF4444")
        }

        // Back
        findViewById<ImageView>(R.id.btnZoneBack).setOnClickListener { finish() }

        // Hero banner
        findViewById<TextView>(R.id.tvZoneSectorHeader).text = zone.sector
        findViewById<TextView>(R.id.tvZoneUnitName).text = zone.unitName

        val tvZoneId = findViewById<TextView>(R.id.tvZoneId)
        tvZoneId.text = zone.zoneId
        tvZoneId.setTextColor(statusColor)

        val tvPersonnel = findViewById<TextView>(R.id.tvZonePersonnel)
        tvPersonnel.text = "${zone.activePersonnelCount}/${zone.totalPersonnelCapacity} PERSONNEL ACTIVE"

        // Alert banner
        val tvAlertDesc = findViewById<TextView>(R.id.tvAlertDesc)
        tvAlertDesc.text = zone.alertMessage

        // Metric tiles
        val tvCumulative = findViewById<TextView>(R.id.tvZoneCumulative)
        tvCumulative.text = "${zone.cumulativePpm} PPM"
        tvCumulative.setTextColor(statusColor)

        val tvPeak = findViewById<TextView>(R.id.tvZonePeak1Hr)
        tvPeak.text = "${zone.oneHrPeakPpm} PPM"
        tvPeak.setTextColor(statusColor)

        val tvAverage = findViewById<TextView>(R.id.tvZoneAverage)
        tvAverage.text = "${zone.zoneAveragePpm} PPM"
        tvAverage.setTextColor(statusColor)

        val tvUptime = findViewById<TextView>(R.id.tvZoneUptime)
        tvUptime.text = "${zone.uptimePercent}%"

        // 24-hour trend chart
        val chart = findViewById<TrendLineChartView>(R.id.chartZoneTrend)
        chart.setData(
            floatArrayOf(1.2f, 2.1f, 3.4f, 6.8f, 8.4f, 12.1f, 9.0f, 6.5f),
            statusColor,
            zone.warningThreshold.toFloat(),
            Color.parseColor("#F59E0B")
        )

        // Personnel list
        val personnelLayout = findViewById<LinearLayout>(R.id.layoutPersonnelList)
        personnelLayout.removeAllViews()
        zone.activePersonnel.forEach { worker ->
            val itemView = LayoutInflater.from(this)
                .inflate(R.layout.item_exposure_record, personnelLayout, false)

            // Re-use item layout for personnel: timestamp = role, location = name, peak = dose
            itemView.findViewById<TextView>(R.id.tvRecordTimestamp).text = worker.role
            itemView.findViewById<TextView>(R.id.tvRecordLocation).text = worker.name
            itemView.findViewById<TextView>(R.id.tvRecordPeak).text = String.format("%.2f PPM·hr", worker.dosePpmHr)
            itemView.findViewById<TextView>(R.id.tvRecordDuration).text = ""
            val status = itemView.findViewById<TextView>(R.id.tvRecordStatus)
            status.text = "ACTIVE"
            status.setTextColor(getColor(R.color.h2s_green))
            status.background = getDrawable(R.drawable.bg_badge_green)
            itemView.findViewById<View>(R.id.viewSeverityStrip).setBackgroundColor(statusColor)

            personnelLayout.addView(itemView)
        }

        if (zone.activePersonnel.isEmpty()) {
            val tv = TextView(this)
            tv.text = "No active personnel in this zone"
            tv.setTextColor(Color.parseColor("#64748B"))
            tv.textSize = 12f
            personnelLayout.addView(tv)
        }
    }
}
