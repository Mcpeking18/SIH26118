package com.mrpl.wristband.ui.view

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.DashPathEffect
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import com.mrpl.wristband.data.MockDataProvider
import com.mrpl.wristband.data.RefineryZone
import com.mrpl.wristband.data.ZoneStatus

/**
 * Interactive Schematic Refinery Map View.
 * Displays refinery plant units with pipelines, live status colors, and tap triggers.
 */
class RefineryMapView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    var onZoneClickListener: ((RefineryZone) -> Unit)? = null

    private val zones = MockDataProvider.refineryZones
    private val zoneRects = mutableListOf<Pair<RectF, RefineryZone>>()

    private val bgGridPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#151D2A")
        strokeWidth = 1f
    }

    private val pipePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#2563EB")
        strokeWidth = 4f
        style = Paint.Style.STROKE
        pathEffect = DashPathEffect(floatArrayOf(12f, 8f), 0f)
    }

    private val cardBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#121927")
        style = Paint.Style.FILL
    }

    private val cardStrokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        strokeWidth = 2.5f
        style = Paint.Style.STROKE
    }

    private val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 30f
        isFakeBoldText = true
    }

    private val idPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#94A3B8")
        textSize = 22f
    }

    private val ppmPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 28f
        isFakeBoldText = true
    }

    private val badgePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        textSize = 20f
        isFakeBoldText = true
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val w = width.toFloat()
        val h = height.toFloat()
        if (w == 0f || h == 0f) return

        // Draw schematic grid
        val step = 60f
        var x = 0f
        while (x < w) {
            canvas.drawLine(x, 0f, x, h, bgGridPaint)
            x += step
        }
        var y = 0f
        while (y < h) {
            canvas.drawLine(0f, y, w, y, bgGridPaint)
            y += step
        }

        // Draw pipeline network connecting units
        val p1 = Pair(w * 0.5f, h * 0.16f)
        val p2 = Pair(w * 0.28f, h * 0.42f)
        val p3 = Pair(w * 0.72f, h * 0.42f)
        val p4 = Pair(w * 0.32f, h * 0.76f)
        val p5 = Pair(w * 0.72f, h * 0.76f)

        canvas.drawLine(p1.first, p1.second, p2.first, p2.second, pipePaint)
        canvas.drawLine(p1.first, p1.second, p3.first, p3.second, pipePaint)
        canvas.drawLine(p2.first, p2.second, p4.first, p4.second, pipePaint)
        canvas.drawLine(p3.first, p3.second, p5.first, p5.second, pipePaint)
        canvas.drawLine(p4.first, p4.second, p5.first, p5.second, pipePaint)

        zoneRects.clear()

        // Draw Zone Cards at schematic positions
        val positions = listOf(
            RectF(w * 0.15f, h * 0.08f, w * 0.85f, h * 0.23f), // HDS-04 Sulfur Recovery
            RectF(w * 0.05f, h * 0.33f, w * 0.48f, h * 0.51f), // DIST-01
            RectF(w * 0.52f, h * 0.33f, w * 0.95f, h * 0.51f), // FCCU-03
            RectF(w * 0.05f, h * 0.67f, w * 0.48f, h * 0.85f), // TANK-08
            RectF(w * 0.52f, h * 0.67f, w * 0.95f, h * 0.85f)  // FLARE-02
        )

        for (i in zones.indices) {
            if (i >= positions.size) break
            val zone = zones[i]
            val rect = positions[i]
            zoneRects.add(Pair(rect, zone))

            val statusColor = when (zone.status) {
                ZoneStatus.LOW -> Color.parseColor("#10B981")
                ZoneStatus.ELEVATED -> Color.parseColor("#F59E0B")
                ZoneStatus.HIGH -> Color.parseColor("#F97316")
                ZoneStatus.CRITICAL -> Color.parseColor("#EF4444")
            }

            // Card background
            canvas.drawRoundRect(rect, 16f, 16f, cardBgPaint)

            // Card border colored by status
            cardStrokePaint.color = statusColor
            canvas.drawRoundRect(rect, 16f, 16f, cardStrokePaint)

            // Zone ID tag
            idPaint.color = Color.parseColor("#94A3B8")
            canvas.drawText("ZONE: ${zone.zoneId}", rect.left + 20f, rect.top + 34f, idPaint)

            // Zone Name
            val displayName = if (rect.width() > w * 0.6f) zone.unitName else {
                if (zone.unitName.length > 14) zone.unitName.take(14) + "…" else zone.unitName
            }
            canvas.drawText(displayName, rect.left + 20f, rect.top + 70f, titlePaint)

            // Live PPM readout
            ppmPaint.color = statusColor
            canvas.drawText("${zone.cumulativePpm} PPM", rect.left + 20f, rect.bottom - 22f, ppmPaint)

            // Status label on right
            badgePaint.color = statusColor
            val statusLabel = when (zone.status) {
                ZoneStatus.LOW -> "LOW"
                ZoneStatus.ELEVATED -> "ELEVATED"
                ZoneStatus.HIGH -> "HIGH"
                ZoneStatus.CRITICAL -> "CRIT"
            }
            canvas.drawText(statusLabel, rect.right - 90f, rect.bottom - 22f, badgePaint)
        }
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_UP) {
            val touchX = event.x
            val touchY = event.y

            for (pair in zoneRects) {
                if (pair.first.contains(touchX, touchY)) {
                    performClick()
                    onZoneClickListener?.invoke(pair.second)
                    return true
                }
            }
        }
        return true
    }

    override fun performClick(): Boolean {
        super.performClick()
        return true
    }
}
