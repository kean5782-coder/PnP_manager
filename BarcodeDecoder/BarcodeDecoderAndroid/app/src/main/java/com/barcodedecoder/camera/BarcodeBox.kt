package com.barcodedecoder.camera

import android.graphics.RectF

/**
 * Модель обнаруженного штрихкода на экране.
 *
 * @property rawValue Необработанная строка значения штрихкода (байты/текст).
 * @property displayValue Человекочитаемое отображение значения.
 * @property screenRect Экранные координаты для отрисовки рамки поверх PreviewView.
 * @property isSelected Флаг того, что штрихкод в данный момент выбран пользователем.
 * @property format Формат штрихкода (Code 128, Data Matrix, QR Code и т.д. по классификации ML Kit).
 */
data class BarcodeBox(
    val rawValue: String,
    val displayValue: String,
    val screenRect: RectF,
    var isSelected: Boolean = false,
    val format: Int = 0
)
