package com.barcodedecoder.util

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.widget.Toast

/**
 * Утилита для отправки обратной связи, баг-репортов и отчетов о нераспознанных кодах разработчику.
 */
object FeedbackHelper {

    const val DEVELOPER_EMAIL = "kean5782@yandex.ru"
    const val AUTHOR_NAME = "kean5782 (Анохин Александр Александрович)"

    private const val MAX_CODE_LENGTH = 150
    private const val MAX_NOTES_LENGTH = 1000
    private const val MAX_SUBJECT_LENGTH = 120

    /**
     * Очищает пользовательский ввод: удаляет нуль-байты, опасные управляющие символы ASCII,
     * HTML-теги и обрезает текст до максимальной длины.
     */
    fun sanitizeInput(input: String, maxLength: Int): String {
        if (input.isBlank()) return ""
        
        var clean = input
            .replace("\u0000", "") // Удаление NULL байтов
            .replace(Regex("[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]"), "") // Удаление непечатных управляющих кодов
            .replace(Regex("<[^>]*>"), "") // Удаление возможных HTML тегов
            .trim()

        if (clean.length > maxLength) {
            clean = clean.substring(0, maxLength) + " [обрезано]"
        }
        return clean
    }

    /**
     * Отправляет сформированный отчет через почтовый клиент (mailto).
     */
    fun sendEmail(
        context: Context,
        subject: String,
        body: String
    ) {
        val safeSubject = sanitizeInput(subject, MAX_SUBJECT_LENGTH)
        val safeBody = body.replace("\u0000", "")

        AppLogger.log("Feedback", "Sending email report: $safeSubject")
        val intent = Intent(Intent.ACTION_SENDTO).apply {
            data = Uri.parse("mailto:$DEVELOPER_EMAIL")
            putExtra(Intent.EXTRA_EMAIL, arrayOf(DEVELOPER_EMAIL))
            putExtra(Intent.EXTRA_SUBJECT, safeSubject)
            putExtra(Intent.EXTRA_TEXT, safeBody)
        }

        try {
            context.startActivity(Intent.createChooser(intent, "Выберите почтовое приложение"))
        } catch (e: Exception) {
            // Fallback: пробуем общий интент отправки
            val fallbackIntent = Intent(Intent.ACTION_SEND).apply {
                type = "message/rfc822"
                putExtra(Intent.EXTRA_EMAIL, arrayOf(DEVELOPER_EMAIL))
                putExtra(Intent.EXTRA_SUBJECT, safeSubject)
                putExtra(Intent.EXTRA_TEXT, safeBody)
            }
            try {
                context.startActivity(Intent.createChooser(fallbackIntent, "Отправить отчёт разработчику"))
            } catch (exc: Exception) {
                Toast.makeText(context, "Не найдено почтовое приложение. Скопируйте отчёт.", Toast.LENGTH_LONG).show()
                shareText(context, safeSubject, safeBody)
            }
        }
    }

    /**
     * Позволяет поделиться текстом отчета через стандартное системное меню «Поделиться».
     */
    fun shareText(context: Context, title: String, text: String) {
        val safeTitle = sanitizeInput(title, MAX_SUBJECT_LENGTH)
        val safeText = text.replace("\u0000", "")

        val shareIntent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_SUBJECT, safeTitle)
            putExtra(Intent.EXTRA_TEXT, safeText)
        }
        try {
            context.startActivity(Intent.createChooser(shareIntent, "Поделиться отчётом"))
        } catch (e: Exception) {
            Toast.makeText(context, "Не удалось открыть меню отправки: ${e.message}", Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * Формирует структурированный текст отчета о нераспознанном штрихкоде.
     */
    fun buildUnrecognizedCodeReport(
        context: Context,
        rawCode: String,
        userNotes: String
    ): String {
        val cleanCode = sanitizeInput(rawCode, MAX_CODE_LENGTH)
        val cleanNotes = sanitizeInput(userNotes, MAX_NOTES_LENGTH)

        return """
            === БАГ-РЕПОРТ: НЕРАСПОЗНАННЫЙ ШТРИХКОД ===
            
            [Штрихкод / Артикул]:
            $cleanCode
            
            [Комментарий / Номинал и производитель]:
            ${if (cleanNotes.isNotBlank()) cleanNotes else "(не указано)"}
            
            --- ДИАГНОСТИЧЕСКИЕ ДАННЫЕ ---
            ${AppLogger.getDeviceInfo(context)}
            
            --- ПОСЛЕДНИЕ СОБЫТИЯ ---
            ${AppLogger.getRecentLogs()}
        """.trimIndent()
    }

    /**
     * Формирует структурированный текст отчета об общей проблеме или отзыве.
     */
    fun buildGeneralFeedbackReport(
        context: Context,
        feedbackType: String,
        userMessage: String
    ): String {
        val cleanType = sanitizeInput(feedbackType, 50)
        val cleanMessage = sanitizeInput(userMessage, MAX_NOTES_LENGTH)

        return """
            === ОБРАТНАЯ СВЯЗЬ / БАГ-РЕПОРТ: $cleanType ===
            
            [Сообщение пользователя]:
            $cleanMessage
            
            --- ДИАГНОСТИЧЕСКИЕ ДАННЫЕ ---
            ${AppLogger.getDeviceInfo(context)}
            
            --- ПОСЛЕДНИЕ СОБЫТИЯ ---
            ${AppLogger.getRecentLogs()}
        """.trimIndent()
    }
}
