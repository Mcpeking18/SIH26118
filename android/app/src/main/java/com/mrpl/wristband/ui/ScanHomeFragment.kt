package com.mrpl.wristband.ui

import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.google.android.material.button.MaterialButton
import com.mrpl.wristband.R
import com.mrpl.wristband.data.DosimetryBridge

class ScanHomeFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val root = inflater.inflate(R.layout.fragment_scan_home, container, false)
        val btnScan = root.findViewById<MaterialButton>(R.id.btnInitializeConnection)
        
        // Open ScannerActivity directly - chemical strip placement
        btnScan.setOnClickListener {
            startActivity(Intent(requireContext(), ScannerActivity::class.java))
        }
        
        return root
    }
}