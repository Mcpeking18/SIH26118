package com.mrpl.wristband.ui

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.LinearLayout
import android.widget.Toast
import androidx.fragment.app.Fragment
import com.google.android.material.button.MaterialButton
import com.mrpl.wristband.R

class ProfileFragment : Fragment() {

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View? {
        val root = inflater.inflate(R.layout.fragment_profile, container, false)

        val btnSignOut = root.findViewById<MaterialButton>(R.id.btnSignOut)
        val rowDeviceSettings = root.findViewById<LinearLayout>(R.id.rowDeviceSettings)
        val rowAlertThresholds = root.findViewById<LinearLayout>(R.id.rowAlertThresholds)
        val rowCalibration = root.findViewById<LinearLayout>(R.id.rowCalibration)

        rowDeviceSettings.setOnClickListener {
            Toast.makeText(requireContext(), "Device Settings (Coming in Phase 3)", Toast.LENGTH_SHORT).show()
        }

        rowAlertThresholds.setOnClickListener {
            Toast.makeText(requireContext(), "Alert Thresholds: OSHA TWA 1ppm / Ceiling 20ppm / STEL 5ppm", Toast.LENGTH_SHORT).show()
        }

        rowCalibration.setOnClickListener {
            Toast.makeText(requireContext(), "Next Calibration: Oct 24, 2024 – Spectrophotometric Chamber Required", Toast.LENGTH_SHORT).show()
        }

        btnSignOut.setOnClickListener {
            android.app.AlertDialog.Builder(requireContext())
                .setTitle("Sign Out")
                .setMessage("Are you sure you want to sign out of the H2S Guard System?")
                .setPositiveButton("SIGN OUT") { _, _ ->
                    val intent = Intent(requireContext(), SignInActivity::class.java)
                    intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                    startActivity(intent)
                }
                .setNegativeButton("CANCEL", null)
                .show()
        }

        return root
    }
}
