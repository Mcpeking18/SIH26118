package com.mrpl.wristband.ui

import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.CheckBox
import android.widget.EditText
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.android.material.button.MaterialButton
import com.mrpl.wristband.R

class SignInActivity : AppCompatActivity() {

    private var isPasswordVisible = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_sign_in)

        val etEmpId = findViewById<EditText>(R.id.etEmpId)
        val etPin = findViewById<EditText>(R.id.etPin)
        val ivTogglePassword = findViewById<ImageView>(R.id.ivTogglePassword)
        val cbAcknowledge = findViewById<CheckBox>(R.id.cbAcknowledge)
        val btnSignIn = findViewById<MaterialButton>(R.id.btnSignIn)
        val tvResetPin = findViewById<TextView>(R.id.tvResetPin)
        val layoutTrainingHub = findViewById<LinearLayout>(R.id.layoutTrainingHub)

        ivTogglePassword.setOnClickListener {
            isPasswordVisible = !isPasswordVisible
            if (isPasswordVisible) {
                etPin.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD
                ivTogglePassword.setColorFilter(getColor(R.color.h2s_blue_light))
            } else {
                etPin.inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                ivTogglePassword.setColorFilter(getColor(R.color.h2s_text_muted))
            }
            etPin.setSelection(etPin.text.length)
        }

        tvResetPin.setOnClickListener {
            Toast.makeText(this, "Security PIN reset requested through supervisor node.", Toast.LENGTH_SHORT).show()
        }

        layoutTrainingHub.setOnClickListener {
            Toast.makeText(this, "Accessing Refinery Safety & Sensor Training Module...", Toast.LENGTH_SHORT).show()
        }

        btnSignIn.setOnClickListener {
            if (!cbAcknowledge.isChecked) {
                Toast.makeText(this, "Please acknowledge refinery safety protocols to proceed.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            val empId = etEmpId.text.toString().trim()
            if (empId.isEmpty()) {
                Toast.makeText(this, "Please enter Employee ID", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            // Launch Main Dashboard
            val intent = Intent(this, MainActivity::class.java)
            intent.putExtra("EMP_ID", empId)
            startActivity(intent)
            finish()
        }
    }
}
