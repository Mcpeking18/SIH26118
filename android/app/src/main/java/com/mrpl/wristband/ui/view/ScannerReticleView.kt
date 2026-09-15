package com.mrpl.wristband.ui.view

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/**
 * Custom Viewfinder Reticle View matching Page 3 of the Visily design:
 * Highlighting blue corner brackets, target guide, and "ALIGN TAG HERE" cue.
 */
class ScannerReticleView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private val scrimPaint = Paint().apply {
        color = Color.parseColor("#9905080E")
        style = Paint.Style.FILL
    }

    private val cornerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#3B82F6")
        strokeWidth = 6f
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
    }

    private val boxBorderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#263B82F6")
        strokeWidth = 2f
        style = Paint.Style.STROKE
    }

    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#94A3B8")
        textSize = 28f
        textAlign = Paint.Align.CENTER
        isFakeBoldText = true
        letterSpacing = 0.15f
    }

    private val centerLaserPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#33EF4444")
        strokeWidth = 2f
        style = Paint.Style.STROKE
    }

    private val targetRect = RectF()

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val w = width.toFloat()
        val h = height.toFloat()

        val boxWidth = w * 0.78f
        val boxHeight = boxWidth * 1.15f

        val left = (w - boxWidth) / 2f
        val top = (h - boxHeight) / 2.2f
        val right = left + boxWidth
        val bottom = top + boxHeight
        targetRect.set(left, top, right, bottom)

        // Draw outer scrim (4 rectangles around target)
        canvas.drawRect(0f, 0f, w, top, scrimPaint)
        canvas.drawRect(0f, bottom, w, h, scrimPaint)
        canvas.drawRect(0f, top, left, bottom, scrimPaint)
        canvas.drawRect(right, top, w, bottom, scrimPaint)

        // Draw boundary box
        canvas.drawRect(targetRect, boxBorderPaint)

        // Draw corner brackets (length ~ 40dp)
        val cornerLen = 50f
        // Top-Left
        canvas.drawLine(left, top, left + cornerLen, top, cornerPaint)
        canvas.drawLine(left, top, left, top + cornerLen, cornerPaint)
        // Top-Right
        canvas.drawLine(right, top, right - cornerLen, top, cornerPaint)
        canvas.drawLine(right, top, right, top + cornerLen, cornerPaint)
        // Bottom-Left
        canvas.drawLine(left, bottom, left + cornerLen, bottom, cornerPaint)
        canvas.drawLine(left, bottom, left, bottom - cornerLen, cornerPaint)
        // Bottom-Right
        canvas.drawLine(right, bottom, right - cornerLen, bottom, cornerPaint)
        canvas.drawLine(right, bottom, right, bottom - cornerLen, cornerPaint)

        // Draw horizontal center guide line
        val centerY = (top + bottom) / 2f
        canvas.drawLine(left + 20f, centerY, right - 20f, centerY, centerLaserPaint)

        // Draw text "ALIGN TAG HERE" inside bottom of target box
        canvas.drawText("ALIGN TAG HERE", w / 2f, bottom - 24f, textPaint)
    }
}
