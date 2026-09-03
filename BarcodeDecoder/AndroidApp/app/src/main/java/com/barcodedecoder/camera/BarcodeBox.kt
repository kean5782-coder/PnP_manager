package com.barcodedecoder.camera

import android.graphics.RectF

/**
 * Модель обнаруженного штрихкода или распознанного печатного текста компонента на экране.
 *
 * @property rawValue Необработанная строка значения штрихкода или OCR-текста.
 * @property displayValue Человекочитаемое отображение значения.
 * @property screenRect Экранные координаты для отрисовки рамки поверх PreviewView.
 * @property isSelected Флаг того, что элемент в данный момент выбран пользователем.
 * @property format Формат штрихкода (Code 128, Data Matrix, QR Code и т.д. по классификации ML Kit).
 * @property isTextOcr Истина, если элемент распознан оптическим распознаванием текста (OCR).
 * @property parsedUnifiedName Результат расшифровки (унифицированное имя, если распознано правилом).
 */
data class BarcodeBox(
    val rawValue: String,
    val displayValue: String,
    val screenRect: RectF,
    var isSelected: Boolean = false,
    val format: Int = 0,
    val isTextOcr: Boolean = false,
    val parsedUnifiedName: String? = null
)
