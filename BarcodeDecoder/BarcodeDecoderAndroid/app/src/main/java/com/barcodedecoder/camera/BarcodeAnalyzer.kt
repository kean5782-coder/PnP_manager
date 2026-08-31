package com.barcodedecoder.camera

import android.graphics.Rect
import android.graphics.RectF
import androidx.annotation.OptIn
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.view.PreviewView
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage

/**
 * Анализатор кадров CameraX с интеграцией Google ML Kit Barcode Scanning.
 *
 * Особенности:
 * 1. Дросселирование (throttling): обработка не чаще чем раз в 200 мс для экономии батареи и CPU.
 * 2. Автоматический учет ориентации кадра (rotationDegrees: 0, 90, 180, 270).
 * 3. Точная трансформация координат boundingBox из системы координат сенсора камеры
 *    в экранные координаты [PreviewView] с режимом масштабирования [PreviewView.ScaleType.FILL_CENTER].
 * 4. Гарантированное закрытие [ImageProxy] в [ImageAnalysis.Analyzer.analyze] для предотвращения утечек буфера камеры.
 *
 * @param previewView Виджет превью камеры для расчета коэффициентов масштабирования.
 * @param onBarcodesDetected Callback, вызываемый при обнаружении штрихкодов в кадре.
 */
class BarcodeAnalyzer(
    private val previewView: PreviewView,
    private val onBarcodesDetected: (List<BarcodeBox>) -> Unit
) : ImageAnalysis.Analyzer {

    private val scanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_ALL_FORMATS)
            .build()
    )

    private var lastAnalysisTimestamp = 0L
    private val scanIntervalMs = 200L // Интервал между анализами кадров

    @Volatile
    var isScanningEnabled: Boolean = true

    @OptIn(ExperimentalGetImage::class)
    override fun analyze(imageProxy: ImageProxy) {
        val currentTimestamp = System.currentTimeMillis()
        if (!isScanningEnabled || currentTimestamp - lastAnalysisTimestamp < scanIntervalMs) {
            imageProxy.close()
            return
        }

        val mediaImage = imageProxy.image
        if (mediaImage == null) {
            imageProxy.close()
            return
        }

        val rotationDegrees = imageProxy.imageInfo.rotationDegrees
        val inputImage = InputImage.fromMediaImage(mediaImage, rotationDegrees)

        lastAnalysisTimestamp = currentTimestamp

        // Расчет размеров повернутого изображения для нормализации координат ML Kit
        val imageWidth: Float
        val imageHeight: Float
        if (rotationDegrees == 90 || rotationDegrees == 270) {
            imageWidth = imageProxy.height.toFloat()
            imageHeight = imageProxy.width.toFloat()
        } else {
            imageWidth = imageProxy.width.toFloat()
            imageHeight = imageProxy.height.toFloat()
        }

        scanner.process(inputImage)
            .addOnSuccessListener { barcodes ->
                if (!isScanningEnabled) {
                    return@addOnSuccessListener
                }
                val boxes = barcodes.mapNotNull { barcode ->
                    val rawValue = barcode.rawValue ?: barcode.displayValue ?: return@mapNotNull null
                    val boundingBox = barcode.boundingBox ?: return@mapNotNull null
                    val screenRect = transformRect(boundingBox, imageWidth, imageHeight)
                    BarcodeBox(
                        rawValue = rawValue,
                        displayValue = barcode.displayValue ?: rawValue,
                        screenRect = screenRect,
                        format = barcode.format
                    )
                }
                onBarcodesDetected(boxes)
            }
            .addOnFailureListener {
                // Игнорируем единичные сбои кадров в потоковом видео
            }
            .addOnCompleteListener {
                // Всегда освобождаем буфер кадра
                imageProxy.close()
            }
    }

    /**
     * Преобразует координаты прямоугольника из пространства кадра камеры
     * в экранные координаты [PreviewView] с учетом масштабирования и центрирования.
     */
    private fun transformRect(sourceRect: Rect, imageWidth: Float, imageHeight: Float): RectF {
        val viewWidth = previewView.width.toFloat()
        val viewHeight = previewView.height.toFloat()

        if (viewWidth <= 0 || viewHeight <= 0 || imageWidth <= 0 || imageHeight <= 0) {
            return RectF(sourceRect)
        }

        // PreviewView использует режим FILL_CENTER: масштабирование по максимальному коэффициенту
        val scaleX = viewWidth / imageWidth
        val scaleY = viewHeight / imageHeight
        val scale = maxOf(scaleX, scaleY)

        val scaledImageWidth = imageWidth * scale
        val scaledImageHeight = imageHeight * scale
        val offsetX = (viewWidth - scaledImageWidth) / 2f
        val offsetY = (viewHeight - scaledImageHeight) / 2f

        val left = sourceRect.left * scale + offsetX
        val top = sourceRect.top * scale + offsetY
        val right = sourceRect.right * scale + offsetX
        val bottom = sourceRect.bottom * scale + offsetY

        return RectF(left, top, right, bottom)
    }
}
