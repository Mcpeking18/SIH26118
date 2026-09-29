package com.mrpl.wristband.ui

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.mrpl.wristband.R
import com.mrpl.wristband.data.HistoryManager

class ExposureHistoryFragment : Fragment() {

    private lateinit var adapter: ExposureAdapter


    override fun onResume() {
        super.onResume()
        loadHistory()
    }

    private fun loadHistory() {
        val view = view ?: return
        val rv = view.findViewById<RecyclerView>(R.id.rvExposureHistory)
        val tvCount = view.findViewById<TextView>(R.id.tvRecordCount)
        val layoutEmptyState = view.findViewById<View>(R.id.layoutEmptyState)
        val layoutGraphContainer = view.findViewById<LinearLayout>(R.id.layoutGraphContainer)

        val selectedId = "WB-DEMO-001" // Prototype Dummy ID
        
        val allRecords = HistoryManager.getRecords(requireContext())
        val realRecords = allRecords.filter { it.wristbandId == selectedId }
        
        adapter = ExposureAdapter(realRecords)
        rv.layoutManager = LinearLayoutManager(requireContext())
        rv.adapter = adapter
        tvCount.text = "${realRecords.size} records"

        if (realRecords.isEmpty()) {
            layoutEmptyState.visibility = View.VISIBLE
            rv.visibility = View.GONE
            layoutGraphContainer.visibility = View.GONE
        } else {
            layoutEmptyState.visibility = View.GONE
            rv.visibility = View.VISIBLE
            layoutGraphContainer.visibility = View.VISIBLE
            
            layoutGraphContainer.removeAllViews()
            
            // Draw simple bars for ppm hr dose
            val maxDose = realRecords.maxOfOrNull { it.dosePpmHr ?: 0.0 } ?: 0.0
            val scaleMax = if (maxDose > 5.0) maxDose * 1.2 else 5.0
            
            // Plot oldest to newest
            for (record in realRecords.reversed()) {
                val dose = record.dosePpmHr ?: 0.0
                val heightPercent = (dose / scaleMax).toFloat().coerceIn(0.02f, 1.0f)
                
                val barContainer = LinearLayout(requireContext()).apply {
                    orientation = LinearLayout.VERTICAL
                    gravity = android.view.Gravity.BOTTOM or android.view.Gravity.CENTER_HORIZONTAL
                    layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
                }
                
                val dummyTop = View(requireContext()).apply {
                    layoutParams = LinearLayout.LayoutParams(40, 0, 1f - heightPercent)
                }
                
                val bar = View(requireContext()).apply {
                    setBackgroundColor(requireContext().getColor(if (record.isMock) R.color.h2s_divider else R.color.h2s_blue_light))
                    layoutParams = LinearLayout.LayoutParams(24, 0, heightPercent).apply {
                        bottomMargin = 8
                    }
                }
                
                val dateLabel = TextView(requireContext()).apply {
                    val dateParts = record.timestamp.split(" ")
                    text = if (dateParts.size > 1) dateParts[0] else ""
                    textSize = 10f
                    setTextColor(requireContext().getColor(R.color.h2s_text_muted))
                }
                
                barContainer.addView(dummyTop)
                barContainer.addView(bar)
                barContainer.addView(dateLabel)
                
                layoutGraphContainer.addView(barContainer)
            }
        }
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val root = inflater.inflate(R.layout.fragment_exposure_history, container, false)

        val rv = root.findViewById<RecyclerView>(R.id.rvExposureHistory)
        val tvCount = root.findViewById<TextView>(R.id.tvRecordCount)
        val layoutEmptyState = root.findViewById<View>(R.id.layoutEmptyState)
        val layoutGraphContainer = root.findViewById<LinearLayout>(R.id.layoutGraphContainer)

        val selectedId = "WB-DEMO-001" // Prototype Dummy ID
        
        val allRecords = HistoryManager.getRecords(requireContext())
        val realRecords = allRecords.filter { it.wristbandId == selectedId }
        
        adapter = ExposureAdapter(realRecords)
        rv.layoutManager = LinearLayoutManager(requireContext())
        rv.adapter = adapter
        tvCount.text = "${realRecords.size} records"

        if (realRecords.isEmpty()) {
            layoutEmptyState.visibility = View.VISIBLE
            rv.visibility = View.GONE
            layoutGraphContainer.visibility = View.GONE
        } else {
            layoutEmptyState.visibility = View.GONE
            rv.visibility = View.VISIBLE
            layoutGraphContainer.visibility = View.VISIBLE
            
            layoutGraphContainer.removeAllViews()
            
            // Draw simple bars for ppm hr dose
            val maxDose = realRecords.maxOfOrNull { it.dosePpmHr ?: 0.0 } ?: 0.0
            val scaleMax = if (maxDose > 5.0) maxDose * 1.2 else 5.0
            
            // Plot oldest to newest
            for (record in realRecords.reversed()) {
                val dose = record.dosePpmHr ?: 0.0
                val heightPercent = (dose / scaleMax).toFloat().coerceIn(0.02f, 1.0f)
                
                val barContainer = LinearLayout(requireContext()).apply {
                    orientation = LinearLayout.VERTICAL
                    gravity = android.view.Gravity.BOTTOM or android.view.Gravity.CENTER_HORIZONTAL
                    layoutParams = LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.MATCH_PARENT, 1f)
                }
                
                val dummyTop = View(requireContext()).apply {
                    layoutParams = LinearLayout.LayoutParams(40, 0, 1f - heightPercent)
                }
                
                val bar = View(requireContext()).apply {
                    setBackgroundColor(requireContext().getColor(R.color.h2s_blue_light))
                    layoutParams = LinearLayout.LayoutParams(24, 0, heightPercent).apply {
                        bottomMargin = 8
                    }
                }
                
                val dateLabel = TextView(requireContext()).apply {
                    val dateParts = record.timestamp.split(" ")
                    text = if (dateParts.size > 1) dateParts[0] else ""
                    textSize = 10f
                    setTextColor(requireContext().getColor(R.color.h2s_text_muted))
                }
                
                barContainer.addView(dummyTop)
                barContainer.addView(bar)
                barContainer.addView(dateLabel)
                
                layoutGraphContainer.addView(barContainer)
            }
        }
        return root
    }
}
