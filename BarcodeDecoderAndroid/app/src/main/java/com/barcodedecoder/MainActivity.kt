package com.barcodedecoder

import android.Manifest
import android.app.UiModeManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.net.Uri
import java.net.URLEncoder
import android.os.Bundle
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
import com.google.android.material.bottomsheet.BottomSheetBehavior
import com.google.android.material.bottomsheet.BottomSheetDialog
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.common.InputImage
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var cameraExecutor: ExecutorService
    private var camera: Camera? = null
    private var isTorchOn = false

    private lateinit var parser: VendorParser
    private var analyzer: BarcodeAnalyzer? = null

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        if (isGranted) {
            binding.layoutPermission.visibility = View.GONE
            startCamera()
        } else {
            binding.layoutPermission.visibility = View.VISIBLE
        }
    }

    private val pickImageLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) {
            decodeImageFromUri(uri)
        }
    }

    private val PREFS_NAME = "barcode_decoder_prefs"
    private val KEY_DISCLAIMER_ACCEPTED = "disclaimer_accepted"

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

        // Initialize decoding engine
        val rules = RuleFactory.createAllRules()
        parser = VendorParser(rules)

        cameraExecutor = Executors.newSingleThreadExecutor()

        setupListeners()

        val prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        if (!prefs.getBoolean(KEY_DISCLAIMER_ACCEPTED, false)) {
            showDisclaimerDialog(isFirstLaunch = true)
        } else {
            checkPermissionsAndStart()
            checkPendingCrashReport()
        }
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
        if (allPermissionsGranted()) {
            startCamera()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    private fun setupListeners() {
        binding.btnGrantPermission.setOnClickListener {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        binding.btnFlashlight.setOnClickListener {
            toggleFlashlight()
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
                getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                    .edit()
                    .putBoolean(KEY_DISCLAIMER_ACCEPTED, true)
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

    private fun allPermissionsGranted() = ContextCompat.checkSelfPermission(
        this, Manifest.permission.CAMERA
    ) == PackageManager.PERMISSION_GRANTED

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

            val imageAnalysis = ImageAnalysis.Builder()
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()
                .also {
                    it.setAnalyzer(cameraExecutor, analyzer!!)
                }

            val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

            try {
                cameraProvider.unbindAll()
                camera = cameraProvider.bindToLifecycle(
                    this, cameraSelector, preview, imageAnalysis
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
            binding.btnFlashlight.setIconResource(R.drawable.ic_flashlight)
            if (isTorchOn) {
                binding.btnFlashlight.setIconTintResource(R.color.accent)
            } else {
                binding.btnFlashlight.setIconTintResource(android.R.color.white)
            }
        } else {
            Toast.makeText(this, "Вспышка недоступна на этом устройстве", Toast.LENGTH_SHORT).show()
        }
    }

    private fun onBarcodeSelected(box: BarcodeBox) {
        analyzer?.isScanningEnabled = false
        binding.btnScanAgain.visibility = View.VISIBLE
        binding.tvStatusHint.text = "Выбран код: ${box.rawValue}"

        val parseResult = parser.parse(box.rawValue)
        showResultBottomSheet(box.rawValue, parseResult)
    }

    private fun resumeScanning() {
        binding.scannerOverlay.clear()
        analyzer?.isScanningEnabled = true
        binding.btnScanAgain.visibility = View.GONE
        binding.tvStatusHint.text = getString(R.string.scanning_hint)
    }

    private fun showResultBottomSheet(rawCode: String, result: ParseResult?) {
        val dialog = BottomSheetDialog(this)
        val view = layoutInflater.inflate(R.layout.bottom_sheet_result, null)
        dialog.setContentView(view)
        dialog.behavior.state = BottomSheetBehavior.STATE_EXPANDED
        dialog.behavior.skipCollapsed = true

        val tvUnifiedName = view.findViewById<TextView>(R.id.tvUnifiedName)
        val tvVendor = view.findViewById<TextView>(R.id.tvVendor)
        val tvCompType = view.findViewById<TextView>(R.id.tvCompType)
        val tvUsedCode = view.findViewById<TextView>(R.id.tvUsedCode)
        val tvExtractedParams = view.findViewById<TextView>(R.id.tvExtractedParams)
        val btnCopy = view.findViewById<View>(R.id.btnCopy)
        val btnCloseSheet = view.findViewById<View>(R.id.btnCloseSheet)
        val btnReportUnrecognized = view.findViewById<View>(R.id.btnReportUnrecognized)
        val btnSearchWeb = view.findViewById<View>(R.id.btnSearchWeb)

        val copyText: String
        val searchQuery = rawCode.trim()

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
            resumeScanning()
        }

        dialog.setOnDismissListener {
            resumeScanning()
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

        val inputImage: InputImage
        try {
            inputImage = InputImage.fromFilePath(this, uri)
        } catch (exc: Exception) {
            Toast.makeText(this, "${getString(R.string.image_processing_error)}: ${exc.localizedMessage}", Toast.LENGTH_LONG).show()
            resumeScanning()
            return
        }

        val galleryScanner = BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_ALL_FORMATS)
                .build()
        )

        galleryScanner.process(inputImage)
            .addOnSuccessListener { barcodes ->
                if (barcodes.isEmpty()) {
                    Toast.makeText(this, getString(R.string.no_barcodes_found_in_image), Toast.LENGTH_LONG).show()
                    resumeScanning()
                } else if (barcodes.size == 1) {
                    val rawValue = barcodes[0].rawValue ?: barcodes[0].displayValue ?: ""
                    if (rawValue.isNotEmpty()) {
                        binding.btnScanAgain.visibility = View.VISIBLE
                        binding.tvStatusHint.text = "Код из фото: $rawValue"
                        val parseResult = parser.parse(rawValue)
                        showResultBottomSheet(rawValue, parseResult)
                    } else {
                        Toast.makeText(this, getString(R.string.no_barcodes_found_in_image), Toast.LENGTH_SHORT).show()
                        resumeScanning()
                    }
                } else {
                    val validCodes = barcodes.mapNotNull { it.rawValue ?: it.displayValue }.distinct()
                    if (validCodes.isEmpty()) {
                        Toast.makeText(this, getString(R.string.no_barcodes_found_in_image), Toast.LENGTH_SHORT).show()
                        resumeScanning()
                        return@addOnSuccessListener
                    }
                    val items = validCodes.toTypedArray()
                    MaterialAlertDialogBuilder(this)
                        .setTitle("${getString(R.string.select_barcode_dialog_title)} (${items.size})")
                        .setItems(items) { _, which ->
                            val selectedCode = items[which]
                            binding.btnScanAgain.visibility = View.VISIBLE
                            binding.tvStatusHint.text = "Выбран код: $selectedCode"
                            val parseResult = parser.parse(selectedCode)
                            showResultBottomSheet(selectedCode, parseResult)
                        }
                        .setOnCancelListener {
                            resumeScanning()
                        }
                        .setNegativeButton("Отмена") { _, _ ->
                            resumeScanning()
                        }
                        .show()
                }
            }
            .addOnFailureListener { exc ->
                Toast.makeText(this, "${getString(R.string.image_processing_error)}: ${exc.localizedMessage}", Toast.LENGTH_LONG).show()
                resumeScanning()
            }
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraExecutor.shutdown()
    }
}
