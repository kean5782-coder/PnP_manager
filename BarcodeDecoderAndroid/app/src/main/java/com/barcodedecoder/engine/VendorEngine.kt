package com.barcodedecoder.engine

import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale
import java.util.regex.Pattern

const val MAX_TRIM_LEFT = 15
const val MAX_TRIM_RIGHT = 80

fun formatG(num: Double): String {
    if (num == 0.0) return "0"
    val df = DecimalFormat("0.###", DecimalFormatSymbols(Locale.US))
    return df.format(num)
}

fun parseRussianResistorValue(rawInput: String): String {
    var raw = rawInput.lowercase().trim()
    raw = raw.replace("ом", "")
    raw = raw.replace("r", "")
    val pattern = Pattern.compile("""^([\d.,]+)\s*([ккм]?)""")
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

    fun match(code: String): Map<String, String>? {
        val matcher = pattern.matcher(code)
        if (!matcher.matches()) return null

        val result = mutableMapOf<String, String>()
        // Named groups extraction
        val groupNames = listOf(
            "size", "dielectric", "code", "tolerance", "voltage",
            "type", "suffix", "series", "termination", "size_code",
            "size_tolerance", "temp_code", "cap_code", "cap_tolerance",
            "thickness", "special", "packaging", "internal", "rest",
            "pack", "value", "reel", "func", "term", "prefix"
        )
        for (name in groupNames) {
            try {
                val value = matcher.group(name)
                if (value != null) {
                    result[name] = value
                }
            } catch (_: IllegalArgumentException) {
                // Group name not in pattern
            }
        }
        return result
    }
}

data class ParseResult(
    val rule: VendorRule,
    val groups: Map<String, String>,
    val usedCode: String,
    val leftTrim: Int,
    val rightTrim: Int,
    val unifiedName: String
)

class VendorParser(val rules: List<VendorRule>) {

    fun parse(code: String, vendorName: String? = null): ParseResult? {
        val original = code.trim()
        if (original.isEmpty()) return null

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

        // Try without trimming first
        val directMatch = tryMatch(original)
        if (directMatch != null) {
            val (rule, groups) = directMatch
            val unified = convertToUnified(original, rule, groups)
            return ParseResult(rule, groups, original, 0, 0, unified)
        }

        data class Candidate(val left: Int, val right: Int, val total: Int)
        val candidates = mutableListOf<Candidate>()

        for (left in 0..MAX_TRIM_LEFT) {
            for (right in 0..MAX_TRIM_RIGHT) {
                if (left == 0 && right == 0) continue
                if (left >= original.length || right >= original.length) continue
                candidates.add(Candidate(left, right, left + right))
            }
        }

        candidates.sortWith(compareBy({ it.total }, { it.left }))

        for ((left, right, _) in candidates) {
            if (left + right >= original.length) continue
            val candidate = original.substring(left, original.length - right)
            if (candidate.isEmpty()) continue
            val match = tryMatch(candidate)
            if (match != null) {
                val (rule, groups) = match
                val unified = convertToUnified(candidate, rule, groups)
                return ParseResult(rule, groups, candidate, left, right, unified)
            }
        }

        return null
    }

    fun convertToUnified(code: String, rule: VendorRule, groups: Map<String, String>): String {
        return if (rule.isResistor) {
            val sizeCode = groups["size"] ?: ""
            val size = rule.sizeMap[sizeCode] ?: sizeCode
            val rawValue = groups["value"] ?: groups["code"] ?: ""
            val valueStr = if (rawValue.isNotEmpty()) {
                rule.valueParser?.invoke(rawValue) ?: parseResistorValue(rawValue, rule.suffixMap)
            } else {
                "?"
            }
            val toleranceCode = groups["tolerance"] ?: ""
            val tolerance = rule.toleranceMap[toleranceCode] ?: toleranceCode
            if (valueStr == "0R") {
                "R_${size}_0R"
            } else {
                "R_${size}_${valueStr}_${tolerance}"
            }
        } else {
            val sizeCode = groups["size"] ?: ""
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

    private fun parseResistorValue(rawInput: String, suffixMap: Map<String, String>): String {
        var raw = rawInput.trim().uppercase()
        raw = raw.replace("Ω", "")
        raw = raw.replace("(?i)ом".toRegex(), "")

        if (raw == "000" || raw == "0" || raw == "0R") return "0R"

        val matchInside = Pattern.compile("""([KMR])(\d+)$""").matcher(raw)
        if (matchInside.find() && matchInside.start() < raw.length - 1) {
            val letter = matchInside.group(1)
            val numPart = raw.substring(0, matchInside.start())
            val decimalPart = matchInside.group(2)
            val valNum = "$numPart.$decimalPart".toDoubleOrNull() ?: 0.0
            return when (letter) {
                "R" -> "${formatG(valNum)}R"
                "K" -> "${formatG(valNum)}K"
                "M" -> "${formatG(valNum)}M"
                else -> "${formatG(valNum)}R"
            }
        }

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

object RuleFactory {
    fun createAllRules(): List<VendorRule> {
        return createCapacitorRules() + createResistorRules()
    }

    fun createCapacitorRules(): List<VendorRule> {
        val rules = mutableListOf<VendorRule>()

        // CCTC
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

        // KEMET
        rules.add(
            VendorRule(
                name = "KEMET",
                compType = "capacitor",
                patternStr = """^C(?<size>\d{4})(?<type>[A-Z])(?<code>\d{3})(?<tolerance>[BCDFGJKMOPZ])(?<voltage>\d)(?<dielectric>[GRPUV])(?<suffix>[A-Z]{0,2})$""",
                sizeMap = mapOf("0402" to "0402", "0603" to "0603", "0805" to "0805", "1206" to "1206", "1210" to "1210", "1812" to "1812", "1825" to "1825", "2220" to "2220", "2225" to "2225"),
                dielectricMap = mapOf("G" to "C0G", "R" to "X7R", "P" to "X5R", "U" to "Z5U", "V" to "Y5V"),
                voltageMap = mapOf("1" to "100V", "2" to "200V", "3" to "25V", "4" to "16V", "5" to "50V", "6" to "35V", "7" to "4V", "8" to "10V", "9" to "6.3V"),
                toleranceMap = mapOf("B" to "0.10pF", "C" to "0.25pF", "D" to "0.5pF", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "M" to "20%", "Z" to "+80%/-20%"),
                isResistor = false
            )
        )

        // Taiyo Yuden
        rules.add(
            VendorRule(
                name = "TaiyoYuden",
                compType = "capacitor",
                patternStr = """^(?<voltage>[PALJETGUHQSX])(?<series>[MVW])(?<termination>[KS])(?<sizeCode>\d{3})(?<sizeTolerance>[A-E]?)(?<tempCode>BJ|B7|C6|C7|LD|CG|UJ|UK)(?<capCode>\d+R\d+|\d{3})(?<capTolerance>[ABCDFGJKMZ])(?<thickness>[KHCEDPVWADGLNYM])(?<special>[A-Z]?)-?(?<packaging>[FTPRW]?)(?<internal>[A-Z]?)$""",
                sizeMap = mapOf("021" to "008004", "042" to "01005", "063" to "0201", "105" to "0402", "107" to "0603", "212" to "0805", "316" to "1206", "325" to "1210", "432" to "1812"),
                dielectricMap = mapOf("BJ" to "X5R", "B7" to "X7R", "C6" to "X6S", "C7" to "X7S", "LD" to "X5R", "CG" to "C0G", "UJ" to "U2J", "UK" to "U2K"),
                voltageMap = mapOf("P" to "2.5V", "A" to "4V", "J" to "6.3V", "L" to "10V", "E" to "16V", "T" to "25V", "G" to "35V", "U" to "50V", "H" to "100V", "Q" to "250V", "S" to "630V", "X" to "2000V"),
                isResistor = false
            )
        )

        // Murata
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

        // Samsung Capacitor
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

        // TDK Capacitor
        rules.add(
            VendorRule(
                name = "TDK_Cap",
                compType = "capacitor",
                patternStr = """^C(?<size>\d{4})(?<dielectric>COG|C0G|X5R|X6S|X7R|X7S|X7T)(?<voltage>0G|0J|1A|1C|1E|1V|1H|1N)(?<code>\d{3})(?<tolerance>[BCDFGJKM])(?<rest>.*)$""",
                sizeMap = mapOf("0402" to "01005", "0603" to "0201", "1005" to "0402", "1608" to "0603", "2012" to "0805", "3216" to "1206", "3225" to "1210", "4532" to "1812", "5750" to "2220"),
                dielectricMap = mapOf("COG" to "C0G", "C0G" to "C0G", "X5R" to "X5R", "X6S" to "X6S", "X7R" to "X7R", "X7S" to "X7S", "X7T" to "X7T"),
                voltageMap = mapOf("0G" to "4V", "0J" to "6.3V", "1A" to "10V", "1C" to "16V", "1E" to "25V", "1V" to "35V", "1H" to "50V", "1N" to "75V"),
                toleranceMap = mapOf("B" to "0.10pF", "C" to "0.25pF", "D" to "0.50pF", "F" to "1%", "G" to "2%", "J" to "5%", "K" to "10%", "M" to "20%"),
                isResistor = false
            )
        )

        // Walsin Capacitor
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

        // Yageo Capacitor
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

    fun createResistorRules(): List<VendorRule> {
        val rules = mutableListOf<VendorRule>()

        // Viking
        rules.add(
            VendorRule(
                name = "Viking",
                compType = "resistor",
                patternStr = """^CR-(?<size>E5|01|02|03|05|06|10|0A|12|25|62)(?<tolerance>[BDFJ])(?<pack>[A-Z0-9]*?)-(?<value>.+)$""",
                sizeMap = mapOf("E5" to "01005", "01" to "0201", "02" to "0402", "03" to "0603", "05" to "0805", "06" to "1206", "10" to "1210", "0A" to "2010", "12" to "2512", "25" to "1225", "62" to "0612"),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "J" to "5%"),
                suffixMap = mapOf("R" to "Ω", "K" to "KΩ", "M" to "MΩ", "L" to "mΩ"),
                isResistor = true
            )
        )

        val parseRcOrRiValue: (String) -> String = { rawInput ->
            val raw = rawInput.uppercase()
            if (raw.contains('R')) {
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

        // RC Yageo
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

        // RI HOTTECH
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

        // ROHM ESR
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

        // ROHM PMR
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

        // Samsung Resistor
        rules.add(
            VendorRule(
                name = "Samsung_Res",
                compType = "resistor",
                patternStr = """^(?<prefix>RC|RCB|RF|RM|RN|RK|RP|RUT|RU|RUK|RJ|RCW|RCV|RCS|RFS|RPS|RH)(?<size>\d{4})(?<tolerance>[DFGJ])(?<code>\d{3}|\d{4}|[0-9]R[0-9]{1,2})(?<pack>[A-Z]{2})$""",
                sizeMap = mapOf(
                    "0402" to "0402", "0603" to "0603", "1005" to "0402", "1608" to "0603", "2012" to "0805",
                    "3216" to "1206", "3225" to "1210", "5025" to "2010", "6432" to "2512"
                ),
                toleranceMap = mapOf("D" to "0.5%", "F" to "1%", "G" to "2%", "J" to "5%"),
                suffixMap = mapOf("R" to "Ω", "K" to "KΩ", "M" to "MΩ"),
                isResistor = true
            )
        )

        // Walsin Resistor
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

        // Yageo Resistor
        val yageoSeries = "AC|RC|RT|RL|RV|RE|RA|RK|RS|RP|RQ|RN|RM"
        rules.add(
            VendorRule(
                name = "Yageo",
                compType = "resistor",
                patternStr = """^(?<series>$yageoSeries)(?<size>\d{4})(?<tolerance>[BDFJ])(?<pack>[A-Z]*)-?(?<reel>\d{2})?(?<value>.+?)L$""",
                sizeMap = mapOf(
                    "0075" to "0075", "0100" to "0100", "0201" to "0201", "0402" to "0402", "0603" to "0603",
                    "0805" to "0805", "1206" to "1206", "1210" to "1210", "1218" to "1218", "2010" to "2010", "2512" to "2512"
                ),
                toleranceMap = mapOf("B" to "0.1%", "D" to "0.5%", "F" to "1%", "J" to "5%"),
                suffixMap = mapOf("R" to "Ω", "K" to "KΩ", "M" to "MΩ"),
                isResistor = true
            )
        )

        // Russian Resistors
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

        // P1-12
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

        // P1-16
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
