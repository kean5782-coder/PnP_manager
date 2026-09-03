package com.barcodedecoder.camera

import android.graphics.Rect
import android.graphics.RectF
import androidx.annotation.OptIn
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.view.PreviewView
import com.barcodedecoder.engine.ParseResult
import com.google.android.gms.tasks.Tasks
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions

/**
 * Анализатор кадров CameraX с параллельной интеграцией:
 * 1. Google ML Kit Barcode Scanning (все 1D и 2D форматы штрихкодов).
 * 2. Google ML Kit Text Recognition (OCR оптическое распознавание печатных названий компонентов).
 */
class BarcodeAnalyzer(
    private val previewView: PreviewView,
    private val onBarcodesDetected: (List<BarcodeBox>) -> Unit
) : ImageAnalysis.Analyzer {

    private val barcodeScanner = BarcodeScanning.getClient(
        BarcodeScannerOptions.Builder()
            .setBarcodeFormats(Barcode.FORMAT_ALL_FORMATS)
            .build()
    )

    private val textRecognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    private var lastAnalysisTimestamp = 0L
    private val scanIntervalMs = 200L // Интервал между анализами кадров

    @Volatile
    var isScanningEnabled: Boolean = true

    /** Поставщик зоны поиска (ROI видоискателя) в экранных координатах */
    var roiProvider: (() -> RectF)? = null

    /** Парсер правил для валидации и расшифровки распознанного печатного текста */
    var textParser: ((String) -> ParseResult?)? = null

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

        val currentRoi = roiProvider?.invoke()

        val barcodeTask = barcodeScanner.process(inputImage)
        val textTask = textRecognizer.process(inputImage)

        Tasks.whenAllComplete(barcodeTask, textTask)
            .addOnSuccessListener {
                if (!isScanningEnabled) return@addOnSuccessListener
                val boxes = mutableListOf<BarcodeBox>()

                // 1. Обработка обнаруженных штрихкодов
                if (barcodeTask.isSuccessful) {
                    val barcodes = barcodeTask.result
                    for (barcode in barcodes) {
                        val rawValue = barcode.rawValue ?: barcode.displayValue ?: continue
                        val boundingBox = barcode.boundingBox ?: continue
                        val screenRect = transformRect(boundingBox, imageWidth, imageHeight)

                        if (currentRoi != null && !currentRoi.isEmpty) {
                            val centerX = screenRect.centerX()
                            val centerY = screenRect.centerY()
                            if (!currentRoi.contains(centerX, centerY) && !RectF.intersects(currentRoi, screenRect)) {
                                continue
                            }
                        }

                        val parsed = textParser?.invoke(rawValue)
                        boxes.add(
                            BarcodeBox(
                                rawValue = rawValue,
                                displayValue = barcode.displayValue ?: rawValue,
                                screenRect = screenRect,
                                format = barcode.format,
                                isTextOcr = false,
                                parsedUnifiedName = parsed?.unifiedName
                            )
                        )
                    }
                }

                // 2. Обработка распознанного печатного текста (OCR)
                if (textTask.isSuccessful) {
                    val visionText = textTask.result
                    for (block in visionText.textBlocks) {
                        for (line in block.lines) {
                            val rawLine = line.text.trim()
                            if (rawLine.length < 3) continue

                            val parsed = textParser?.invoke(rawLine) ?: continue
                            val boundingBox = line.boundingBox ?: continue
                            val screenRect = transformRect(boundingBox, imageWidth, imageHeight)

                            if (currentRoi != null && !currentRoi.isEmpty) {
                                val centerX = screenRect.centerX()
                                val centerY = screenRect.centerY()
                                if (!currentRoi.contains(centerX, centerY) && !RectF.intersects(currentRoi, screenRect)) {
                                    continue
                                }
                            }

                            val isDuplicate = boxes.any {
                                it.rawValue.equals(rawLine, ignoreCase = true) ||
                                (it.parsedUnifiedName != null && it.parsedUnifiedName == parsed.unifiedName)
                            }
                            if (!isDuplicate) {
                                boxes.add(
                                    BarcodeBox(
                                        rawValue = rawLine,
                                        displayValue = rawLine,
                                        screenRect = screenRect,
                                        isTextOcr = true,
                                        parsedUnifiedName = parsed.unifiedName
                                    )
                                )
                            }
                        }
                    }
                }

                onBarcodesDetected(boxes)
            }
            .addOnFailureListener {
                // Игнорируем единичные сбои кадров в потоковом видео
            }
            .addOnCompleteListener {
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
