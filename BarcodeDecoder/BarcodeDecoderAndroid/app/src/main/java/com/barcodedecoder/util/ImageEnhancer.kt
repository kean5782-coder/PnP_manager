package com.barcodedecoder.util

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.ColorMatrix
import android.graphics.ColorMatrixColorFilter
import android.graphics.ImageFormat
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Rect
import android.graphics.RectF
import android.graphics.YuvImage
import androidx.camera.core.ImageProxy
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer

/**
 * Утилиты для высокоточного захвата, кадрирования и многопроходной цифровой обработки
 * изображений штрихкодов с катушек (контрастирование, бинаризация, масштабирование).
 */
object ImageEnhancer {

    /**
     * Преобразует [ImageProxy] из CameraX в ориентированный [Bitmap].
     */
    fun imageProxyToBitmap(imageProxy: ImageProxy): Bitmap? {
        val rotationDegrees = imageProxy.imageInfo.rotationDegrees
        val bitmap = when (imageProxy.format) {
            ImageFormat.JPEG -> {
                val buffer: ByteBuffer = imageProxy.planes[0].buffer
                val bytes = ByteArray(buffer.remaining())
                buffer.get(bytes)
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            }
            ImageFormat.YUV_420_888 -> {
                yuv420ToBitmap(imageProxy)
            }
            else -> {
                val buffer = imageProxy.planes[0].buffer
                val bytes = ByteArray(buffer.remaining())
                buffer.get(bytes)
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
            }
        } ?: return null

        return if (rotationDegrees != 0) {
            val matrix = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
            val rotated = Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
            if (rotated != bitmap) {
                bitmap.recycle()
            }
            rotated
        } else {
            bitmap
        }
    }

    private fun yuv420ToBitmap(imageProxy: ImageProxy): Bitmap? {
        val planes = imageProxy.planes
        val yBuffer = planes[0].buffer
        val uBuffer = planes[1].buffer
        val vBuffer = planes[2].buffer

        val ySize = yBuffer.remaining()
        val uSize = uBuffer.remaining()
        val vSize = vBuffer.remaining()

        val nv21 = ByteArray(ySize + uSize + vSize)
        yBuffer.get(nv21, 0, ySize)
        vBuffer.get(nv21, ySize, vSize)
        uBuffer.get(nv21, ySize + vSize, uSize)

        val yuvImage = YuvImage(nv21, ImageFormat.NV21, imageProxy.width, imageProxy.height, null)
        val out = ByteArrayOutputStream()
        yuvImage.compressToJpeg(Rect(0, 0, imageProxy.width, imageProxy.height), 100, out)
        val imageBytes = out.toByteArray()
        return BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.size)
    }

    /**
     * Кадрирует [Bitmap] строго по зоне поиска [roiOnScreen].
     */
    fun cropToRoi(bitmap: Bitmap, roiOnScreen: RectF, viewWidth: Int, viewHeight: Int): Bitmap {
        if (viewWidth <= 0 || viewHeight <= 0 || roiOnScreen.isEmpty) {
            return bitmap
        }

        val bw = bitmap.width.toFloat()
        val bh = bitmap.height.toFloat()
        val vw = viewWidth.toFloat()
        val vh = viewHeight.toFloat()

        val scale = maxOf(vw / bw, vh / bh)
        val scaledWidth = bw * scale
        val scaledHeight = bh * scale
        val offsetX = (vw - scaledWidth) / 2f
        val offsetY = (vh - scaledHeight) / 2f

        val leftInBmp = maxOf(0f, (roiOnScreen.left - offsetX) / scale)
        val topInBmp = maxOf(0f, (roiOnScreen.top - offsetY) / scale)
        val rightInBmp = minOf(bw, (roiOnScreen.right - offsetX) / scale)
        val bottomInBmp = minOf(bh, (roiOnScreen.bottom - offsetY) / scale)

        val cropWidth = (rightInBmp - leftInBmp).toInt()
        val cropHeight = (bottomInBmp - topInBmp).toInt()

        return if (cropWidth > 10 && cropHeight > 10) {
            Bitmap.createBitmap(bitmap, leftInBmp.toInt(), topInBmp.toInt(), cropWidth, cropHeight)
        } else {
            bitmap
        }
    }

    /**
     * Повышает контраст и резкость (помогает при выцветшей или нечеткой термопечати).
     */
    fun enhanceContrast(src: Bitmap): Bitmap {
        val dest = Bitmap.createBitmap(src.width, src.height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(dest)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)

        val cm = ColorMatrix().apply {
            // Увеличение контраста x1.6 с компенсацией яркости
            set(floatArrayOf(
                1.6f, 0f, 0f, 0f, -45f,
                0f, 1.6f, 0f, 0f, -45f,
                0f, 0f, 1.6f, 0f, -45f,
                0f, 0f, 0f, 1f, 0f
            ))
        }
        paint.colorFilter = ColorMatrixColorFilter(cm)
        canvas.drawBitmap(src, 0f, 0f, paint)
        return dest
    }

    /**
     * Выполняет адаптивную пороговую бинаризацию (черно-белое разделение).
     */
    fun binarize(src: Bitmap, threshold: Int = 128, invert: Boolean = false): Bitmap {
        val width = src.width
        val height = src.height
        val pixels = IntArray(width * height)
        src.getPixels(pixels, 0, width, 0, 0, width, height)

        for (i in pixels.indices) {
            val color = pixels[i]
            val r = Color.red(color)
            val g = Color.green(color)
            val b = Color.blue(color)
            // Формула яркости по ITU-R BT.601
            val gray = (0.299 * r + 0.587 * g + 0.114 * b).toInt()

            val isWhite = if (invert) gray < threshold else gray >= threshold
            pixels[i] = if (isWhite) Color.WHITE else Color.BLACK
        }

        val dest = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        dest.setPixels(pixels, 0, width, 0, 0, width, height)
        return dest
    }

    /**
     * Масштабирует изображение в 2 раза для обнаружения микро-кодов (DataMatrix 2x2 мм).
     */
    fun upscale(src: Bitmap, factor: Float = 2.0f): Bitmap {
        val targetWidth = (src.width * factor).toInt()
        val targetHeight = (src.height * factor).toInt()
        return Bitmap.createScaledBitmap(src, targetWidth, targetHeight, true)
    }
}
