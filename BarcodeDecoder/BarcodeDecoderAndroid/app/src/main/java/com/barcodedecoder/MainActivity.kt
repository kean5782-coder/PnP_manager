package com.barcodedecoder

import android.Manifest
import android.app.UiModeManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentUris
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.util.Size
import android.view.KeyEvent
import android.view.View
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import com.barcodedecoder.camera.BarcodeAnalyzer
import com.barcodedecoder.camera.BarcodeBox
import com.barcodedecoder.databinding.ActivityMainBinding
import com.barcodedecoder.engine.ParseResult
import com.barcodedecoder.engine.RuleFactory
import com.barcodedecoder.engine.VendorParser
import com.barcodedecoder.util.AppLogger
import com.barcodedecoder.util.CrashHandler
import com.barcodedecoder.util.FeedbackHelper
import com.barcodedecoder.util.ImageEnhancer
import com.google.android.gms.tasks.Tasks
import com.google.android.material.bottomsheet.BottomSheetBehavior
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.net.URLEncoder
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Главный экран приложения:
 * - CameraX (Preview + ImageAnalysis в зоне ROI + ImageCapture для детального захвата).
 * - Панель из 3 основных элементов управления (Галерея с превью, Кнопка захвата кадра, Фонарик).
 * - Адаптация под вертикальную (снизу) и горизонтальную (справа) ориентации.
 * - Умный выбор штрихкодов с превью расшифровки из галереи и захваченных кадров.
 * - Навигация с пульта Android TV (DPAD).
 */
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var cameraExecutor: ExecutorService
    private var camera: Camera? = null
    private var imageCapture: ImageCapture? = null
    private var isTorchOn = false

    private lateinit var parser: VendorParser
    private var analyzer: BarcodeAnalyzer? = null

    // Регистрация запроса разрешений
    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val cameraGranted = permissions[Manifest.permission.CAMERA] ?: false
        if (cameraGranted) {
            binding.layoutPermission.visibility = View.GONE
            startCamera()
        } else {
            binding.layoutPermission.visibility = View.VISIBLE
        }
        loadLatestGalleryThumbnail()
    }

    // Регистрация выбора картинки из галереи
    private val pickImageLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) {
            decodeImageFromUri(uri)
        }
    }

    private val prefsName = "barcode_decoder_prefs"
    private val keyDisclaimerAccepted = "disclaimer_accepted"

    private fun isTvDevice(): Boolean {
        val uiModeManager = getSystemService(Context.UI_MODE_SERVICE) as? UiModeManager
        return (uiModeManager?.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION) ||
                !packageManager.hasSystemFeature(PackageManager.FEATURE_TOUCHSCREEN)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        CrashHandler.init(this)
        AppLogger.log("MainActivity", "App started")

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // Инициализация движка правил парсинга
        val rules = RuleFactory.createAllRules()
        parser = VendorParser(rules)

        cameraExecutor = Executors.newSingleThreadExecutor()

        setupListeners()

        val prefs = getSharedPreferences(prefsName, Context.MODE_PRIVATE)
        if (!prefs.getBoolean(keyDisclaimerAccepted, false)) {
            showDisclaimerDialog(isFirstLaunch = true)
        } else {
            checkPermissionsAndStart()
            checkPendingCrashReport()
        }
    }

    override fun onResume() {
        super.onResume()
        loadLatestGalleryThumbnail()
    }

    private fun checkPendingCrashReport() {
        val crashLog = AppLogger.getPendingCrashLog(this)
        if (!crashLog.isNullOrBlank()) {
            MaterialAlertDialogBuilder(this)
                .setTitle("Отчёт о сбое")
                .setMessage("Приложение аварийно завершило работу в прошлый раз. Отправить отчёт об ошибке разработчику (kean5782@yandex.ru)?")
                .setPositiveButton("Отправить") { _, _ ->
                    FeedbackHelper.sendEmail(this, "[BarcodeDecoder CrashReport]", crashLog)
                    AppLogger.clearCrashLog(this)
                }
                .setNegativeButton("Закрыть") { _, _ ->
                    AppLogger.clearCrashLog(this)
                }
                .show()
        }
    }

    private fun checkPermissionsAndStart() {
        val permissions = mutableListOf(Manifest.permission.CAMERA)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.READ_MEDIA_IMAGES)
        } else {
            permissions.add(Manifest.permission.READ_EXTERNAL_STORAGE)
        }

        val needed = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (needed.isEmpty() || ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
            binding.layoutPermission.visibility = View.GONE
            startCamera()
            loadLatestGalleryThumbnail()
        } else {
            requestPermissionLauncher.launch(permissions.toTypedArray())
        }
    }

    /**
     * Загружает миниатюру последнего изображения из галереи на кнопку [btnGallery].
     */
    private fun loadLatestGalleryThumbnail() {
        try {
            val hasStoragePerm = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                ContextCompat.checkSelfPermission(this, Manifest.permission.READ_MEDIA_IMAGES) == PackageManager.PERMISSION_GRANTED
            } else {
                ContextCompat.checkSelfPermission(this, Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
            }

            if (!hasStoragePerm) return

            cameraExecutor.execute {
                val projection = arrayOf(
                    MediaStore.Images.Media._ID,
                    MediaStore.Images.Media.DATE_ADDED
                )
                val sortOrder = "${MediaStore.Images.Media.DATE_ADDED} DESC"
                val cursor = contentResolver.query(
                    MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                    projection,
                    null,
                    null,
                    sortOrder
                )

                cursor?.use {
                    if (it.moveToFirst()) {
                        val idColumn = it.getColumnIndexOrThrow(MediaStore.Images.Media._ID)
                        val id = it.getLong(idColumn)
                        val contentUri = ContentUris.withAppendedId(
                            MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id
                        )

                        val thumbnailBitmap: Bitmap? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                            try {
                                contentResolver.loadThumbnail(contentUri, Size(128, 128), null)
                            } catch (e: Exception) {
                                null
                            }
                        } else {
                            try {
                                MediaStore.Images.Thumbnails.getThumbnail(
                                    contentResolver,
                                    id,
                                    MediaStore.Images.Thumbnails.MINI_KIND,
                                    null
                                )
                            } catch (e: Exception) {
                                null
                            }
                        }

                        if (thumbnailBitmap != null) {
                            runOnUiThread {
                                binding.ivGalleryThumb.setImageBitmap(thumbnailBitmap)
                                binding.ivGalleryThumb.visibility = View.VISIBLE
                                binding.ivGalleryIcon.visibility = View.GONE
                            }
                        }
                    }
                }
            }
        } catch (exc: Exception) {
            AppLogger.log("MainActivity", "Failed to load gallery thumbnail: ${exc.message}")
        }
    }

    private fun setupListeners() {
        binding.btnGrantPermission.setOnClickListener {
            checkPermissionsAndStart()
        }

        binding.btnFlashlight.setOnClickListener {
            toggleFlashlight()
        }

        binding.btnCapture.setOnClickListener {
            // Если на экране уже что-то распозналось «на лету» (подсвечено зеленым) — сразу открываем его
            val currentBoxes = binding.scannerOverlay.getBoxes()
            if (currentBoxes.isNotEmpty()) {
                val targetBox = binding.scannerOverlay.getFocusedOrFirstBox() ?: currentBoxes.first()
                onBarcodeSelected(targetBox)
                return@setOnClickListener
            }

            // Если пока ничего не распознано — выполняем усиленный поиск в замершем кадре
            captureAndIntensiveScan()
        }

        binding.btnGallery.setOnClickListener {
            openGallery()
        }

        binding.btnManualInput.setOnClickListener {
            showManualInputDialog()
        }

        binding.btnInfo.setOnClickListener {
            showDisclaimerDialog(isFirstLaunch = false)
        }

        binding.btnScanAgain.setOnClickListener {
            resumeScanning()
        }

        binding.scannerOverlay.onBarcodeSelected = { selectedBox ->
            onBarcodeSelected(selectedBox)
        }
    }

    /**
     * Замораживает кадр на экране, делает снимок в высоком разрешении и выполняет усиленный поиск.
     */
    private fun captureAndIntensiveScan() {
        // 1. Моментально «замораживаем» изображение на экране текущим кадром с PreviewView
        val previewBitmap = binding.previewView.bitmap
        if (previewBitmap != null) {
            binding.ivFrozenFrame.setImageBitmap(previewBitmap)
            binding.ivFrozenFrame.visibility = View.VISIBLE
        }

        analyzer?.isScanningEnabled = false
        binding.tvStatusHint.text = "Кадр зафиксирован. Усиленный поиск..."

        // Тактильная / визуальная анимация нажатия кнопки спуска
        binding.btnCapture.animate().scaleX(0.88f).scaleY(0.88f).setDuration(80).withEndAction {
            binding.btnCapture.animate().scaleX(1f).scaleY(1f).setDuration(80).start()
        }.start()

        val capture = imageCapture
        if (capture == null) {
            if (previewBitmap != null) {
                processCapturedBitmap(previewBitmap)
            } else {
                resumeScanning()
            }
            return
        }

        capture.takePicture(
            cameraExecutor,
            object : ImageCapture.OnImageCapturedCallback() {
                override fun onCaptureSuccess(imageProxy: ImageProxy) {
                    val fullBitmap = ImageEnhancer.imageProxyToBitmap(imageProxy)
                    imageProxy.close()
                    val bitmapToProcess = fullBitmap ?: previewBitmap

                    if (bitmapToProcess == null) {
                        runOnUiThread {
                            Toast.makeText(this@MainActivity, "Ошибка захвата кадра", Toast.LENGTH_SHORT).show()
                            resumeScanning()
                        }
                        return
                    }

                    if (fullBitmap != null) {
                        runOnUiThread {
                            binding.ivFrozenFrame.setImageBitmap(fullBitmap)
                        }
                    }

                    processCapturedBitmap(bitmapToProcess)
                }

                override fun onError(exception: ImageCaptureException) {
                    if (previewBitmap != null) {
                        processCapturedBitmap(previewBitmap)
                    } else {
                        runOnUiThread {
                            Toast.makeText(
                                this@MainActivity,
                                "Сбой захвата: ${exception.message}",
                                Toast.LENGTH_SHORT
                            ).show()
                            resumeScanning()
                        }
                    }
                }
            }
        )
    }

    /**
     * Обрабатывает зафиксированный кадр: кадрирует по зоне видоискателя и запускает многопроходный анализ.
     */
    private fun processCapturedBitmap(bitmap: Bitmap) {
        val roi = binding.scannerOverlay.getSearchRectOnScreen()
        val croppedBitmap = ImageEnhancer.cropToRoi(
            bitmap,
            roi,
            binding.previewView.width,
            binding.previewView.height
        )

        val detectedCodes = performMultiPassBarcodeDetection(croppedBitmap)

        runOnUiThread {
            if (detectedCodes.isEmpty()) {
                Toast.makeText(
                    this@MainActivity,
                    "Штрихкоды внутри зоны поиска не найдены",
                    Toast.LENGTH_SHORT
                ).show()
                resumeScanning()
            } else if (detectedCodes.size == 1) {
                val code = detectedCodes.first()
                binding.btnScanAgain.visibility = View.VISIBLE
                binding.tvStatusHint.text = "Захвачен код: $code"
                val parseResult = parser.parse(code)
                showResultBottomSheet(code, parseResult)
            } else {
                showBarcodeSelectionDialog(detectedCodes, "Найдено штрихкодов в кадре")
            }
        }
    }

    /**
     * Выполняет многопроходный цифровой анализ изображения (штрихкоды + оптическое распознавание текста OCR).
     */
    private fun performMultiPassBarcodeDetection(croppedBitmap: Bitmap): List<String> {
        val barcodeScanner = BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_ALL_FORMATS)
                .build()
        )
        val textRecognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

        val uniqueCodes = mutableSetOf<String>()

        fun scanBitmapSync(bmp: Bitmap) {
            try {
                val inputImage = InputImage.fromBitmap(bmp, 0)
                val barcodeTask = barcodeScanner.process(inputImage)
                val textTask = textRecognizer.process(inputImage)

                Tasks.await(Tasks.whenAllComplete(barcodeTask, textTask))

                if (barcodeTask.isSuccessful) {
                    for (barcode in barcodeTask.result) {
                        val value = barcode.rawValue ?: barcode.displayValue
                        if (!value.isNullOrBlank()) {
                            uniqueCodes.add(value.trim())
                        }
                    }
                }

                if (textTask.isSuccessful) {
                    for (block in textTask.result.textBlocks) {
                        for (line in block.lines) {
                            val lineText = line.text.trim()
                            if (lineText.length >= 3 && parser.parse(lineText) != null) {
                                uniqueCodes.add(lineText)
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                // Игнорируем единичные сбои фильтров
            }
        }

        // Проход 1: Исходный кадрированный кадр в высоком разрешении
        scanBitmapSync(croppedBitmap)
        if (uniqueCodes.isNotEmpty()) return uniqueCodes.toList()

        // Проход 2: Повышение контраста
        val contrastBitmap = ImageEnhancer.enhanceContrast(croppedBitmap)
        scanBitmapSync(contrastBitmap)
        if (uniqueCodes.isNotEmpty()) return uniqueCodes.toList()

        // Проход 3: Адаптивная бинаризация (для блеклой термопечати)
        val binarizedBitmap = ImageEnhancer.binarize(croppedBitmap, threshold = 120)
        scanBitmapSync(binarizedBitmap)
        if (uniqueCodes.isNotEmpty()) return uniqueCodes.toList()

        // Проход 4: Инвертированная бинаризация
        val invertedBitmap = ImageEnhancer.binarize(croppedBitmap, threshold = 120, invert = true)
        scanBitmapSync(invertedBitmap)
        if (uniqueCodes.isNotEmpty()) return uniqueCodes.toList()

        // Проход 5: 2x масштабирование для микро-DataMatrix
        val upscaledBitmap = ImageEnhancer.upscale(croppedBitmap, 2.0f)
        scanBitmapSync(upscaledBitmap)

        return uniqueCodes.toList()
    }

    private fun showDisclaimerDialog(isFirstLaunch: Boolean) {
        val dialogView = layoutInflater.inflate(R.layout.dialog_disclaimer, null)
        val btnOpenFeedback = dialogView.findViewById<View>(R.id.btnOpenFeedbackFromDisclaimer)
        btnOpenFeedback?.setOnClickListener {
            showFeedbackDialog(defaultCode = "")
        }

        val builder = MaterialAlertDialogBuilder(this)
            .setView(dialogView)
            .setCancelable(!isFirstLaunch)

        if (isFirstLaunch) {
            builder.setPositiveButton(getString(R.string.disclaimer_accept)) { _, _ ->
                getSharedPreferences(prefsName, Context.MODE_PRIVATE)
                    .edit()
                    .putBoolean(keyDisclaimerAccepted, true)
                    .apply()
                checkPermissionsAndStart()
            }
            builder.setNegativeButton(getString(R.string.disclaimer_decline)) { _, _ ->
                finish()
            }
            builder.setOnCancelListener {
                finish()
            }
        } else {
            builder.setPositiveButton(getString(R.string.disclaimer_close), null)
        }

        builder.show()
    }

    private fun showFeedbackDialog(defaultCode: String) {
        val dialogView = layoutInflater.inflate(R.layout.dialog_feedback, null)
        val etReportCode = dialogView.findViewById<EditText>(R.id.etReportCode)
        val etReportNotes = dialogView.findViewById<EditText>(R.id.etReportNotes)

        if (defaultCode.isNotEmpty()) {
            etReportCode.setText(defaultCode)
        }

        MaterialAlertDialogBuilder(this)
            .setView(dialogView)
            .setPositiveButton("Отправить Email") { _, _ ->
                val code = etReportCode.text.toString().trim()
                val notes = etReportNotes.text.toString().trim()
                val reportSubject = if (code.isNotEmpty()) {
                    "[BarcodeDecoder] Нераспознанный код: $code"
                } else {
                    "[BarcodeDecoder] Отзыв / Баг-репорт"
                }
                val reportBody = if (code.isNotEmpty()) {
                    FeedbackHelper.buildUnrecognizedCodeReport(this, code, notes)
                } else {
                    FeedbackHelper.buildGeneralFeedbackReport(this, "Баг-репорт / Отзыв", notes)
                }
                FeedbackHelper.sendEmail(this, reportSubject, reportBody)
            }
            .setNeutralButton("Поделиться") { _, _ ->
                val code = etReportCode.text.toString().trim()
                val notes = etReportNotes.text.toString().trim()
                val reportSubject = if (code.isNotEmpty()) {
                    "[BarcodeDecoder] Нераспознанный код: $code"
                } else {
                    "[BarcodeDecoder] Отзыв / Баг-репорт"
                }
                val reportBody = if (code.isNotEmpty()) {
                    FeedbackHelper.buildUnrecognizedCodeReport(this, code, notes)
                } else {
                    FeedbackHelper.buildGeneralFeedbackReport(this, "Баг-репорт / Отзыв", notes)
                }
                FeedbackHelper.shareText(this, reportSubject, reportBody)
            }
            .setNegativeButton("Отмена", null)
            .show()
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        when (keyCode) {
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER, KeyEvent.KEYCODE_BUTTON_A -> {
                if (analyzer?.isScanningEnabled == true) {
                    val targetBox = binding.scannerOverlay.getFocusedOrFirstBox()
                    if (targetBox != null) {
                        onBarcodeSelected(targetBox)
                        return true
                    }
                }
            }
            KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_DPAD_DOWN -> {
                if (analyzer?.isScanningEnabled == true) {
                    val nextBox = binding.scannerOverlay.selectNextBox()
                    if (nextBox != null) {
                        val tvPrefix = if (isTvDevice()) " [Пульт: Нажмите OK]" else ""
                        binding.tvStatusHint.text = "Выбран код: ${nextBox.rawValue}$tvPrefix"
                        return true
                    }
                }
            }
            KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_UP -> {
                if (analyzer?.isScanningEnabled == true) {
                    val prevBox = binding.scannerOverlay.selectPreviousBox()
                    if (prevBox != null) {
                        val tvPrefix = if (isTvDevice()) " [Пульт: Нажмите OK]" else ""
                        binding.tvStatusHint.text = "Выбран код: ${prevBox.rawValue}$tvPrefix"
                        return true
                    }
                }
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    /**
     * Настраивает и связывает сценарии Preview, ImageAnalysis и ImageCapture.
     */
    private fun startCamera() {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)

        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().also {
                it.setSurfaceProvider(binding.previewView.surfaceProvider)
            }

            analyzer = BarcodeAnalyzer(binding.previewView) { detectedBoxes ->
                runOnUiThread {
                    if (analyzer?.isScanningEnabled == true) {
                        binding.scannerOverlay.setBoxes(detectedBoxes)

                        val tvPrefix = if (isTvDevice()) " (Нажмите OK на пульте)" else ""
                        when (detectedBoxes.size) {
                            0 -> {
                                binding.tvStatusHint.text = getString(R.string.scanning_hint)
                            }
                            1 -> {
                                binding.tvStatusHint.text = "Найден 1 штрихкод$tvPrefix"
                            }
                            else -> {
                                binding.tvStatusHint.text = "Найдено ${detectedBoxes.size} штрихкодов. Выберите нужный$tvPrefix"
                            }
                        }
                    }
                }
            }

            // Связываем зону видоискателя для фильтрации штрихкодов "на лету"
            analyzer?.roiProvider = {
                binding.scannerOverlay.getSearchRectOnScreen()
            }

            // Связываем парсер для распознавания печатного текста (OCR) "на лету"
            analyzer?.textParser = { code ->
                parser.parse(code)
            }

            val imageAnalysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor, analyzer!!)
                }

            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
                .build()

            val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

            try {
                cameraProvider.unbindAll()
                camera = cameraProvider.bindToLifecycle(
                    this, cameraSelector, preview, imageAnalysis, imageCapture
                )
            } catch (exc: Exception) {
                Toast.makeText(this, "Ошибка запуска камеры: ${exc.message}", Toast.LENGTH_SHORT).show()
            }

        }, ContextCompat.getMainExecutor(this))
    }

    private fun toggleFlashlight() {
        val cam = camera ?: return
        if (cam.cameraInfo.hasFlashUnit()) {
            isTorchOn = !isTorchOn
            cam.cameraControl.enableTorch(isTorchOn)
            if (isTorchOn) {
                binding.ivFlashlightIcon.setColorFilter(ContextCompat.getColor(this, R.color.accent))
                binding.btnFlashlight.setCardBackgroundColor(ContextCompat.getColor(this, R.color.box_highlight_fill))
            } else {
                binding.ivFlashlightIcon.setColorFilter(ContextCompat.getColor(this, android.R.color.white))
                binding.btnFlashlight.setCardBackgroundColor(ContextCompat.getColor(this, R.color.card_surface))
            }
        } else {
            Toast.makeText(this, "Вспышка недоступна на этом устройстве", Toast.LENGTH_SHORT).show()
        }
    }

    private fun onBarcodeSelected(box: BarcodeBox) {
        val previewBitmap = binding.previewView.bitmap
        if (previewBitmap != null) {
            binding.ivFrozenFrame.setImageBitmap(previewBitmap)
            binding.ivFrozenFrame.visibility = View.VISIBLE
        }
        analyzer?.isScanningEnabled = false
        binding.btnScanAgain.visibility = View.VISIBLE
        binding.tvStatusHint.text = "Выбран код: ${box.rawValue}"

        val parseResult = parser.parse(box.rawValue)
        showResultBottomSheet(box.rawValue, parseResult)
    }

    private fun resumeScanning() {
        binding.ivFrozenFrame.visibility = View.GONE
        binding.ivFrozenFrame.setImageDrawable(null)
        binding.scannerOverlay.clear()
        analyzer?.isScanningEnabled = true
        binding.btnScanAgain.visibility = View.GONE
        binding.tvStatusHint.text = getString(R.string.scanning_hint)
    }

    /**
     * Отображает диалог выбора штрихкода с предосмотром расшифровки в скобках.
     */
    private fun showBarcodeSelectionDialog(codes: List<String>, titlePrefix: String) {
        val itemsWithPreview = codes.map { rawCode ->
            val result = parser.parse(rawCode)
            if (result != null) {
                "$rawCode (${result.unifiedName})"
            } else {
                "$rawCode (Не распознан)"
            }
        }.toTypedArray()

        MaterialAlertDialogBuilder(this)
            .setTitle(titlePrefix)
            .setItems(itemsWithPreview) { _, which ->
                val selectedCode = codes[which]
                binding.btnScanAgain.visibility = View.VISIBLE
                binding.tvStatusHint.text = "Выбран код: $selectedCode"
                val parseResult = parser.parse(selectedCode)
                showResultBottomSheet(selectedCode, parseResult)
            }
            .setNegativeButton("Отмена") { _, _ ->
                resumeScanning()
            }
            .show()
    }

    private fun showResultBottomSheet(rawCode: String, result: ParseResult?) {
        val dialog = BottomSheetDialog(this)
        val sheetView = layoutInflater.inflate(R.layout.bottom_sheet_result, null)
        dialog.setContentView(sheetView)

        val behavior = BottomSheetBehavior.from(sheetView.parent as View)
        behavior.state = BottomSheetBehavior.STATE_EXPANDED
        behavior.skipCollapsed = true

        val tvUnifiedName = sheetView.findViewById<TextView>(R.id.tvUnifiedName)
        val tvVendor = sheetView.findViewById<TextView>(R.id.tvVendor)
        val tvCompType = sheetView.findViewById<TextView>(R.id.tvCompType)
        val tvUsedCode = sheetView.findViewById<TextView>(R.id.tvUsedCode)
        val tvExtractedParams = sheetView.findViewById<TextView>(R.id.tvExtractedParams)
        val btnSearchWeb = sheetView.findViewById<View>(R.id.btnSearchWeb)
        val btnCopy = sheetView.findViewById<View>(R.id.btnCopy)
        val btnCloseSheet = sheetView.findViewById<View>(R.id.btnCloseSheet)
        val btnReportUnrecognized = sheetView.findViewById<View>(R.id.btnReportUnrecognized)

        val copyText: String
        val searchQuery: String

        if (result != null) {
            btnReportUnrecognized.visibility = View.GONE
            tvUnifiedName.text = result.unifiedName
            tvVendor.text = result.rule.name
            tvCompType.text = result.rule.compType
            val trimInfo = if (result.leftTrim > 0 || result.rightTrim > 0) {
                "${result.usedCode} (очищено: -${result.leftTrim} сл, -${result.rightTrim} спр)"
            } else {
                result.usedCode
            }
            tvUsedCode.text = trimInfo

            val paramsBuilder = StringBuilder()
            for ((k, v) in result.groups) {
                paramsBuilder.append("• $k: $v\n")
            }
            tvExtractedParams.text = paramsBuilder.toString().trimEnd()

            copyText = "Унифицированное имя: ${result.unifiedName}\n" +
                    "Производитель: ${result.rule.name}\n" +
                    "Тип: ${result.rule.compType}\n" +
                    "Код: ${result.usedCode}\n" +
                    paramsBuilder.toString()
            searchQuery = "${result.rule.name} ${result.usedCode} datasheet"
        } else {
            btnReportUnrecognized.visibility = View.VISIBLE
            btnReportUnrecognized.setOnClickListener {
                showFeedbackDialog(defaultCode = rawCode)
            }
            tvUnifiedName.text = "Не распознано"
            tvUnifiedName.setTextColor(ContextCompat.getColor(this, android.R.color.holo_red_light))
            tvVendor.text = "—"
            tvCompType.text = "—"
            tvUsedCode.text = rawCode
            tvExtractedParams.text = getString(R.string.not_recognized)
            copyText = "Код: $rawCode (Не распознан)"
            searchQuery = "$rawCode datasheet"
        }

        btnSearchWeb.setOnClickListener {
            if (searchQuery.isNotEmpty()) {
                try {
                    val encodedQuery = URLEncoder.encode(searchQuery, "UTF-8")
                    val searchUri = Uri.parse("https://www.google.com/search?q=$encodedQuery")
                    val browserIntent = Intent(Intent.ACTION_VIEW, searchUri)
                    startActivity(browserIntent)
                } catch (e: Exception) {
                    try {
                        val webSearchIntent = Intent(Intent.ACTION_WEB_SEARCH).apply {
                            putExtra(android.app.SearchManager.QUERY, searchQuery)
                        }
                        startActivity(webSearchIntent)
                    } catch (exc: Exception) {
                        Toast.makeText(this, getString(R.string.no_browser_found), Toast.LENGTH_SHORT).show()
                    }
                }
            } else {
                Toast.makeText(this, "Пустой запрос для поиска", Toast.LENGTH_SHORT).show()
            }
        }

        btnCopy.setOnClickListener {
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = ClipData.newPlainText("Barcode Result", copyText)
            clipboard.setPrimaryClip(clip)
            Toast.makeText(this, getString(R.string.copied_to_clipboard), Toast.LENGTH_SHORT).show()
        }

        btnCloseSheet.setOnClickListener {
            dialog.dismiss()
        }

        dialog.show()
    }

    private fun showManualInputDialog() {
        val dialogView = layoutInflater.inflate(R.layout.dialog_manual_input, null)
        val etManualCode = dialogView.findViewById<EditText>(R.id.etManualCode)

        MaterialAlertDialogBuilder(this)
            .setView(dialogView)
            .setPositiveButton(getString(R.string.decode_button)) { _, _ ->
                val inputCode = etManualCode.text.toString().trim()
                if (inputCode.isNotEmpty()) {
                    val result = parser.parse(inputCode)
                    showResultBottomSheet(inputCode, result)
                }
            }
            .setNegativeButton("Отмена", null)
            .show()
    }

    private fun openGallery() {
        try {
            pickImageLauncher.launch("image/*")
        } catch (exc: Exception) {
            Toast.makeText(this, "Не удалось открыть галерею: ${exc.message}", Toast.LENGTH_SHORT).show()
        }
    }

    private fun decodeImageFromUri(uri: Uri) {
        analyzer?.isScanningEnabled = false
        binding.scannerOverlay.clear()
        binding.tvStatusHint.text = "Обработка изображения из галереи..."

        val bitmap: Bitmap
        try {
            val inputStream = contentResolver.openInputStream(uri)
            val decoded = android.graphics.BitmapFactory.decodeStream(inputStream)
            inputStream?.close()
            if (decoded == null) {
                Toast.makeText(this, getString(R.string.image_processing_error), Toast.LENGTH_SHORT).show()
                resumeScanning()
                return
            }
            bitmap = decoded
        } catch (exc: Exception) {
            Toast.makeText(this, "${getString(R.string.image_processing_error)}: ${exc.localizedMessage}", Toast.LENGTH_LONG).show()
            resumeScanning()
            return
        }

        // Отображаем выбранное изображение на весь экран и отключаем затемнение видоискателя
        binding.ivFrozenFrame.setImageBitmap(bitmap)
        binding.ivFrozenFrame.visibility = View.VISIBLE
        binding.scannerOverlay.isScrimEnabled = false
        binding.btnScanAgain.visibility = View.VISIBLE

        val inputImage = InputImage.fromBitmap(bitmap, 0)
        val galleryScanner = BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_ALL_FORMATS)
                .build()
        )
        val textRecognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

        val barcodeTask = galleryScanner.process(inputImage)
        val textTask = textRecognizer.process(inputImage)

        Tasks.whenAllComplete(barcodeTask, textTask)
            .addOnSuccessListener {
                val boxes = mutableListOf<BarcodeBox>()
                val imageWidth = bitmap.width.toFloat()
                val imageHeight = bitmap.height.toFloat()
                val viewWidth = binding.scannerOverlay.width.toFloat()
                val viewHeight = binding.scannerOverlay.height.toFloat()

                // 1. Штрихкоды
                if (barcodeTask.isSuccessful) {
                    for (barcode in barcodeTask.result) {
                        val rawValue = barcode.rawValue ?: barcode.displayValue ?: continue
                        val boundingBox = barcode.boundingBox ?: continue
                        val screenRect = transformGalleryRect(boundingBox, imageWidth, imageHeight, viewWidth, viewHeight)
                        val parsed = parser.parse(rawValue)
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

                // 2. Распознанный печатный текст (OCR)
                if (textTask.isSuccessful) {
                    for (block in textTask.result.textBlocks) {
                        for (line in block.lines) {
                            val rawLine = line.text.trim()
                            if (rawLine.length < 3) continue

                            val parsed = parser.parse(rawLine) ?: continue
                            val boundingBox = line.boundingBox ?: continue
                            val screenRect = transformGalleryRect(boundingBox, imageWidth, imageHeight, viewWidth, viewHeight)

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

                if (boxes.isEmpty()) {
                    Toast.makeText(this, getString(R.string.no_barcodes_found_in_image), Toast.LENGTH_LONG).show()
                    binding.tvStatusHint.text = "Штрихкоды и маркировки не найдены. Нажмите «Сканировать заново»"
                } else {
                    binding.scannerOverlay.setBoxes(boxes)

                    val tvPrefix = if (isTvDevice()) " (Нажмите OK на пульте)" else ""
                    if (boxes.size == 1) {
                        val typeText = if (boxes[0].isTextOcr) "1 печатный код (OCR)" else "1 штрихкод"
                        binding.tvStatusHint.text = "Найден $typeText. Нажмите на зелёную рамку для расшифровки$tvPrefix"
                    } else {
                        binding.tvStatusHint.text = "Найдено ${boxes.size} элементов. Нажмите на нужную зелёную рамку$tvPrefix"
                    }
                }
            }
            .addOnFailureListener { exc ->
                Toast.makeText(this, "${getString(R.string.image_processing_error)}: ${exc.localizedMessage}", Toast.LENGTH_LONG).show()
                resumeScanning()
            }
    }

    /**
     * Преобразует координаты прямоугольника из исходного фото в экранные координаты ImageView (fitCenter).
     */
    private fun transformGalleryRect(
        sourceRect: android.graphics.Rect,
        imageWidth: Float,
        imageHeight: Float,
        viewWidth: Float,
        viewHeight: Float
    ): android.graphics.RectF {
        if (viewWidth <= 0f || viewHeight <= 0f || imageWidth <= 0f || imageHeight <= 0f) {
            return android.graphics.RectF(sourceRect)
        }

        val scaleX = viewWidth / imageWidth
        val scaleY = viewHeight / imageHeight
        val scale = minOf(scaleX, scaleY)

        val scaledWidth = imageWidth * scale
        val scaledHeight = imageHeight * scale
        val offsetX = (viewWidth - scaledWidth) / 2f
        val offsetY = (viewHeight - scaledHeight) / 2f

        val left = sourceRect.left * scale + offsetX
        val top = sourceRect.top * scale + offsetY
        val right = sourceRect.right * scale + offsetX
        val bottom = sourceRect.bottom * scale + offsetY

        return android.graphics.RectF(left, top, right, bottom)
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }
}
