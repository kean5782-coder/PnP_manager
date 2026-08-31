package com.barcodedecoder.util

import android.content.Context
import android.os.Build
import android.util.Log
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.LinkedList
import java.util.Locale

object AppLogger {
    private const val TAG = "BarcodeDecoder"
    private const val MAX_MEMORY_LOGS = 100
    private val memoryLogs = LinkedList<String>()
    private val dateFormat = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US)

    @Synchronized
    fun log(tag: String, message: String) {
        val timestamp = dateFormat.format(Date())
        val logEntry = "[$timestamp][$tag] $message"
        Log.d(tag, message)

        if (memoryLogs.size >= MAX_MEMORY_LOGS) {
            memoryLogs.removeFirst()
        }
        memoryLogs.addLast(logEntry)
    }

    @Synchronized
    fun getRecentLogs(): String {
        return memoryLogs.joinToString("\n")
    }

    fun getDeviceInfo(context: Context): String {
        val pInfo = try {
            context.packageManager.getPackageInfo(context.packageName, 0)
        } catch (_: Exception) {
            null
        }
        val versionName = pInfo?.versionName ?: "unknown"
        val versionCode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            pInfo?.longVersionCode ?: 0
        } else {
            @Suppress("DEPRECATION")
            pInfo?.versionCode?.toLong() ?: 0
        }

        return """
            Версия приложения: $versionName (Build $versionCode)
            Устройство: ${Build.MANUFACTURER} ${Build.MODEL} (${Build.DEVICE})
            Версия Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})
            Архитектура: ${Build.SUPPORTED_ABIS.joinToString(", ")}
            Дата и время: ${dateFormat.format(Date())}
        """.trimIndent()
    }

    fun saveCrashLog(context: Context, throwable: Throwable) {
        try {
            val file = File(context.filesDir, "crash_log.txt")
            val sw = StringWriter()
            val pw = PrintWriter(sw)
            throwable.printStackTrace(pw)
            val stackTrace = sw.toString()

            val crashContent = """
                === CRASH REPORT ===
                ${getDeviceInfo(context)}
                
                --- STACKTRACE ---
                $stackTrace
                
                --- RECENT LOGS ---
                ${getRecentLogs()}
            """.trimIndent()

            file.writeText(crashContent)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save crash log", e)
        }
    }

    fun getPendingCrashLog(context: Context): String? {
        val file = File(context.filesDir, "crash_log.txt")
        return if (file.exists() && file.length() > 0) {
            file.readText()
        } else null
    }

    fun clearCrashLog(context: Context) {
        val file = File(context.filesDir, "crash_log.txt")
        if (file.exists()) {
            file.delete()
        }
    }
}
