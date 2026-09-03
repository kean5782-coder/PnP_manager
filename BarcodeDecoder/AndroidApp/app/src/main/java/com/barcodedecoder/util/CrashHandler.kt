package com.barcodedecoder.util

import android.content.Context

/**
 * Глобальный перехватчик необработанных исключений (UncaughtExceptionHandler).
 * Сохраняет подробный стек вызовов и системные логи перед передачей управления стандартному обработчику ОС.
 */
class CrashHandler private constructor(private val context: Context) : Thread.UncaughtExceptionHandler {

    private val defaultHandler: Thread.UncaughtExceptionHandler? = Thread.getDefaultUncaughtExceptionHandler()

    override fun uncaughtException(thread: Thread, throwable: Throwable) {
        AppLogger.saveCrashLog(context, throwable)
        defaultHandler?.uncaughtException(thread, throwable)
    }

    companion object {
        /**
         * Инициализирует глобальный обработчик сбоев в приложении.
         */
        fun init(context: Context) {
            val handler = CrashHandler(context.applicationContext)
            Thread.setDefaultUncaughtExceptionHandler(handler)
        }
    }
}
