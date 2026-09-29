package com.mrpl.wristband.ui.view

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.Shader
import android.util.AttributeSet
import android.view.View

/**
 * Custom Canvas Chart View to match Visily's 7-Day & 24-Hour exposure trend curves
 * with smooth bezier paths, subtle background grid, and threshold lines.
 */
class TrendLineChartView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var dataPoints: FloatArray = floatArrayOf(2f, 4f, 1f, 8f, 14.2f, 3f, 5f, 2f)
    private var lineStrokeColor: Int = Color.parseColor("#3B82F6")
    private var fillGradientStartColor: Int = Color.parseColor("#4D2563EB")
    private var fillGradientEndColor: Int = Color.parseColor("#050A10")
    private var thresholdValue: Float? = null
    private var thresholdColor: Int = Color.parseColor("#F97316")

    private val gridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#1B2538")
        strokeWidth = 1.5f
        style = Paint.Style.STROKE
    }

    private val linePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 4.5f
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
    }

    private val thresholdPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 2.5f
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(10f, 10f), 0f)
    }

    private val linePath = Path()
    private val fillPath = Path()

    fun setData(
        points: FloatArray,
        lineColor: Int = Color.parseColor("#3B82F6"),
        threshold: Float? = null,
        thresholdLineColor: Int = Color.parseColor("#F97316")
    ) {
        this.dataPoints = points
        this.lineStrokeColor = lineColor
        this.thresholdValue = threshold
        this.thresholdColor = thresholdLineColor

        if (lineColor == Color.parseColor("#F97316")) {
            fillGradientStartColor = Color.parseColor("#4DF97316")
        } else {
            fillGradientStartColor = Color.parseColor("#4D2563EB")
        }

        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (dataPoints.isEmpty()) return

        val w = width.toFloat()
        val h = height.toFloat()
        val padding = 24f

        val chartWidth = w - padding * 2
        val chartHeight = h - padding * 2

        // Draw horizontal grid lines
        val gridLines = 4
        for (i in 0..gridLines) {
            val y = padding + (chartHeight / gridLines) * i
            canvas.drawLine(padding, y, w - padding, y, gridPaint)
        }

        // Draw vertical grid lines
        val vertLines = 6
        for (i in 0..vertLines) {
            val x = padding + (chartWidth / vertLines) * i
            canvas.drawLine(x, padding, x, h - padding, gridPaint)
        }

        var maxVal = dataPoints.maxOrNull() ?: 1f
        if (thresholdValue != null && thresholdValue!! > maxVal) {
            maxVal = thresholdValue!!
        }
        maxVal *= 1.2f // margin at top
        val minVal = 0f

        val stepX = chartWidth / (dataPoints.size - 1).coerceAtLeast(1)

        linePath.reset()
        fillPath.reset()

        val points = mutableListOf<Pair<Float, Float>>()
        for (i in dataPoints.indices) {
            val x = padding + i * stepX
            val ratio = (dataPoints[i] - minVal) / (maxVal - minVal).coerceAtLeast(1f)
            val y = (h - padding) - ratio * chartHeight
            points.add(Pair(x, y))
        }

        if (points.isNotEmpty()) {
            linePath.moveTo(points[0].first, points[0].second)
            fillPath.moveTo(points[0].first, h - padding)
            fillPath.lineTo(points[0].first, points[0].second)

            for (i in 1 until points.size) {
                val prev = points[i - 1]
                val curr = points[i]
                val midX = (prev.first + curr.first) / 2
                linePath.cubicTo(midX, prev.second, midX, curr.second, curr.first, curr.second)
                fillPath.cubicTo(midX, prev.second, midX, curr.second, curr.first, curr.second)
            }

            fillPath.lineTo(points.last().first, h - padding)
            fillPath.close()

            // Draw gradient fill
            fillPaint.shader = LinearGradient(
                0f, padding, 0f, h - padding,
                fillGradientStartColor, fillGradientEndColor,
                Shader.TileMode.CLAMP
            )
            canvas.drawPath(fillPath, fillPaint)

            // Draw line
            linePaint.color = lineStrokeColor
            canvas.drawPath(linePath, linePaint)
        }

        // Draw dashed threshold line if present
        thresholdValue?.let { thresh ->
            val ratio = (thresh - minVal) / (maxVal - minVal).coerceAtLeast(1f)
            val threshY = (h - padding) - ratio * chartHeight
            thresholdPaint.color = thresholdColor
            canvas.drawLine(padding, threshY, w - padding, threshY, thresholdPaint)
        }
    }
}
