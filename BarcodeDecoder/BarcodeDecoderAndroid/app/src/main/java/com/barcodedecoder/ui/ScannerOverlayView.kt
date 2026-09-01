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
 * Кастомный View для отображения:
 * 1. Ограниченной зоны поиска штрихкода (видоискатель ROI + затемняющая маска Scrim).
 * 2. Подсветок обнаруженных штрихкодов, угловых меток и информационных бейджей.
 * 3. Интерактивного выбора по касанию и навигации с пульта DPAD Android TV.
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

    // Затемняющая маска вокруг видоискателя
    private val scrimPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.FILL
        color = Color.parseColor("#80000000") // 50% полупрозрачный черный
    }

    // Рамка видоискателя (угловые скобки)
    private val reticlePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 10f
        strokeCap = Paint.Cap.ROUND
        color = ContextCompat.getColor(context, R.color.accent)
    }

    // Тонкая окантовка окна видоискателя
    private val reticleBorderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 2f
        color = Color.parseColor("#40FFFFFF")
    }

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

    /** Текущий вычисленный прямоугольник видоискателя в экранных координатах */
    private val searchRect = RectF()

    /** Индекс текущего сфокусированного штрихкода (для навигации стрелками пульта/клавиатуры) */
    var focusedBoxIndex: Int = -1

    /**
     * Возвращает прямоугольник зоны поиска (видоискателя) в экранных координатах.
     */
    fun getSearchRectOnScreen(): RectF {
        if (searchRect.isEmpty && width > 0 && height > 0) {
            calculateSearchRect()
        }
        return RectF(searchRect)
    }

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        calculateSearchRect()
    }

    /**
     * Рассчитывает компактную зону поиска (видоискатель) с учетом ориентации экрана.
     */
    private fun calculateSearchRect() {
        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0f || h <= 0f) return

        if (w < h) {
            // Портретный режим: центрируем квадрат в верхне-средней части экрана
            val boxSize = w * 0.74f
            val left = (w - boxSize) / 2f
            // Смещаем чуть выше центра, чтобы освободить место снизу под панель управления (~110dp)
            val top = (h - boxSize) * 0.38f
            searchRect.set(left, top, left + boxSize, top + boxSize)
        } else {
            // Альбомный режим: центрируем квадрат слева от правой панели управления
            val boxSize = minOf(h * 0.70f, w * 0.55f)
            val left = (w * 0.85f - boxSize) / 2f
            val top = (h - boxSize) / 2f
            searchRect.set(left, top, left + boxSize, top + boxSize)
        }
    }

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
     * Возвращает список всех отображаемых рамок штрихкодов.
     */
    fun getBoxes(): List<BarcodeBox> = boxes

    /**
     * Проверяет, есть ли на экране обнаруженные штрихкоды.
     */
    fun hasBoxes(): Boolean = boxes.isNotEmpty()

    /** Включает/выключает затемняющую маску видоискателя (выключается при просмотре фото из галереи) */
    var isScrimEnabled: Boolean = true
        set(value) {
            field = value
            invalidate()
        }

    /**
     * Очищает состояние оверлея и сбрасывает фокус.
     */
    fun clear() {
        this.boxes = emptyList()
        this.selectedBox = null
        this.focusedBoxIndex = -1
        this.isScrimEnabled = true
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

        val w = width.toFloat()
        val h = height.toFloat()
        if (w <= 0f || h <= 0f) return

        if (searchRect.isEmpty) {
            calculateSearchRect()
        }

        // 1. Отрисовка затемнения (Scrim) вокруг окна видоискателя (если включено)
        if (isScrimEnabled) {
            // Верх
            canvas.drawRect(0f, 0f, w, searchRect.top, scrimPaint)
            // Низ
            canvas.drawRect(0f, searchRect.bottom, w, h, scrimPaint)
            // Лево
            canvas.drawRect(0f, searchRect.top, searchRect.left, searchRect.bottom, scrimPaint)
            // Право
            canvas.drawRect(searchRect.right, searchRect.top, w, searchRect.bottom, scrimPaint)

            // Тонкая полупрозрачная рамка видоискателя
            val cornerRadius = 24f
            canvas.drawRoundRect(searchRect, cornerRadius, cornerRadius, reticleBorderPaint)

            // Выразительные угловые скобки видоискателя
            drawViewfinderCorners(canvas, searchRect)
        }

        // 2. Отрисовка рамок обнаруженных штрихкодов
        val activeBoxes = if (selectedBox != null) listOf(selectedBox!!) else boxes

        for ((index, box) in activeBoxes.withIndex()) {
            val rect = box.screenRect
            val isSelected = (box == selectedBox)
            val isFocused = (selectedBox == null && index == focusedBoxIndex)

            val strokePaint = if (isSelected || isFocused) selectedBoxPaint else boxPaint
            val fillPaint = if (isSelected || isFocused) selectedFillPaint else boxFillPaint

            val boxRadius = 16f
            canvas.drawRoundRect(rect, boxRadius, boxRadius, fillPaint)
            drawCornerReticles(canvas, rect, strokePaint)

            // Текст бейджа
            val prefix = if (box.isTextOcr) "🔤 " else "🏷️ "
            val displayText = box.parsedUnifiedName ?: box.rawValue
            val text = if (displayText.length > 22) {
                prefix + displayText.substring(0, 19) + "..."
            } else {
                prefix + displayText
            }
            val hint = when {
                isSelected -> "✓ Выбрано"
                isFocused -> "★ Нажмите OK / Выбрать"
                box.isTextOcr -> "Печатный текст (OCR)"
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
     * Отрисовывает мощные угловые скобки зоны видоискателя (Google Lens style).
     */
    private fun drawViewfinderCorners(canvas: Canvas, rect: RectF) {
        val cornerLength = 48f
        val r = 16f

        // Верхний левый угол
        canvas.drawLine(rect.left + r, rect.top, rect.left + r + cornerLength, rect.top, reticlePaint)
        canvas.drawLine(rect.left, rect.top + r, rect.left, rect.top + r + cornerLength, reticlePaint)
        canvas.drawArc(rect.left, rect.top, rect.left + 2 * r, rect.top + 2 * r, 180f, 90f, false, reticlePaint)

        // Верхний правый угол
        canvas.drawLine(rect.right - r - cornerLength, rect.top, rect.right - r, rect.top, reticlePaint)
        canvas.drawLine(rect.right, rect.top + r, rect.right, rect.top + r + cornerLength, reticlePaint)
        canvas.drawArc(rect.right - 2 * r, rect.top, rect.right, rect.top + 2 * r, 270f, 90f, false, reticlePaint)

        // Нижний левый угол
        canvas.drawLine(rect.left + r, rect.bottom, rect.left + r + cornerLength, rect.bottom, reticlePaint)
        canvas.drawLine(rect.left, rect.bottom - r - cornerLength, rect.left, rect.bottom - r, reticlePaint)
        canvas.drawArc(rect.left, rect.bottom - 2 * r, rect.left + 2 * r, rect.bottom, 90f, 90f, false, reticlePaint)

        // Нижний правый угол
        canvas.drawLine(rect.right - r - cornerLength, rect.bottom, rect.right - r, rect.bottom, reticlePaint)
        canvas.drawLine(rect.right, rect.bottom - r - cornerLength, rect.right, rect.bottom - r, reticlePaint)
        canvas.drawArc(rect.right - 2 * r, rect.bottom - 2 * r, rect.right, rect.bottom, 0f, 90f, false, reticlePaint)
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
