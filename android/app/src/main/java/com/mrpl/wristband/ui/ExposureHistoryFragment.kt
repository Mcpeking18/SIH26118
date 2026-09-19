package com.mrpl.wristband.ui

import android.graphics.Color
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.mrpl.wristband.R
import com.mrpl.wristband.data.MockDataProvider
import com.mrpl.wristband.ui.view.TrendLineChartView

class ExposureHistoryFragment : Fragment() {

    private lateinit var adapter: ExposureAdapter

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val root = inflater.inflate(R.layout.fragment_exposure_history, container, false)

        val rv = root.findViewById<RecyclerView>(R.id.rvExposureHistory)
        val chart = root.findViewById<TrendLineChartView>(R.id.chartHistoryTrend)
        val tvCount = root.findViewById<TextView>(R.id.tvRecordCount)
        val btnExport = root.findViewById<ImageView>(R.id.btnExportHistory)

        // Seed 7-day trend: Mon=0.5, Tue=1.2, Wed=0.8, Thu=4.8, Fri=14.2, Sat=2.1, Sun=0.9
        chart.setData(
            floatArrayOf(0.5f, 1.2f, 0.8f, 4.8f, 14.2f, 2.1f, 0.9f),
            Color.parseColor("#3B82F6"),
            5.0f,
            Color.parseColor("#F97316")
        )

        val allRecords = MockDataProvider.exposureRecords
        adapter = ExposureAdapter(allRecords) { record ->
            Toast.makeText(requireContext(), "${record.location}: ${record.peakLevelPpm} PPM - ${record.status}", Toast.LENGTH_SHORT).show()
        }
        rv.layoutManager = LinearLayoutManager(requireContext())
        rv.adapter = adapter
        tvCount.text = "${allRecords.size} records"

        // Filter chip logic
        val filterAll = root.findViewById<TextView>(R.id.filterAll)
        val filterSafe = root.findViewById<TextView>(R.id.filterSafe)
        val filterAlert = root.findViewById<TextView>(R.id.filterAlert)
        val filterCrit = root.findViewById<TextView>(R.id.filterCrit)

        filterAll.setOnClickListener {
            adapter.updateData(allRecords)
            tvCount.text = "${allRecords.size} records"
        }

        filterSafe.setOnClickListener {
            val filtered = allRecords.filter { it.status == "NORMAL" }
            adapter.updateData(filtered)
            tvCount.text = "${filtered.size} records"
        }

        filterAlert.setOnClickListener {
            val filtered = allRecords.filter { it.status == "PPE REQ" || it.status == "LIMIT REACHED" }
            adapter.updateData(filtered)
            tvCount.text = "${filtered.size} records"
        }

        filterCrit.setOnClickListener {
            val filtered = allRecords.filter { it.status == "EVACUATION" }
            adapter.updateData(filtered)
            tvCount.text = "${filtered.size} records"
        }

        btnExport.setOnClickListener {
            Toast.makeText(requireContext(), "Exporting compliance log as PDF/CSV...", Toast.LENGTH_SHORT).show()
        }

        return root
    }
}
