package com.mrpl.wristband.ui

import android.graphics.Color
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.mrpl.wristband.R
import com.mrpl.wristband.data.ExposureRecord
import com.mrpl.wristband.data.ExposureSeverity

class ExposureAdapter(
    private var records: List<ExposureRecord>,
    private val onItemClick: (ExposureRecord) -> Unit = {}
) : RecyclerView.Adapter<ExposureAdapter.ViewHolder>() {

    inner class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val stripView: View = itemView.findViewById(R.id.viewSeverityStrip)
        val tvTimestamp: TextView = itemView.findViewById(R.id.tvRecordTimestamp)
        val tvStatus: TextView = itemView.findViewById(R.id.tvRecordStatus)
        val tvLocation: TextView = itemView.findViewById(R.id.tvRecordLocation)
        val tvPeak: TextView = itemView.findViewById(R.id.tvRecordPeak)
        val tvDuration: TextView = itemView.findViewById(R.id.tvRecordDuration)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_exposure_record, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val record = records[position]
        val ctx = holder.itemView.context

        holder.tvTimestamp.text = record.timestamp
        holder.tvLocation.text = record.location
        holder.tvPeak.text = "${record.peakLevelPpm} PPM"
        holder.tvDuration.text = record.duration
        holder.tvStatus.text = record.status

        val (stripColor, peakColor, statusColor, statusBg) = when (record.severity) {
            ExposureSeverity.EVACUATION -> listOf(
                Color.parseColor("#EF4444"),
                Color.parseColor("#EF4444"),
                Color.parseColor("#EF4444"),
                ctx.getDrawable(R.drawable.bg_badge_red)
            )
            ExposureSeverity.LIMIT_REACHED -> listOf(
                Color.parseColor("#F97316"),
                Color.parseColor("#F97316"),
                Color.parseColor("#F97316"),
                ctx.getDrawable(R.drawable.bg_badge_orange)
            )
            ExposureSeverity.PPE_REQ -> listOf(
                Color.parseColor("#F59E0B"),
                Color.parseColor("#F59E0B"),
                Color.parseColor("#F59E0B"),
                ctx.getDrawable(R.drawable.bg_badge_yellow)
            )
            ExposureSeverity.NORMAL -> listOf(
                Color.parseColor("#10B981"),
                Color.parseColor("#10B981"),
                Color.parseColor("#10B981"),
                ctx.getDrawable(R.drawable.bg_badge_green)
            )
        }

        holder.stripView.setBackgroundColor(stripColor as Int)
        holder.tvPeak.setTextColor(peakColor as Int)
        holder.tvStatus.setTextColor(statusColor as Int)
        holder.tvStatus.background = statusBg as android.graphics.drawable.Drawable?

        holder.itemView.setOnClickListener { onItemClick(record) }
    }

    override fun getItemCount() = records.size

    fun updateData(newRecords: List<ExposureRecord>) {
        records = newRecords
        notifyDataSetChanged()
    }
}
