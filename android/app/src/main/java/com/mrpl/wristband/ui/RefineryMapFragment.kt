package com.mrpl.wristband.ui

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import com.mrpl.wristband.R
import com.mrpl.wristband.data.RefineryZone
import com.mrpl.wristband.ui.view.RefineryMapView

class RefineryMapFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val root = inflater.inflate(R.layout.fragment_refinery_map, container, false)

        val mapView = root.findViewById<RefineryMapView>(R.id.refineryMapView)
        mapView.onZoneClickListener = { zone: RefineryZone ->
            val intent = Intent(requireContext(), ZoneDetailsActivity::class.java)
            intent.putExtra("ZONE_DATA", zone)
            startActivity(intent)
        }

        return root
    }
}
