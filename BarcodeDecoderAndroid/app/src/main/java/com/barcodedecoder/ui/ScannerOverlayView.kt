package com.barcodedecoder.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.content.ContextCompat
import com.barcodedecoder.R
import com.barcodedecoder.camera.BarcodeBox

class ScannerOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var boxes: List<BarcodeBox> = emptyList()
    private var selectedBox: BarcodeBox? = null

    var onBarcodeSelected: ((BarcodeBox) -> Unit)? = null

    private val boxPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 6f
        color = ContextCompat.getColor(context, R.color.box_highlight)
    }

    private val boxFillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = ContextCompat.getColor(context, R.color.box_highlight_fill)
    }

    private val selectedBoxPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 8f
        color = ContextCompat.getColor(context, R.color.box_selected)
    }

    private val selectedFillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = ContextCompat.getColor(context, R.color.box_selected_fill)
    }

    private val badgeBgPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = ContextCompat.getColor(context, R.color.box_badge_bg)
    }

    private val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 34f
        isFakeBoldText = true
    }

    private val hintTextPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = ContextCompat.getColor(context, R.color.accent)
        textSize = 28f
    }

    var focusedBoxIndex: Int = -1

    fun setBoxes(newBoxes: List<BarcodeBox>) {
        if (selectedBox != null) {
            // If already selected, do not overwrite until cleared
            return
        }
        this.boxes = newBoxes
        if (focusedBoxIndex >= newBoxes.size || (focusedBoxIndex == -1 && newBoxes.isNotEmpty())) {
            focusedBoxIndex = if (newBoxes.isNotEmpty()) 0 else -1
        }
        invalidate()
    }

    fun selectBox(box: BarcodeBox) {
        this.selectedBox = box
        invalidate()
    }

    fun selectNextBox(): BarcodeBox? {
        if (boxes.isEmpty()) return null
        focusedBoxIndex = (focusedBoxIndex + 1) % boxes.size
        invalidate()
        return boxes[focusedBoxIndex]
    }

    fun selectPreviousBox(): BarcodeBox? {
        if (boxes.isEmpty()) return null
        focusedBoxIndex = if (focusedBoxIndex <= 0) boxes.size - 1 else focusedBoxIndex - 1
        invalidate()
        return boxes[focusedBoxIndex]
    }

    fun getFocusedOrFirstBox(): BarcodeBox? {
        if (boxes.isEmpty()) return null
        return if (focusedBoxIndex in boxes.indices) boxes[focusedBoxIndex] else boxes.first()
    }

    fun clear() {
        this.boxes = emptyList()
        this.selectedBox = null
        this.focusedBoxIndex = -1
        invalidate()
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (event.action == MotionEvent.ACTION_DOWN) {
            val x = event.x
            val y = event.y

            // Touch padding of 40px for comfortable tap target
            val touchPadding = 40f

            for (box in boxes) {
                val expandedRect = RectF(
                    box.screenRect.left - touchPadding,
                    box.screenRect.top - touchPadding,
                    box.screenRect.right + touchPadding,
                    box.screenRect.bottom + touchPadding
                )

                if (expandedRect.contains(x, y)) {
                    selectedBox = box
                    box.isSelected = true
                    invalidate()
                    onBarcodeSelected?.invoke(box)
                    return true
                }
            }
        }
        return super.onTouchEvent(event)
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        val activeBoxes = if (selectedBox != null) listOf(selectedBox!!) else boxes

        for ((index, box) in activeBoxes.withIndex()) {
            val rect = box.screenRect
            val isSelected = (box == selectedBox)
            val isFocused = (selectedBox == null && index == focusedBoxIndex)

            val strokePaint = if (isSelected || isFocused) selectedBoxPaint else boxPaint
            val fillPaint = if (isSelected || isFocused) selectedFillPaint else boxFillPaint

            val cornerRadius = 16f

            // Fill & border
            canvas.drawRoundRect(rect, cornerRadius, cornerRadius, fillPaint)
            drawCornerReticles(canvas, rect, strokePaint)

            // Text badge on top or bottom
            val text = if (box.rawValue.length > 22) {
                box.rawValue.substring(0, 19) + "..."
            } else {
                box.rawValue
            }
            val hint = when {
                isSelected -> "✓ Выбрано"
                isFocused -> "★ Нажмите OK / Выбрать"
                else -> "Нажмите для выбора"
            }

            val textWidth = textPaint.measureText(text)
            val hintWidth = hintTextPaint.measureText(hint)
            val badgeWidth = maxOf(textWidth, hintWidth) + 36f
            val badgeHeight = 80f

            var badgeTop = rect.top - badgeHeight - 12f
            if (badgeTop < 20f) {
                badgeTop = rect.bottom + 12f
            }
            val badgeLeft = maxOf(16f, minOf(rect.left, width - badgeWidth - 16f))
            val badgeRect = RectF(badgeLeft, badgeTop, badgeLeft + badgeWidth, badgeTop + badgeHeight)

            canvas.drawRoundRect(badgeRect, 14f, 14f, badgeBgPaint)
            canvas.drawText(text, badgeLeft + 18f, badgeTop + 36f, textPaint)
            canvas.drawText(hint, badgeLeft + 18f, badgeTop + 68f, hintTextPaint)
        }
    }

    private fun drawCornerReticles(canvas: Canvas, rect: RectF, paint: Paint) {
        val cornerLength = minOf(rect.width() * 0.25f, rect.height() * 0.25f, 40f)

        // Top-Left
        canvas.drawLine(rect.left, rect.top, rect.left + cornerLength, rect.top, paint)
        canvas.drawLine(rect.left, rect.top, rect.left, rect.top + cornerLength, paint)

        // Top-Right
        canvas.drawLine(rect.right, rect.top, rect.right - cornerLength, rect.top, paint)
        canvas.drawLine(rect.right, rect.top, rect.right, rect.top + cornerLength, paint)

        // Bottom-Left
        canvas.drawLine(rect.left, rect.bottom, rect.left + cornerLength, rect.bottom, paint)
        canvas.drawLine(rect.left, rect.bottom, rect.left, rect.bottom - cornerLength, paint)

        // Bottom-Right
        canvas.drawLine(rect.right, rect.bottom, rect.right - cornerLength, rect.bottom, paint)
        canvas.drawLine(rect.right, rect.bottom, rect.right, rect.bottom - cornerLength, paint)
    }
}
