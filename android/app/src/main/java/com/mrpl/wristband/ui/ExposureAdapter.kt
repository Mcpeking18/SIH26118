package com.mrpl.wristband.ui

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.mrpl.wristband.R
import com.mrpl.wristband.data.ScanUiResult

class ExposureAdapter(
    private var records: List<ScanUiResult>
) : RecyclerView.Adapter<ExposureAdapter.ViewHolder>() {

    inner class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        val tvTimestamp: TextView = itemView.findViewById(R.id.tvRecordTimestamp)
        val tvWristbandId: TextView = itemView.findViewById(R.id.tvRecordWristbandId)
        val tvRecordDose: TextView = itemView.findViewById(R.id.tvRecordDose)
        val tvRecordTwa: TextView = itemView.findViewById(R.id.tvRecordTwa)
        val tvRecordOptical: TextView = itemView.findViewById(R.id.tvRecordOptical)
        val tvRecordArea: TextView = itemView.findViewById(R.id.tvRecordArea)
        val tvRecordStatus: TextView = itemView.findViewById(R.id.tvRecordStatus)
        val tvDemoLabel: TextView = itemView.findViewById(R.id.tvDemoLabel)
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_measurement_record, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val record = records[position]

        val dateParts = record.timestamp.split(" - ")
        holder.tvTimestamp.text = if (dateParts.isNotEmpty()) dateParts[0] else record.timestamp
        holder.tvWristbandId.text = record.wristbandId ?: "Unknown"
        holder.tvRecordArea.text = record.zone ?: "Unknown Area"
        
        holder.tvRecordDose.text = if (record.dosePpmHr != null) String.format("%.2f", record.dosePpmHr) else "N/A"
        holder.tvRecordTwa.text = if (record.twaPpm != null) String.format("%.2f", record.twaPpm) else "N/A"
        
        val lStar = if (record.deltaLStar != null) String.format("%.2f", record.deltaLStar) else "--"
        val e00 = if (record.deltaE00 != null) String.format("%.2f", record.deltaE00) else "--"
        holder.tvRecordOptical.text = "Optical response: ΔL* $lStar  |  ΔE00 $e00"
        holder.tvDemoLabel.visibility = if (record.isMock) View.VISIBLE else View.GONE
    }

    override fun getItemCount() = records.size
}
