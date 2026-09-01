package com.barcodedecoder.engine

import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale
import java.util.regex.Pattern

/**
 * Максимальное число удаляемых символов слева (префиксы катушек 1P, Q, 1T и т.д.)
 * и справа (суффиксы упаковок, технологические коды).
 */
const val MAX_TRIM_LEFT = 15
const val MAX_TRIM_RIGHT = 80

/**
 * Форматирует вещественное число в компактную строку, отсекая лишние нули в конце
 * (аналог спецификатора %g в C/Python) без потери значащих цифр для миллиомных значений.
 */
fun formatG(num: Double): String {
    if (num == 0.0) return "0"
    val df = DecimalFormat("0.######", DecimalFormatSymbols(Locale.US))
    return df.format(num)
}

/**
 * Преобразует российское обозначение резисторов (Р1-12, Р1-16, например '10кОм', '4.7МОм', '100Ом', '10k', '4,7к')
 * в унифицированный формат со стандартными суффиксами R/K/M.
 */
fun parseRussianResistorValue(rawInput: String): String {
    var raw = rawInput.lowercase().trim()
    raw = raw.replace("ом", "")
    raw = raw.replace("r", "")
    
    // Поддержка как русских букв (к, м), так и латинских (k, m)
    val pattern = Pattern.compile("""^([\d.,]+)\s*([кkмm]?)""")
    val matcher = pattern.matcher(raw)
    if (!matcher.find()) return rawInput

    val numStr = matcher.group(1)?.replace(',', '.') ?: return rawInput
    val unit = matcher.group(2) ?: ""
    val num = numStr.toDoubleOrNull() ?: return rawInput

    return when (unit) {
        "к", "k" -> "${formatG(num)}K"
        "м", "m" -> "${formatG(num)}M"
        else -> {
            when {
                num >= 1000000 -> "${formatG(num / 1000000)}M"
                num >= 1000 -> "${formatG(num / 1000)}K"
                else -> "${formatG(num)}R"
            }
        }
    }
}

/**
 * Правило декодирования маркировки компонентов конкретного производителя.
 *
 * @param name Название производителя или серии (например, "Murata", "Vishay", "Samsung_Cap").
 * @param compType Тип радиокомпонента ("resistor" или "capacitor").
 * @param patternStr Регулярное выражение с именованными группами захвата.
 * @param sizeMap Таблица сопоставления внутренних кодов размеров стандарту EIA (0402, 0603, 0805...).
 * @param dielectricMap Таблица сопоставления диэлектриков (C0G, X7R, X5R...).
 * @param voltageMap Таблица сопоставления кодов рабочего напряжения (16V, 25V, 50V...).
 * @param toleranceMap Таблица сопоставления кодов точности/допуска (0.1%, 1%, 5%...).
 * @param valueParser Дополнительная функция парсинга значения (если требуется кастомная логика).
 * @param suffixMap Таблица сопоставления суффиксов единиц (R, K, M, L -> mΩ).
 * @param isResistor Флаг резистора (true) или конденсатора (false).
 */
class VendorRule(
    val name: String,
    val compType: String,
    patternStr: String,
    val sizeMap: Map<String, String>,
    val dielectricMap: Map<String, String> = emptyMap(),
    val voltageMap: Map<String, String> = emptyMap(),
    val toleranceMap: Map<String, String> = emptyMap(),
    val valueParser: ((String) -> String)? = null,
    val suffixMap: Map<String, String> = emptyMap(),
    val isResistor: Boolean = false
) {
    val pattern: Pattern = Pattern.compile(patternStr, Pattern.CASE_INSENSITIVE)

    /** Список именованных групп, фактически присутствующих в шаблоне данного правила. */
    private val presentGroupNames: List<String>

    init {
        // Извлекаем имена группы из regex один раз при создании правила,
        // вместо try/catch перебора 33 имён при каждом совпадении (STYLE-1)
        val groupNamePattern = Pattern.compile("""\(\?<([a-zA-Z_][a-zA-Z0-9_]*)>""")
        val groupMatcher = groupNamePattern.matcher(patternStr)
        val names = mutableListOf<String>()
        while (groupMatcher.find()) {
            groupMatcher.group(1)?.let { names.add(it) }
        }
        presentGroupNames = names
    }

    /**
     * Выполняет сопоставление строки кода с регулярным выражением правила.
     * Возвращает карту извлеченных именованных групп или null.
     */
    fun match(code: String): Map<String, String>? {
        val matcher = pattern.matcher(code)
        if (!matcher.matches()) return null

        val result = mutableMapOf<String, String>()
        for (groupName in presentGroupNames) {
            val value = matcher.group(groupName)
            if (value != null) {
                result[groupName] = value
            }
        }
        return result
    }
}

/**
 * Результат расшифровки кода компонента.
 *
 * @param rule Совпавшее правило производителя.
 * @param groups Извлеченные именованные параметры (номинал, диэлектрик, допуск и т.д.).
 * @param usedCode Очищенная подстрока кода, подошедшая под шаблон.
 * @param leftTrim Количество отсеченных мусорных символов слева.
 * @param rightTrim Количество отсеченных мусорных символов справа.
 * @param unifiedName Стандартизированное имя компонента (например, "R_0603_10K_1%").
 */
data class ParseResult(
    val rule: VendorRule,
    val groups: Map<String, String>,
    val usedCode: String,
    val leftTrim: Int,
    val rightTrim: Int,
    val unifiedName: String
)

/**
 * Движок разбора и сопоставления правил для всех поддерживаемых производителей.
 */
class VendorParser(val rules: List<VendorRule>) {

    /**
     * Выполняет распознавание кода со сканера или ручного ввода.
     * Автоматически выполняет поиск подстроки при наличии префиксов/суффиксов.
     */
    companion object {
        private const val MAX_TRIM_LEFT = 15
        private const val MAX_TRIM_RIGHT = 15

        // Регулярное выражение для очистки стандартных префиксов катушек (EIA/CEA-863, EDIFACT, etc.)
        private val BARCODE_PREFIX_REGEX = Pattern.compile(
            """^(?:ITEM\(1P\)|CUST\s*PROD\s*ID\(P\)|CUST\s*P/N|OUR\s*P/N|TDK\s*ITEM|P/N|ITEM|\(1P\)|\(30P\)|\(31P\)|\(1T\)|\(1S\)|\(6P\)|\(Q\)|\(V\)|\(P\)|1P|30P|31P|P|1T|1S|6P|9D|Q|V|K|D|10D|11D|12D)[:\s\-]*""",
            Pattern.CASE_INSENSITIVE
        )
    }

    /**
     * Выполняет распознавание кода со сканера или ручного ввода.
     * Автоматически выполняет поиск подстроки при наличии префиксов/суффиксов
     * и токенизацию составных 2D DataMatrix/QR кодов.
     */
    fun parse(code: String, vendorName: String? = null): ParseResult? {
        val original = code.trim()
        if (original.isEmpty()) return null

        // 1. Попытка разобрать строку целиком (как единичный токен)
        val singleMatch = parseSingleToken(original, vendorName)
        if (singleMatch != null) return singleMatch

        // 1.1 Попытка с удалением пробелов внутри (для этикеток, где часть артикула напечатана с пробелами, например "RC 0402 F R-07 33R2")
        if (original.contains(' ') && !original.startsWith("Р1-", ignoreCase = true)) {
            val noSpaces = original.replace(" ", "")
            val noSpaceMatch = parseSingleToken(noSpaces, vendorName)
            if (noSpaceMatch != null) return noSpaceMatch
        }

        // 2. Если не подошло или строка содержит составные разделители (ISO 15434, CSV, &, /, etc.):
        var cleaned = original
        if (cleaned.startsWith("[)>")) {
            val firstSep = cleaned.indexOfAny(charArrayOf('\u001d', '\u001e', '\n', ',', ';'))
            if (firstSep != -1 && firstSep < 10) {
                cleaned = cleaned.substring(firstSep + 1)
            }
        }

        // Разбиваем на токены по всем стандартным разделителям
        val tokens = cleaned.split(Regex("""[\u001d\u001e\u0004,;&|\n\r\t/]+"""))
            .map { it.trim() }
            .filter { it.isNotEmpty() }

        for (token in tokens) {
            val tokenMatch = parseSingleToken(token, vendorName)
            if (tokenMatch != null) return tokenMatch

            if (token.contains(' ') && !token.startsWith("Р1-", ignoreCase = true)) {
                val tokenNoSpaces = token.replace(" ", "")
                val tokenNoSpaceMatch = parseSingleToken(tokenNoSpaces, vendorName)
                if (tokenNoSpaceMatch != null) return tokenNoSpaceMatch
            }

            val matcher = BARCODE_PREFIX_REGEX.matcher(token)
            if (matcher.find()) {
                val stripped = token.substring(matcher.end()).trim()
                if (stripped.isNotEmpty()) {
                    val strippedMatch = parseSingleToken(stripped, vendorName)
                    if (strippedMatch != null) return strippedMatch

                    if (stripped.contains(' ') && !stripped.startsWith("Р1-", ignoreCase = true)) {
                        val strippedNoSpaces = stripped.replace(" ", "")
                        val strippedNoSpaceMatch = parseSingleToken(strippedNoSpaces, vendorName)
                        if (strippedNoSpaceMatch != null) return strippedNoSpaceMatch
                    }
                }
            }
        }

        return null
    }

    private fun parseSingleToken(token: String, vendorName: String? = null): ParseResult? {
        val t = token.trim()
        if (t.isEmpty()) return null

        fun tryMatch(candidate: String): Pair<VendorRule, Map<String, String>>? {
            val c = candidate.trim()
            if (c.isEmpty()) return null
            if (vendorName != null) {
                for (rule in rules) {
                    if (rule.name.equals(vendorName, ignoreCase = true)) {
                        val groups = rule.match(c)
                        if (groups != null) return rule to groups
                    }
                }
                return null
            } else {
                for (rule in rules) {
                    val groups = rule.match(c)
                    if (groups != null) return rule to groups
                }
                return null
            }
        }

        // 1. Прямое совпадение
        val directMatch = tryMatch(t)
        if (directMatch != null) {
            val (rule, groups) = directMatch
            val unified = convertToUnified(rule, groups)
            return ParseResult(rule, groups, t, 0, 0, unified)
        }

        // 2. Если перед кодом стоит стандартный префикс штрихкода (1P, P, etc.)
        val prefixMatcher = BARCODE_PREFIX_REGEX.matcher(t)
        if (prefixMatcher.find()) {
            val stripped = t.substring(prefixMatcher.end()).trim()
            if (stripped.isNotEmpty()) {
                val strippedMatch = tryMatch(stripped)
                if (strippedMatch != null) {
                    val (rule, groups) = strippedMatch
                    val unified = convertToUnified(rule, groups)
                    return ParseResult(rule, groups, stripped, prefixMatcher.end(), 0, unified)
                }
            }
        }

        // 3. Подбор по обрезке мусорных символов слева и справа
        data class Candidate(val left: Int, val right: Int, val total: Int)
        val candidates = mutableListOf<Candidate>()

        val maxLeft = minOf(MAX_TRIM_LEFT, t.length - 3)
        val maxRight = minOf(MAX_TRIM_RIGHT, t.length - 3)

        for (left in 0..maxLeft) {
            for (right in 0..maxRight) {
                if (left == 0 && right == 0) continue
                if (left + right >= t.length - 2) continue
                candidates.add(Candidate(left, right, left + right))
            }
        }

        candidates.sortWith(compareBy({ it.total }, { it.left }))

        for ((left, right, _) in candidates) {
            val candidate = t.substring(left, t.length - right)
            if (candidate.isEmpty()) continue
            val match = tryMatch(candidate)
            if (match != null) {
                val (rule, groups) = match
                val unified = convertToUnified(rule, groups)
                return ParseResult(rule, groups, candidate, left, right, unified)
            }
        }

        return null
    }

    /**
     * Преобразует извлеченные параметры в унифицированное наименование.
     */
    fun convertToUnified(rule: VendorRule, groups: Map<String, String>): String {
        return if (rule.isResistor) {
            val sizeCode = groups["size"] ?: groups["cga_size"] ?: groups["cgaSize"] ?: ""
            val size = rule.sizeMap[sizeCode] ?: sizeCode
            val rawValue = groups["value"] ?: groups["code"] ?: ""
            val valueStr = if (rawValue.isNotEmpty()) {
                rule.valueParser?.invoke(rawValue) ?: parseResistorValue(rawValue, rule.suffixMap)
            } else {
                val tol = groups["tolerance"] ?: ""
                if (tol == "Z" || tol == "0") "0R" else "?"
            }
            val toleranceCode = groups["tolerance"] ?: ""
            val tolerance = rule.toleranceMap[toleranceCode] ?: toleranceCode
            
            val isJumper = valueStr == "0R" || tolerance == "0%" || rawValue in listOf("0000", "000", "00", "0", "0R", "0R00", "0R0") || rawValue.all { it == '0' && rawValue.isNotEmpty() }
            if (isJumper) {
                if (tolerance.isNotEmpty() && tolerance != "0%") {
                    "R_${size}_0R_${tolerance}"
                } else {
                    "R_${size}_0R"
                }
            } else if (tolerance.isNotEmpty()) {
                "R_${size}_${valueStr}_${tolerance}"
            } else {
                "R_${size}_${valueStr}"
            }
        } else {
            val sizeCode = groups["size"] ?: groups["cga_size"] ?: groups["cgaSize"] ?: ""
            val size = rule.sizeMap[sizeCode] ?: sizeCode
            val dielectricCode = groups["dielectric"] ?: ""
            val dielectric = rule.dielectricMap[dielectricCode] ?: dielectricCode
            val rawValue = groups["code"] ?: ""
            val valueStr = if (rawValue.isNotEmpty()) {
                rule.valueParser?.invoke(rawValue) ?: parseCapacitanceValue(rawValue)
            } else {
                "?"
            }
            val voltageCode = groups["voltage"] ?: ""
            val voltage = rule.voltageMap[voltageCode] ?: "?"
            "C_${size}_${dielectric}_${valueStr}_${voltage}"
        }
    }

    /**
     * Парсинг номиналов резисторов (3/4-значная кодировка EIA, буквенная нотация, джамперы).
     */
    private fun parseResistorValue(rawInput: String, suffixMap: Map<String, String>): String {
        var raw = rawInput.trim().uppercase()
        raw = raw.replace("Ω", "")
        raw = raw.replace("(?i)ом".toRegex(), "")

        if (raw == "0000" || raw == "000" || raw == "00" || raw == "0" || raw == "0R" || raw == "0R00" || raw == "0R0") return "0R"

        // Буквенная нотация внутри (например, 10K0, 4K70, 100R, 1R00, 1M00, 2M2)
        val matchInside = Pattern.compile("""^(\d+)([RKM])(\d*)$""").matcher(raw)
        if (matchInside.matches()) {
            val numPart = matchInside.group(1) ?: ""
            val letter = matchInside.group(2) ?: ""
            val decimalPart = matchInside.group(3) ?: ""
            val valStr = if (decimalPart.isNotEmpty()) "$numPart.$decimalPart" else numPart
            val valNum = valStr.toDoubleOrNull() ?: 0.0
            return when (letter) {
                "R" -> "${formatG(valNum)}R"
                "K" -> "${formatG(valNum)}K"
                "M" -> "${formatG(valNum)}M"
                else -> "${formatG(valNum)}R"
            }
        }

        // Суффиксы единиц на конце (R, K, M, L -> mΩ)
        if (raw.isNotEmpty() && suffixMap.containsKey(raw.takeLast(1))) {
            val suffix = raw.takeLast(1)
            var numPart = raw.dropLast(1)
            val unit = suffixMap[suffix] ?: ""
            if (numPart.contains('R')) {
                numPart = numPart.replace("R", ".")
            }
            var valNum = numPart.toDoubleOrNull() ?: 0.0
            return when (unit) {
                "Ω", "mΩ" -> {
                    if (unit == "mΩ") valNum /= 1000.0
                    when {
                        valNum >= 1000000 -> "${formatG(valNum / 1000000)}M"
                        valNum >= 1000 -> "${formatG(valNum / 1000)}K"
                        else -> "${formatG(valNum)}R"
                    }
                }
                "KΩ" -> "${formatG(valNum)}K"
                "MΩ" -> "${formatG(valNum)}M"
                else -> "$numPart$unit"
            }
        }

        // 3-значные и 4-значные цифровые коды
        return when (raw.length) {
            3 -> {
                if (raw.contains('R')) {
                    val valNum = raw.replace("R", ".").toDoubleOrNull() ?: 0.0
                    "${formatG(valNum)}R"
                } else {
                    val mantissa = raw.substring(0, 2).toIntOrNull() ?: return raw
                    val multiplier = raw.substring(2, 3).toIntOrNull() ?: return raw
                    val valNum = mantissa * Math.pow(10.0, multiplier.toDouble())
                    when {
                        valNum >= 1000000 -> "${formatG(valNum / 1000000)}M"
                        valNum >= 1000 -> "${formatG(valNum / 1000)}K"
                        else -> "${formatG(valNum)}R"
                    }
                }
            }
            4 -> {
                if (raw.contains('R')) {
                    val valNum = raw.replace("R", ".").toDoubleOrNull() ?: 0.0
                    "${formatG(valNum)}R"
                } else {
                    val mantissa = raw.substring(0, 3).toIntOrNull() ?: return raw
                    val multiplier = raw.substring(3, 4).toIntOrNull() ?: return raw
                    val valNum = mantissa * Math.pow(10.0, multiplier.toDouble())
                    when {
                        valNum >= 1000000 -> "${formatG(valNum / 1000000)}M"
                        valNum >= 1000 -> "${formatG(valNum / 1000)}K"
                        else -> "${formatG(valNum)}R"
                    }
                }
            }
            else -> raw
        }
    }

    /**
     * Парсинг значений емкости конденсаторов (pF, nF, uF).
     */
    private fun parseCapacitanceValue(rawInput: String): String {
        var raw = rawInput.trim().uppercase()
        if (raw.contains('R')) {
            val valNum = raw.replace("R", ".").toDoubleOrNull() ?: 0.0
            return when {
                valNum < 1 -> "${formatG(valNum)}pF"
                valNum < 1000 -> if (valNum % 1.0 == 0.0) "${valNum.toInt()}pF" else "${formatG(valNum)}pF"
                valNum < 1000000 -> {
                    val valNf = valNum / 1000.0
                    if (valNf % 1.0 == 0.0) "${valNf.toInt()}nF" else "${formatG(valNf)}nF"
                }
                else -> {
                    val valUf = valNum / 1000000.0
                    if (valUf % 1.0 == 0.0) "${valUf.toInt()}uF" else "${formatG(valUf)}uF"
                }
            }
        } else {
            if (raw.length == 3) {
                val mantissa = raw.substring(0, 2).toIntOrNull() ?: return raw
                val multiplier = raw.substring(2, 3).toIntOrNull() ?: return raw
                val valNum = mantissa * Math.pow(10.0, multiplier.toDouble())
                return when {
                    valNum < 1000 -> if (valNum % 1.0 == 0.0) "${valNum.toInt()}pF" else "${formatG(valNum)}pF"
                    valNum < 1000000 -> {
                        val valNf = valNum / 1000.0
                        if (valNf % 1.0 == 0.0) "${valNf.toInt()}nF" else "${formatG(valNf)}nF"
                    }
                    else -> {
                        val valUf = valNum / 1000000.0
                        if (valUf % 1.0 == 0.0) "${valUf.toInt()}uF" else "${formatG(valUf)}uF"
                    }
                }
            }
            return raw
        }
    }
}

/**
 * Фабрика правил для конденсаторов и резисторов всех поддерживаемых производителей.
 */
object RuleFactory {

    fun createAllRules(): List<VendorRule> {
        return createCapacitorRules() + createResistorRules()
    }

    /**
     * Создает правила для конденсаторов (CCTC, Kemet, Taiyo Yuden, Murata, Samsung, TDK, AVX, Walsin, Yageo).
     */
    fun createCapacitorRules(): List<VendorRule> {
        val rules = mutableListOf<VendorRule>()

        // 1. CCTC (серия TCC)
        rules.add(
            VendorRule(
                name = "CCTC",
                compType = "capacitor",
                patternStr = """^TCC\s*(?<size>\d{4})\s*(?<dielectric>[A-Z0-9]+)\s*(?<code>\d{3})\s*(?<tolerance>[JKMZ])\s*(?<voltage>\d{3})""",
                sizeMap = mapOf("0201" to "0201", "0402" to "0402", "0603" to "0603", "0805" to "0805", "1206" to "1206", "1210" to "1210"),
                dielectricMap = mapOf("COG" to "C0G", "X7R" to "X7R", "X5R" to "X5R", "X6S" to "X6S", "X7T" to "X7T", "Y5V" to "Y5V"),
                voltageMap = mapOf("500" to "50V", "250" to "25V", "160" to "16V", "100" to "10V", "6R3" to "6.3V", "630" to "63V"),
                toleranceMap = mapOf("J" to "5%", "K" to "10%", "M" to "20%", "Z" to "-20/+80%"),
                isResistor = false
            )
        )

        // 2. KEMET
        rules.add(
            VendorRule(
                name = "KEMET",
                compType = "capacitor",
                patternStr = """^C(?<size>\d{4})(?<type>[A-Z])(?<code>\d{3})(?<tolerance>[BCDFGJKMOPZ])(?<voltage>\d)(?<dielectric>[GRPUV])(?<suffix>[A-Z]{0,4})$""",
                sizeMap = mapOf("0402" to "0402", "0603" to "0603", "0805" to "0805", "1206" to "1206", "1210" to "1210", "1812" to "1812", "1825" to "1825", "2220" to "2220", "2225" to "2225"),
                dielectricMap = mapOf("G" to "C0G", "R" to "X7R", "P" to "X5R", "U" to "Z5U", "V" to "Y5V"),
                voltageMap = mapOf("1" to "100V", "2" to "200V", "3" to "25V", "4" to "16V", "5" to "50V", "6" to "35V", "7" to "4V", "8" to "10V", "9" to "6.3V"),
                toleranceMap = mapOf("B" to "0.10pF", "C" to "0.25pF", "D" to "0.5pF", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "M" to "20%", "Z" to "+80%/-20%"),
                isResistor = false
            )
        )

        // 3. Taiyo Yuden (поддержка всех кодов толщины [A-Z])
        rules.add(
            VendorRule(
                name = "TaiyoYuden",
                compType = "capacitor",
                patternStr = """^(?<voltage>[PALJETGUHQSX])(?<series>[MVW])(?<termination>[KS])(?<size>\d{3})(?<sizeTolerance>[A-E]?)(?<dielectric>BJ|B7|C6|C7|LD|CG|UJ|UK)(?<code>\d+R\d+|\d{3})(?<tolerance>[ABCDFGJKMZ])(?<thickness>[A-Z])(?<special>[A-Z]?)-?(?<packaging>[FTPRW]?)(?<internal>[A-Z]?)$""",
                sizeMap = mapOf("021" to "008004", "042" to "01005", "063" to "0201", "105" to "0402", "107" to "0603", "212" to "0805", "316" to "1206", "325" to "1210", "432" to "1812"),
                dielectricMap = mapOf("BJ" to "X5R", "B7" to "X7R", "C6" to "X6S", "C7" to "X7S", "LD" to "X5R", "CG" to "C0G", "UJ" to "U2J", "UK" to "U2K"),
                voltageMap = mapOf("P" to "2.5V", "A" to "4V", "J" to "6.3V", "L" to "10V", "E" to "16V", "T" to "25V", "G" to "35V", "U" to "50V", "H" to "100V", "Q" to "250V", "S" to "630V", "X" to "2000V"),
                isResistor = false
            )
        )

        // 4. Murata
        val murataSeries = "GRM|GJM|GQM|LLL|LLA|LLM|ERB|GCD|GCM|GCJ|GCH|GCE|GCQ|GMA|GNM|GR4|GR7|GA2|GA3|GC|GD|GF|GB"
        val murataDielectrics = "X7R|X5R|X6S|X7S|X8R|Y5V|C0G|U2J|5C|R7|R6|C7|R9|C8|R8|X6T|X5S|X7T|X8L|X8G|X8P|NP0|NPO"
        val murataPattern = """^(?<series>$murataSeries)(?<size>\d{2,3}[A-Z]?)(?<dielectric>$murataDielectrics)(?<voltage>[A-Z0-9]{2})(?<code>\d{3})(?<tolerance>[A-Z])(?<rest>[A-Z0-9]*)$"""

        val murataSizeMap = mutableMapOf(
            "02" to "01005", "03" to "0201", "15" to "0402", "18" to "0603",
            "21" to "0805", "31" to "1206", "32" to "1210", "43" to "1812",
            "55" to "2220", "022" to "01005", "033" to "0201", "155" to "0402",
            "188" to "0603", "216" to "0805", "219" to "0805", "316" to "1206",
            "319" to "1206", "329" to "1210", "433" to "1812", "555" to "2220", "158" to "0402"
        )
        for ((code, size) in listOf("15" to "0402", "18" to "0603", "21" to "0805", "31" to "1206", "32" to "1210", "43" to "1812", "55" to "2220")) {
            for (c in 'A'..'Z') {
                murataSizeMap["$code$c"] = size
            }
        }

        rules.add(
            VendorRule(
                name = "Murata",
                compType = "capacitor",
                patternStr = murataPattern,
                sizeMap = murataSizeMap,
                dielectricMap = mapOf(
                    "5C" to "C0G", "R7" to "X7R", "R6" to "X5R", "C7" to "X7S",
                    "U2J" to "U2J", "X7R" to "X7R", "X5R" to "X5R", "X6S" to "X6S",
                    "X7S" to "X7S", "X8R" to "X8R", "Y5V" to "Y5V", "C0G" to "C0G",
                    "R9" to "X7R", "C8" to "X6S", "R8" to "X8R", "X6T" to "X6T",
                    "X5S" to "X5S", "X7T" to "X7T", "X8L" to "X8L", "X8G" to "X8G",
                    "X8P" to "X8P", "NP0" to "C0G", "NPO" to "C0G"
                ),
                voltageMap = mapOf(
                    "0G" to "4V", "0J" to "6.3V", "1A" to "10V", "1C" to "16V",
                    "1E" to "25V", "1H" to "50V", "2A" to "100V", "2D" to "200V",
                    "2E" to "250V", "2H" to "500V", "2J" to "630V", "3A" to "1kV",
                    "3D" to "2kV", "3F" to "3.15kV", "BB" to "350V", "E2" to "AC250V"
                ),
                toleranceMap = mapOf(
                    "B" to "0.10pF", "C" to "0.25pF", "D" to "0.5pF", "F" to "1%",
                    "G" to "2%", "J" to "5%", "K" to "10%", "M" to "20%", "Z" to "+80%/-20%"
                ),
                isResistor = false
            )
        )

        // 5. Samsung Capacitor
        rules.add(
            VendorRule(
                name = "Samsung_Cap",
                compType = "capacitor",
                patternStr = """^CL(?<size>\d{2})(?<dielectric>[ACBXYZF])(?<code>\d{3}|[0-9]R[0-9])(?<tolerance>[BCDFGJKMZ])(?<voltage>[A-Z])(?<rest>.*)$""",
                sizeMap = mapOf("02" to "01005", "03" to "0201", "05" to "0402", "10" to "0603", "21" to "0805", "31" to "1206", "32" to "1210", "42" to "1808", "43" to "1812", "55" to "2220"),
                dielectricMap = mapOf("C" to "C0G", "A" to "X5R", "B" to "X7R", "X" to "X6S", "F" to "Y5V", "Y" to "X7S", "Z" to "X7T"),
                voltageMap = mapOf(
                    "R" to "4V", "Q" to "6.3V", "P" to "10V", "O" to "16V", "A" to "25V", "L" to "35V", "B" to "50V", "C" to "100V",
                    "D" to "200V", "E" to "250V", "F" to "350V", "G" to "500V", "H" to "630V", "I" to "1000V", "J" to "2000V", "K" to "3000V"
                ),
                toleranceMap = mapOf(
                    "B" to "0.10pF", "C" to "0.25pF", "D" to "0.50pF", "F" to "1%", "G" to "2%",
                    "J" to "5%", "K" to "10%", "M" to "20%", "Z" to "-20/+80%"
                ),
                isResistor = false
            )
        )

        // 6. TDK Capacitor (включая автомобильную серию CGA)
        rules.add(
            VendorRule(
                name = "TDK_Cap",
                compType = "capacitor",
                patternStr = """^(?:C(?<size>\d{4})|CGA(?<cgaSize>[2-8])[A-Z0-9]{1,2})(?<dielectric>COG|C0G|X5R|X6S|X7R|X7S|X7T)(?<voltage>0G|0J|1A|1C|1E|1V|1H|1N|2A|2E)(?<code>\d{3})(?<tolerance>[BCDFGJKM])(?<rest>.*)$""",
                sizeMap = mapOf(
                    "0402" to "01005", "0603" to "0201", "1005" to "0402", "1608" to "0603",
                    "2012" to "0805", "3216" to "1206", "3225" to "1210", "4532" to "1812", "5750" to "2220",
                    "2" to "0402", "3" to "0603", "4" to "0805", "5" to "1206", "6" to "1210", "8" to "1812"
                ),
                dielectricMap = mapOf("COG" to "C0G", "C0G" to "C0G", "X5R" to "X5R", "X6S" to "X6S", "X7R" to "X7R", "X7S" to "X7S", "X7T" to "X7T"),
                voltageMap = mapOf("0G" to "4V", "0J" to "6.3V", "1A" to "10V", "1C" to "16V", "1E" to "25V", "1V" to "35V", "1H" to "50V", "1N" to "75V", "2A" to "100V", "2E" to "250V"),
                toleranceMap = mapOf("B" to "0.10pF", "C" to "0.25pF", "D" to "0.50pF", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "M" to "20%"),
                isResistor = false
            )
        )

        // 7. AVX / Kyocera AVX MLCC
        rules.add(
            VendorRule(
                name = "AVX",
                compType = "capacitor",
                patternStr = """^(?<size>0201|0402|0603|0805|1206|1210|1812|2220)(?<voltage>[ZY3512V7])(?<dielectric>[ACDFG])(?<code>\d{3}|[0-9]R[0-9])(?<tolerance>[BCDFGJKMZ])(?<pack>[A-Z0-9]{3,4})$""",
                sizeMap = mapOf(
                    "0201" to "0201", "0402" to "0402", "0603" to "0603", "0805" to "0805",
                    "1206" to "1206", "1210" to "1210", "1812" to "1812", "2220" to "2220"
                ),
                dielectricMap = mapOf("A" to "C0G", "C" to "X7R", "D" to "X5R", "F" to "X8R", "G" to "Y5V"),
                voltageMap = mapOf(
                    "Z" to "10V", "Y" to "16V", "3" to "25V", "5" to "50V",
                    "1" to "100V", "2" to "200V", "V" to "250V", "7" to "500V"
                ),
                toleranceMap = mapOf(
                    "B" to "0.10pF", "C" to "0.25pF", "D" to "0.50pF", "F" to "1%", "G" to "2%",
                    "J" to "5%", "K" to "10%", "M" to "20%", "Z" to "-20/+80%"
                ),
                isResistor = false
            )
        )

        // 8. Walsin Capacitor
        rules.add(
            VendorRule(
                name = "Walsin_Cap",
                compType = "capacitor",
                patternStr = """^(?<size>0201|0402|0603|0805|1206|1210|1812)(?<dielectric>[NBXSA])(?<code>\d{3})(?<tolerance>[ABCDFGJKMZ])(?<voltage>\d{3})(?<rest>.*)$""",
                sizeMap = mapOf("0201" to "0201", "0402" to "0402", "0603" to "0603", "0805" to "0805", "1206" to "1206", "1210" to "1210", "1812" to "1812"),
                dielectricMap = mapOf("N" to "C0G", "B" to "X7R", "X" to "X5R", "S" to "X6S", "A" to "X7S"),
                voltageMap = mapOf("040" to "4V", "063" to "6.3V", "100" to "10V", "160" to "16V", "250" to "25V", "500" to "50V"),
                toleranceMap = mapOf("A" to "0.05pF", "B" to "0.10pF", "C" to "0.25pF", "D" to "0.50pF", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "M" to "20%", "Z" to "-20/+80%"),
                isResistor = false
            )
        )

        // 9. Yageo Capacitor
        rules.add(
            VendorRule(
                name = "Yageo_Cap",
                compType = "capacitor",
                patternStr = """^(?<prefix>CC|AC|C|CQ)(?<size>\d{4})(?<tolerance>[BCDFGJKM])(?<packing>[A-Z]{0,2})(?<dielectric>X5R|X7R|X6S|X7S|X8R|X8G|COG|C0G|NP0|NPO|Y5V)(?<voltage>[A-Z0-9]?)(?<rest>[A-Z]{0,2})(?<code>\d{3}|[0-9]R[0-9]{1,2})$""",
                sizeMap = mapOf("0201" to "0201", "0402" to "0402", "0603" to "0603", "0805" to "0805", "1206" to "1206", "1210" to "1210", "1812" to "1812", "2010" to "2010", "2512" to "2512"),
                dielectricMap = mapOf("X5R" to "X5R", "X7R" to "X7R", "X6S" to "X6S", "X7S" to "X7S", "X8R" to "X8R", "X8G" to "X8G", "COG" to "C0G", "C0G" to "C0G", "NP0" to "C0G", "NPO" to "C0G", "Y5V" to "Y5V"),
                voltageMap = mapOf("0" to "100V", "4" to "4V", "5" to "6.3V", "6" to "10V", "7" to "16V", "8" to "25V", "9" to "50V", "C" to "100V", "D" to "200V", "E" to "250V", "F" to "350V", "G" to "500V", "H" to "630V", "I" to "1000V", "J" to "2000V", "K" to "3000V"),
                toleranceMap = mapOf("B" to "0.10pF", "C" to "0.25pF", "D" to "0.50pF", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "M" to "20%"),
                isResistor = false
            )
        )

        return rules
    }

    /**
     * Создает правила для резисторов (Vishay, Panasonic, Bourns, KOA, Royal Ohm, ROHM, Viking, Yageo, HOTTECH, Samsung, Walsin, Р1-12, Р1-16).
     */
    fun createResistorRules(): List<VendorRule> {
        val rules = mutableListOf<VendorRule>()

        // 1. Vishay / Dale (серия CRCW)
        rules.add(
            VendorRule(
                name = "Vishay",
                compType = "resistor",
                patternStr = """^CRCW(?<size>0402|0603|0805|1206|1210|1218|2010|2512)(?<code>\d{3,4}|\d+[RKM]\d*|0000)(?<tolerance>[BDFJZN])(?<tcr>[A-Z0-9]{1,2})(?<pack>[A-Z]{2})$""",
                sizeMap = mapOf(
                    "0402" to "0402", "0603" to "0603", "0805" to "0805", "1206" to "1206",
                    "1210" to "1210", "1218" to "1218", "2010" to "2010", "2512" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "J" to "5%", "Z" to "0%", "N" to "0%"),
                isResistor = true
            )
        )

        // 2. Panasonic (серия ERJ)
        rules.add(
            VendorRule(
                name = "Panasonic",
                compType = "resistor",
                patternStr = """^ERJ-?(?<size>1G|2G|2R|3G|3E|3R|6G|6E|6R|8G|8E|8R|14|12|1T)(?<series>[A-Z]{0,2}?)(?:(?<tolerance>[BDFGJKZ])|(?=[0-9R]))(?<code>\d{3,4}|\d*R\d+|0R00)(?<pack>[A-Z])$""",
                sizeMap = mapOf(
                    "1G" to "0201", "2G" to "0402", "2R" to "0402", "3G" to "0603", "3E" to "0603", "3R" to "0603",
                    "6G" to "0805", "6E" to "0805", "6R" to "0805", "8G" to "1206", "8E" to "1206", "8R" to "1206",
                    "14" to "1210", "12" to "1812", "1T" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "Z" to "0%", "0" to "0%", "" to "0%"),
                isResistor = true
            )
        )

        // 3. Bourns (серии CR, CRA, CRB, CHP, CMP)
        rules.add(
            VendorRule(
                name = "Bourns",
                compType = "resistor",
                patternStr = """^(?<series>CR|CRA|CRB|CHP|CMP)(?<size>01005|0201|0402|0603|0805|1206|1210|2010|2512)-?(?<tolerance>[BDFGJ])(?<tcr>[A-Z/]{1,3})-?(?<code>\d{3,4}|\d*R\d+|000)(?<pack>[A-Z0-9]*)$""",
                sizeMap = mapOf(
                    "01005" to "01005", "0201" to "0201", "0402" to "0402", "0603" to "0603",
                    "0805" to "0805", "1206" to "1206", "1210" to "1210", "2010" to "2010", "2512" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "G" to "2%", "J" to "5%"),
                isResistor = true
            )
        )

        // 4. KOA Speer (серия RK73)
        rules.add(
            VendorRule(
                name = "KOA_Speer",
                compType = "resistor",
                patternStr = """^RK73(?<type>[A-Z])(?<size>1F|1H|1E|1J|2A|2B|2E|W2H|W3A)(?<pack>[A-Z]{2,4})(?<code>\d{3,4}|\d*R\d+|000|0)?(?<tolerance>[BDFGJKZ])?$""",
                sizeMap = mapOf(
                    "1F" to "01005", "1H" to "0201", "1E" to "0402", "1J" to "0603",
                    "2A" to "0805", "2B" to "1206", "2E" to "1210", "W2H" to "2010", "W3A" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "Z" to "0%", "" to "0%"),
                isResistor = true
            )
        )

        // 5. Royal Ohm (серии WA, W8, WG, W4)
        rules.add(
            VendorRule(
                name = "Royal_Ohm",
                compType = "resistor",
                patternStr = """^(?<size>0201|0402|0603|0805|1206|1210|2010|2512)(?<power>[A-Z0-9]{2})(?<tolerance>[BDFGJ])(?<code>\d{3,4}|\d*R\d+|000)(?<pack>[A-Z0-9]{3})$""",
                sizeMap = mapOf(
                    "0201" to "0201", "0402" to "0402", "0603" to "0603", "0805" to "0805",
                    "1206" to "1206", "1210" to "1210", "2010" to "2010", "2512" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "G" to "2%", "J" to "5%"),
                isResistor = true
            )
        )

        // 6. ROHM MCR
        rules.add(
            VendorRule(
                name = "ROHM_MCR",
                compType = "resistor",
                patternStr = """^MCR(?<size>006|01|03|10|18|25|50|100)(?<pack>[A-Z]{3,4})(?<tolerance>[BDFGJ])(?<tcr>[A-Z0-9]?)(?<code>\d{3,4}|\d*R\d+|000)$""",
                sizeMap = mapOf(
                    "006" to "0201", "01" to "0402", "03" to "0603", "10" to "0805",
                    "18" to "1206", "25" to "1210", "50" to "2010", "100" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "G" to "2%", "J" to "5%"),
                isResistor = true
            )
        )

        // 7. Viking (серия CR с гибким разделителем упаковочного кода)
        rules.add(
            VendorRule(
                name = "Viking",
                compType = "resistor",
                patternStr = """^CR-(?<size>E5|01|02|03|05|06|10|0A|12|25|62)(?<tolerance>[BDFJ])(?<pack>[A-Z0-9]*?)-+(?<value>[^\s]+)$""",
                sizeMap = mapOf("E5" to "01005", "01" to "0201", "02" to "0402", "03" to "0603", "05" to "0805", "06" to "1206", "10" to "1210", "0A" to "2010", "12" to "2512", "25" to "1225", "62" to "0612"),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "J" to "5%"),
                suffixMap = mapOf("R" to "Ω", "K" to "KΩ", "M" to "MΩ", "L" to "mΩ"),
                isResistor = true
            )
        )

        // Парсер для RC Yageo и RI HOTTECH
        val parseRcOrRiValue: (String) -> String = { rawInput ->
            val raw = rawInput.uppercase()
            if (raw == "0000" || raw == "000" || raw == "00" || raw == "0" || raw == "0R" || raw == "0R0" || raw == "0R00" || (raw.isNotEmpty() && raw.all { it == '0' })) {
                "0R"
            } else if (raw.contains('R')) {
                val valNum = raw.replace("R", ".").toDoubleOrNull() ?: 0.0
                when {
                    valNum >= 1000000 -> "${formatG(valNum / 1000000)}M"
                    valNum >= 1000 -> "${formatG(valNum / 1000)}K"
                    else -> "${formatG(valNum)}R"
                }
            } else {
                val valNum = when (raw.length) {
                    3 -> {
                        val mantissa = raw.substring(0, 2).toIntOrNull() ?: 0
                        val mult = raw.substring(2, 3).toIntOrNull() ?: 0
                        mantissa * Math.pow(10.0, mult.toDouble())
                    }
                    4 -> {
                        val mantissa = raw.substring(0, 3).toIntOrNull() ?: 0
                        val mult = raw.substring(3, 4).toIntOrNull() ?: 0
                        mantissa * Math.pow(10.0, mult.toDouble())
                    }
                    5 -> {
                        val mantissa = raw.substring(0, 4).toIntOrNull() ?: 0
                        val mult = raw.substring(4, 5).toIntOrNull() ?: 0
                        mantissa * Math.pow(10.0, mult.toDouble())
                    }
                    else -> 0.0
                }
                if (valNum > 0) {
                    when {
                        valNum >= 1000000 -> "${formatG(valNum / 1000000)}M"
                        valNum >= 1000 -> "${formatG(valNum / 1000)}K"
                        else -> "${formatG(valNum)}R"
                    }
                } else rawInput
            }
        }

        // 8. RC Yageo
        rules.add(
            VendorRule(
                name = "RC_Yageo",
                compType = "resistor",
                patternStr = """^RC(?<size>\d{4})(?<tolerance>[BDFJ])(?<code>[\dR]{3,5})(?<pack>[A-Z]{0,2})$""",
                sizeMap = mapOf(
                    "0075" to "01005", "0100" to "0201", "0201" to "0201", "0402" to "0402",
                    "0603" to "0603", "0805" to "0805", "1206" to "1206", "1210" to "1210",
                    "1218" to "1218", "2010" to "2010", "2512" to "2512", "1005" to "0402",
                    "1608" to "0603", "2012" to "0805", "3216" to "1206", "3225" to "1210",
                    "5025" to "2010", "6432" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "J" to "5%"),
                valueParser = parseRcOrRiValue,
                isResistor = true
            )
        )

        // 9. RI HOTTECH
        rules.add(
            VendorRule(
                name = "RI_HOTTECH",
                compType = "resistor",
                patternStr = """^RI(?<size>\d{4})L(?<code>[\dR]{3,5})(?<tolerance>[BDFJ])T$""",
                sizeMap = mapOf(
                    "0075" to "01005", "0100" to "0201", "0201" to "0201", "0402" to "0402",
                    "0603" to "0603", "0805" to "0805", "1206" to "1206", "1210" to "1210",
                    "1218" to "1218", "2010" to "2010", "2512" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "J" to "5%"),
                valueParser = parseRcOrRiValue,
                isResistor = true
            )
        )

        // 10. ROHM ESR
        rules.add(
            VendorRule(
                name = "ROHM_ESR",
                compType = "resistor",
                patternStr = """^ESR(?<size>01|03|10|18|25)(?<pack>[A-Z]{3})(?<tolerance>[DFJ])(?<code>\d{3}|\d{4}|[0-9]R[0-9]{2})$""",
                sizeMap = mapOf("01" to "0402", "03" to "0603", "10" to "0805", "18" to "1206", "25" to "1210"),
                toleranceMap = mapOf("D" to "0.5%", "F" to "1%", "J" to "5%"),
                suffixMap = mapOf("R" to "Ω", "K" to "KΩ", "M" to "MΩ", "L" to "mΩ"),
                isResistor = true
            )
        )

        // 11. ROHM PMR (миллиомные резисторы с L в коде)
        val parsePmrValue: (String) -> String = { rawInput ->
            val raw = rawInput.uppercase()
            if (raw.contains('L')) {
                val valMohm = raw.replace("L", ".").toDoubleOrNull() ?: 0.0
                val valOhm = valMohm / 1000.0
                "${formatG(valOhm)}R"
            } else {
                rawInput
            }
        }
        rules.add(
            VendorRule(
                name = "ROHM_PMR",
                compType = "resistor",
                patternStr = """^PMR(?<size>01|03|10|18|25|50|100)(?<pack>[A-Z]{3})(?<tolerance>[FGJ])(?<special>[UV]?)(?<code>\d{1,2}L\d{0,2}|[0-9]{3})$""",
                sizeMap = mapOf("01" to "0402", "03" to "0603", "10" to "0805", "18" to "1206", "25" to "1210", "50" to "2010", "100" to "2512"),
                toleranceMap = mapOf("F" to "1%", "G" to "2%", "J" to "5%"),
                suffixMap = mapOf("L" to "mΩ"),
                valueParser = parsePmrValue,
                isResistor = true
            )
        )

        // 12. Samsung (резисторы)
        rules.add(
            VendorRule(
                name = "Samsung_Res",
                compType = "resistor",
                patternStr = """^(?<prefix>RC|RCB|RF|RM|RN|RK|RP|RUT|RU|RUK|RJ|RCW|RCV|RCS|RFS|RPS|RH)(?<size>\d{4})(?<tolerance>[DFGJ])(?<code>\d{3}|\d{4}|[0-9]R[0-9]{1,2})(?<pack>[A-Z]{0,2})$""",
                sizeMap = mapOf(
                    "0402" to "0402", "0603" to "0603", "1005" to "0402", "1608" to "0603", "2012" to "0805",
                    "3216" to "1206", "3225" to "1210", "5025" to "2010", "6432" to "2512"
                ),
                toleranceMap = mapOf("D" to "0.5%", "F" to "1%", "G" to "2%", "J" to "5%"),
                suffixMap = mapOf("R" to "Ω", "K" to "KΩ", "M" to "MΩ"),
                isResistor = true
            )
        )

        // 13. Walsin (резисторы)
        rules.add(
            VendorRule(
                name = "Walsin_Res",
                compType = "resistor",
                patternStr = """^(?<prefix>WR|WW|WA|WT|WF|WK)(?<size>\d{2})(?<func>[A-Z]?)(?<code>\d{3,4}|\d*R\d+)(?<tolerance>[FJP]?)(?<pack>[A-Z])(?<term>[LGS])?$""",
                sizeMap = mapOf(
                    "01" to "01005", "02" to "0201", "04" to "0402", "06" to "0603", "08" to "0805",
                    "10" to "1210", "12" to "1206", "18" to "1218", "20" to "2010", "25" to "2512"
                ),
                toleranceMap = mapOf("F" to "1%", "J" to "5%", "" to "0%"),
                suffixMap = mapOf("R" to "Ω", "K" to "KΩ", "M" to "MΩ", "L" to "mΩ"),
                isResistor = true
            )
        )

        // 14. Yageo (все серии резисторов)
        val yageoSeries = "AC|RC|RT|RL|RV|RE|RA|RK|RS|RP|RQ|RN|RM|RJ"
        rules.add(
            VendorRule(
                name = "Yageo",
                compType = "resistor",
                patternStr = """^(?<series>$yageoSeries)(?<size>\d{4})(?<tolerance>[A-Z])(?<pack>[A-Z]*)-?(?<reel>\d{2})?(?<value>\d+[RKM]\d*|\d{3,4}|0R00|0R0|0R|0000|000|00|0|\d+)L?$""",
                sizeMap = mapOf(
                    "0075" to "0075", "0100" to "0100", "0201" to "0201", "0402" to "0402", "0603" to "0603",
                    "0805" to "0805", "1206" to "1206", "1210" to "1210", "1218" to "1218", "2010" to "2010", "2512" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "C" to "0.25%", "D" to "0.5%", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "Z" to "0%"),
                suffixMap = mapOf("R" to "Ω", "K" to "KΩ", "M" to "MΩ"),
                isResistor = true
            )
        )

        // 15. Российские резисторы Р1-12 и Р1-16
        val rusTolMap = mutableMapOf<String, String>()
        val baseTol = mapOf(
            "0.05" to "0.05%", "0.1" to "0.1%", "0.25" to "0.25%",
            "0.5" to "0.5%", "1" to "1%", "2" to "2%", "5" to "5%",
            "10" to "10%", "20" to "20%"
        )
        for ((k, v) in baseTol) {
            rusTolMap[k] = v
            rusTolMap[k.replace('.', ',')] = v
            rusTolMap[v] = v
            rusTolMap[v.replace('.', ',')] = v
        }

        // Р1-12
        rules.add(
            VendorRule(
                name = "Rus_P1-12",
                compType = "resistor",
                patternStr = """^Р1-12-(?<size>[\d.,]+)\s+(?<value>[^\s]+)\s+(?<tolerance>[\d.,]+)\s*%?.*$""",
                sizeMap = mapOf(
                    "0.062" to "0402", "0,062" to "0402",
                    "0.1" to "0603", "0,1" to "0603",
                    "0.125" to "0805", "0,125" to "0805",
                    "0.25" to "1206", "0,25" to "1206",
                    "0.33" to "1210", "0,33" to "1210",
                    "0.5" to "2010", "0,5" to "2010",
                    "0.75" to "2512", "0,75" to "2512",
                    "1.0" to "2512", "1,0" to "2512",
                    "2.0" to "4020", "2,0" to "4020"
                ),
                toleranceMap = rusTolMap,
                valueParser = ::parseRussianResistorValue,
                isResistor = true
            )
        )

        // Р1-16
        rules.add(
            VendorRule(
                name = "Rus_P1-16",
                compType = "resistor",
                patternStr = """^Р1-16-(?<size>[\d.,]+)\s+(?<value>[^\s]+)\s+(?<tolerance>[\d.,]+)\s*%?.*$""",
                sizeMap = mapOf(
                    "0.016" to "0402", "0,016" to "0402",
                    "0.032" to "0603", "0,032" to "0603",
                    "0.063" to "0805", "0,063" to "0805",
                    "0.125" to "1206", "0,125" to "1206",
                    "0.25" to "2010", "0,25" to "2010",
                    "0.5" to "2512", "0,5" to "2512",
                    "1.0" to "4020", "1,0" to "4020"
                ),
                toleranceMap = rusTolMap,
                valueParser = ::parseRussianResistorValue,
                isResistor = true
            )
        )

        return rules
    }
}
