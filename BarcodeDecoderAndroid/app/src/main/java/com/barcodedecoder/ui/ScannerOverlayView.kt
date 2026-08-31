package com.barcodedecoder.ui

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import androidx.core.content.ContextCompat
import com.barcodedecoder.R
import com.barcodedecoder.camera.BarcodeBox

/**
 * Кастомный View для отображения подсветок штрихкодов, угловых меток, информационных бейджей
 * и обработки интерактивного выбора (тач-клики и навигация с пульта DPAD Android TV).
 */
class ScannerOverlayView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyleAttr: Int = 0
) : View(context, attrs, defStyleAttr) {

    private var boxes: List<BarcodeBox> = emptyList()
    private var selectedBox: BarcodeBox? = null

    /** Callback при выборе пользователем конкретного штрихкода */
    var onBarcodeSelected: ((BarcodeBox) -> Unit)? = null

    // Кисти для обычной подсветки обнаруженных рамок
    private val boxPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 6f
        color = ContextCompat.getColor(context, R.color.box_highlight)
    }

    private val boxFillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = ContextCompat.getColor(context, R.color.box_highlight_fill)
    }

    // Кисти для выбранной / сфокусированной рамки
    private val selectedBoxPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 8f
        color = ContextCompat.getColor(context, R.color.box_selected)
    }

    private val selectedFillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = ContextCompat.getColor(context, R.color.box_selected_fill)
    }

    // Кисти для бейджа с текстом значения
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

    /** Индекс текущего сфокусированного штрихкода (для навигации стрелками пульта/клавиатуры) */
    var focusedBoxIndex: Int = -1

    /**
     * Обновляет список отображаемых рамок штрихкодов.
     */
    fun setBoxes(newBoxes: List<BarcodeBox>) {
        if (selectedBox != null) {
            // Если уже выбран конкретный элемент, не перезаписываем до сброса
            return
        }
        this.boxes = newBoxes
        if (focusedBoxIndex >= newBoxes.size || (focusedBoxIndex == -1 && newBoxes.isNotEmpty())) {
            focusedBoxIndex = if (newBoxes.isNotEmpty()) 0 else -1
        }
        invalidate()
    }

    /**
     * Устанавливает выбранный штрихкод.
     */
    fun selectBox(box: BarcodeBox) {
        this.selectedBox = box
        invalidate()
    }

    /**
     * Переключает фокус на следующий обнаруженный штрихкод (DPAD RIGHT / DOWN).
     */
    fun selectNextBox(): BarcodeBox? {
        if (boxes.isEmpty()) return null
        focusedBoxIndex = (focusedBoxIndex + 1) % boxes.size
        invalidate()
        return boxes[focusedBoxIndex]
    }

    /**
     * Переключает фокус на предыдущий обнаруженный штрихкод (DPAD LEFT / UP).
     */
    fun selectPreviousBox(): BarcodeBox? {
        if (boxes.isEmpty()) return null
        focusedBoxIndex = if (focusedBoxIndex <= 0) boxes.size - 1 else focusedBoxIndex - 1
        invalidate()
        return boxes[focusedBoxIndex]
    }

    /**
     * Возвращает текущий сфокусированный или первый доступный штрихкод.
     */
    fun getFocusedOrFirstBox(): BarcodeBox? {
        if (boxes.isEmpty()) return null
        return if (focusedBoxIndex in boxes.indices) boxes[focusedBoxIndex] else boxes.first()
    }

    /**
     * Очищает состояние оверлея и сбрасывает фокус.
     */
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

            // Расширенная область нажатия (+40px) для комфортного тапа пальцем
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

            // Отрисовка полупрозрачного фона и угловых визирных линий
            canvas.drawRoundRect(rect, cornerRadius, cornerRadius, fillPaint)
            drawCornerReticles(canvas, rect, strokePaint)

            // Текст бейджа
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

            // Расчет позиции бейджа: сверху от рамки или снизу, если сверху нет места
            var badgeTop = rect.top - badgeHeight - 12f
            if (badgeTop < 20f) {
                badgeTop = rect.bottom + 12f
            }
            // Ограничение по границам экрана
            if (badgeTop + badgeHeight > height - 16f) {
                badgeTop = maxOf(16f, rect.top - badgeHeight - 12f)
            }
            val badgeLeft = maxOf(16f, minOf(rect.left, width - badgeWidth - 16f))
            val badgeRect = RectF(badgeLeft, badgeTop, badgeLeft + badgeWidth, badgeTop + badgeHeight)

            canvas.drawRoundRect(badgeRect, 14f, 14f, badgeBgPaint)
            canvas.drawText(text, badgeLeft + 18f, badgeTop + 36f, textPaint)
            canvas.drawText(hint, badgeLeft + 18f, badgeTop + 68f, hintTextPaint)
        }
    }

    /**
     * Отрисовывает угловые маркеры видоискателя на рамке штрихкода.
     */
    private fun drawCornerReticles(canvas: Canvas, rect: RectF, paint: Paint) {
        val cornerLength = minOf(rect.width() * 0.25f, rect.height() * 0.25f, 40f)

        // Верхний левый угол
        canvas.drawLine(rect.left, rect.top, rect.left + cornerLength, rect.top, paint)
        canvas.drawLine(rect.left, rect.top, rect.left, rect.top + cornerLength, paint)

        // Верхний правый угол
        canvas.drawLine(rect.right, rect.top, rect.right - cornerLength, rect.top, paint)
        canvas.drawLine(rect.right, rect.top, rect.right, rect.top + cornerLength, paint)

        // Нижний левый угол
        canvas.drawLine(rect.left, rect.bottom, rect.left + cornerLength, rect.bottom, paint)
        canvas.drawLine(rect.left, rect.bottom, rect.left, rect.bottom - cornerLength, paint)

        // Нижний правый угол
        canvas.drawLine(rect.right, rect.bottom, rect.right - cornerLength, rect.bottom, paint)
        canvas.drawLine(rect.right, rect.bottom, rect.right, rect.bottom - cornerLength, paint)
    }
}
