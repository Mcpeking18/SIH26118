package com.mrpl.wristband.ui

import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.mrpl.wristband.R

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val btnScan = findViewById<MaterialButton>(R.id.btnScan)
        val btnHistory = findViewById<MaterialButton>(R.id.btnHistory)

        btnScan.setOnClickListener {
            Toast.makeText(this, "Scan Wristband clicked", Toast.LENGTH_SHORT).show()
        }

        btnHistory.setOnClickListener {
            Toast.makeText(this, "View History clicked", Toast.LENGTH_SHORT).show()
        }
    }
}
