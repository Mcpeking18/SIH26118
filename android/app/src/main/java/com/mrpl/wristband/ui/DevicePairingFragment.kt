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

class DevicePairingFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val root = inflater.inflate(R.layout.fragment_device_pairing, container, false)

        val btnInitialize = root.findViewById<MaterialButton>(R.id.btnInitializeConnection)
        val tvManualEntry = root.findViewById<TextView>(R.id.tvManualEntry)
        val tvProgress = root.findViewById<TextView>(R.id.tvPipelineProgress)

        val tvOp = root.findViewById<TextView>(R.id.tvStepOperatorVal)
        val tvRef = root.findViewById<TextView>(R.id.tvStepRefineryVal)
        val tvUnit = root.findViewById<TextView>(R.id.tvStepUnitVal)
        val tvZone = root.findViewById<TextView>(R.id.tvStepZoneVal)
        val tvWrist = root.findViewById<TextView>(R.id.tvStepWristbandVal)

        btnInitialize.setOnClickListener {
            btnInitialize.isEnabled = false
            btnInitialize.text = "SYNCHRONIZING..."

            val handler = Handler(Looper.getMainLooper())
            handler.postDelayed({
                tvOp.text = "MARCUS VANCE (EMP-9924-X)"
                tvOp.setTextColor(requireContext().getColor(R.color.h2s_green))
                tvProgress.text = "20%"
            }, 300)

            handler.postDelayed({
                tvRef.text = "ABC REFINERY - SECTOR 04"
                tvRef.setTextColor(requireContext().getColor(R.color.h2s_green))
                tvProgress.text = "40%"
            }, 600)

            handler.postDelayed({
                tvUnit.text = "HYDRODESULFURIZATION UNIT"
                tvUnit.setTextColor(requireContext().getColor(R.color.h2s_green))
                tvProgress.text = "60%"
            }, 900)

            handler.postDelayed({
                tvZone.text = "HDS-04 (ACTIVE MONITORED)"
                tvZone.setTextColor(requireContext().getColor(R.color.h2s_green))
                tvProgress.text = "80%"
            }, 1200)

            handler.postDelayed({
                tvWrist.text = "H2S-G4-9982 (PAIRED)"
                tvWrist.setTextColor(requireContext().getColor(R.color.h2s_green))
                tvProgress.text = "100%"
                btnInitialize.isEnabled = true
                btnInitialize.text = "OPEN WRISTBAND SCANNER  ➔"
                btnInitialize.setOnClickListener {
                    startActivity(Intent(requireContext(), ScannerActivity::class.java))
                }
                Toast.makeText(requireContext(), "Telemetry Synchronized. Device Ready for Scan.", Toast.LENGTH_SHORT).show()
            }, 1500)
        }

        tvManualEntry.setOnClickListener {
            Toast.makeText(requireContext(), "Manual Hardware Entry: Sensor ID prompt", Toast.LENGTH_SHORT).show()
            startActivity(Intent(requireContext(), ScannerActivity::class.java))
        }

        return root
    }
}
