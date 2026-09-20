package com.mrpl.wristband.ui

import android.content.Intent
import android.os.Bundle
import org.opencv.android.OpenCVLoader
import android.util.Log
import android.widget.FrameLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.android.material.button.MaterialButton
import com.mrpl.wristband.R

class MainActivity : AppCompatActivity() {

    private lateinit var bottomNav: BottomNavigationView

    override fun onCreate(savedInstanceState: Bundle?) {
                super.onCreate(savedInstanceState)
        if (!OpenCVLoader.initDebug()) {
            Log.e("OpenCV", "Unable to load OpenCV!")
        } else {
            Log.d("OpenCV", "OpenCV loaded successfully!")
        }
        setContentView(R.layout.activity_main)

        bottomNav = findViewById(R.id.bottomNavigation)

//        val btnScan = findViewById<MaterialButton>(R.id.btnTopBarScan)
        val tvTitle = findViewById<TextView>(R.id.tvCurrentTabTitle)
        val tvSub = findViewById<TextView>(R.id.tvCurrentTabSub)

//        btnScan.setOnClickListener {
//            startActivity(Intent(this, ScannerActivity::class.java))
//        }

        // Handle intent extras (e.g. from ExposureResultActivity)
        val openTab = intent.getStringExtra("OPEN_TAB")

        bottomNav.setOnItemSelectedListener { item ->
            val (fragment, title, sub) = when (item.itemId) {
                R.id.nav_home -> Triple(
                    ScanHomeFragment(),
                    getString(R.string.app_name),
                    "SCAN WRISTBAND"
                )
                R.id.nav_history -> Triple(
                    ExposureHistoryFragment(),
                    getString(R.string.compliance_logs),
                    getString(R.string.exposure_archive)
                )
                R.id.nav_map -> Triple(
                    RefineryMapFragment(),
                    "ABC REFINERY",
                    "SECTOR LIVE MAP"
                )
                R.id.nav_profile -> Triple(
                    ProfileFragment(),
                    "MARCUS VANCE",
                    "EMP-9924-X · NODE TX-04"
                )
                else -> return@setOnItemSelectedListener false
            }

            tvTitle.text = title
            tvSub.text = sub
            loadFragment(fragment)
            true
        }

        // Set default tab
        if (savedInstanceState == null) {
            if (openTab == "HISTORY") {
                bottomNav.selectedItemId = R.id.nav_history
            } else {
                bottomNav.selectedItemId = R.id.nav_home
            }
        }
    }

    private fun loadFragment(fragment: Fragment) {
        supportFragmentManager.beginTransaction()
            .replace(R.id.fragmentContainer, fragment)
            .commitAllowingStateLoss()
    }
}
