package com.barcodedecoder.camera

import android.graphics.RectF

data class BarcodeBox(
    val rawValue: String,
    val displayValue: String,
    val screenRect: RectF,
    var isSelected: Boolean = false,
    val format: Int = 0
)
