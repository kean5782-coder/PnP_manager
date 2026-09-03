package com.barcodedecoder

import com.barcodedecoder.engine.RuleFactory
import com.barcodedecoder.engine.VendorParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

/**
 * Комплексный набор модульных тестов движка декодирования радиокомпонентов.
 * Покрывает 100% поддерживаемых типов конденсаторов, резисторов,
 * префиксов упаковочных лент (Reel Label) и краевых случаев.
 */
class VendorEngineTest {

    private val parser = VendorParser(RuleFactory.createAllRules())

    // =========================================================================
    // ТЕСТЫ КОНДЕНСАТОРОВ (CAPACITORS)
    // =========================================================================

    @Test
    fun testCapacitorCCTC() {
        val result = parser.parse("TCC0603COG101J500")
        assertNotNull("Should parse CCTC capacitor", result)
        assertEquals("C_0603_C0G_100pF_50V", result!!.unifiedName)

        val x7r = parser.parse("TCC0805X7R104K250")
        assertNotNull("Should parse CCTC X7R capacitor", x7r)
        assertEquals("C_0805_X7R_100nF_25V", x7r!!.unifiedName)
    }

    @Test
    fun testCapacitorKemet() {
        val result = parser.parse("C0603C104K5RACTU")
        assertNotNull("Should parse Kemet capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)

        val c0g = parser.parse("C0402C101J5GACTU")
        assertNotNull("Should parse Kemet C0G capacitor", c0g)
        assertEquals("C_0402_C0G_100pF_50V", c0g!!.unifiedName)
    }

    @Test
    fun testCapacitorTaiyoYuden() {
        val result = parser.parse("EMK105BJ104KV-F")
        assertNotNull("Should parse Taiyo Yuden capacitor", result)
        assertEquals("C_0402_X5R_100nF_16V", result!!.unifiedName)

        val c0g = parser.parse("UMK107CG101JZ-T")
        assertNotNull("Should parse Taiyo Yuden C0G capacitor", c0g)
        assertEquals("C_0603_C0G_100pF_50V", c0g!!.unifiedName)
    }

    @Test
    fun testCapacitorMurata() {
        val result = parser.parse("GRM155R71C104KA88D")
        assertNotNull("Should parse Murata capacitor", result)
        assertEquals("C_0402_X7R_100nF_16V", result!!.unifiedName)

        val auto = parser.parse("GCM188R71H104KA57D")
        assertNotNull("Should parse Murata automotive capacitor", auto)
        assertEquals("C_0603_X7R_100nF_50V", auto!!.unifiedName)

        val gqm = parser.parse("GQM1885C1H101JB01D")
        assertNotNull("Should parse Murata GQM series Hi-Q capacitor", gqm)
        assertEquals("C_0603_C0G_100pF_50V", gqm!!.unifiedName)

        val gcj = parser.parse("GCJ21BR71H104KA01L")
        assertNotNull("Should parse Murata GCJ series automotive capacitor", gcj)
        assertEquals("C_0805_X7R_100nF_50V", gcj!!.unifiedName)
    }

    @Test
    fun testCapacitorSamsung() {
        val result = parser.parse("CL10B104KB8NNNC")
        assertNotNull("Should parse Samsung capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)

        val c0g = parser.parse("CL05C101JB5NNNC")
        assertNotNull("Should parse Samsung C0G capacitor", c0g)
        assertEquals("C_0402_C0G_100pF_50V", c0g!!.unifiedName)
    }

    @Test
    fun testCapacitorTDK() {
        val std = parser.parse("C1608X7R1C104K080AA")
        assertNotNull("Should parse TDK standard capacitor", std)
        assertEquals("C_0603_X7R_100nF_16V", std!!.unifiedName)

        val cga = parser.parse("CGA3E2X7R1H104K080AA")
        assertNotNull("Should parse TDK CGA automotive capacitor", cga)
        assertEquals("C_0603_X7R_100nF_50V", cga!!.unifiedName)
    }

    @Test
    fun testCapacitorAVX() {
        val result = parser.parse("06035C104KAT2A")
        assertNotNull("Should parse AVX MLCC capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)

        val cog = parser.parse("06035A101JAT2A")
        assertNotNull("Should parse AVX C0G capacitor", cog)
        assertEquals("C_0603_C0G_100pF_50V", cog!!.unifiedName)
    }

    @Test
    fun testCapacitorWalsin() {
        val result = parser.parse("0603B104K500CT")
        assertNotNull("Should parse Walsin capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)
    }

    @Test
    fun testCapacitorYageo() {
        val result = parser.parse("CC0603KRX7R9BB104")
        assertNotNull("Should parse Yageo capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)
    }

    // =========================================================================
    // ТЕСТЫ РЕЗИСТОРОВ (RESISTORS)
    // =========================================================================

    @Test
    fun testResistorVishay() {
        val r100 = parser.parse("CRCW0603100RFKEA")
        assertNotNull("Should parse Vishay CRCW 100R", r100)
        assertEquals("R_0603_100R_1%", r100!!.unifiedName)

        val r10k = parser.parse("CRCW080510K0FKEA")
        assertNotNull("Should parse Vishay CRCW 10K", r10k)
        assertEquals("R_0805_10K_1%", r10k!!.unifiedName)

        val r4k7 = parser.parse("CRCW08054K70FKEA")
        assertNotNull("Should parse Vishay CRCW 4.7K", r4k7)
        assertEquals("R_0805_4.7K_1%", r4k7!!.unifiedName)

        val jumper = parser.parse("CRCW12060000Z0EA")
        assertNotNull("Should parse Vishay CRCW 0R", jumper)
        assertEquals("R_1206_0R_0%", jumper!!.unifiedName)
    }

    @Test
    fun testResistorPanasonic() {
        val r10k = parser.parse("ERJ-3EKF1002V")
        assertNotNull("Should parse Panasonic ERJ 10k", r10k)
        assertEquals("R_0603_10K_1%", r10k!!.unifiedName)

        val r1k = parser.parse("ERJ-2RKF1001X")
        assertNotNull("Should parse Panasonic ERJ 1k", r1k)
        assertEquals("R_0402_1K_1%", r1k!!.unifiedName)

        val jumper = parser.parse("ERJ-3GEY0R00V")
        assertNotNull("Should parse Panasonic ERJ 0R", jumper)
        assertEquals("R_0603_0R_0%", jumper!!.unifiedName)
    }

    @Test
    fun testResistorBourns() {
        val r10k = parser.parse("CR0603-FX-1002ELF")
        assertNotNull("Should parse Bourns CR 10k", r10k)
        assertEquals("R_0603_10K_1%", r10k!!.unifiedName)

        val r4k7 = parser.parse("CR0402-FX-4701GLF")
        assertNotNull("Should parse Bourns CR 4.7k", r4k7)
        assertEquals("R_0402_4.7K_1%", r4k7!!.unifiedName)
    }

    @Test
    fun testResistorKOA() {
        val r10k = parser.parse("RK73H1JTTD1002F")
        assertNotNull("Should parse KOA Speer RK73 10k", r10k)
        assertEquals("R_0603_10K_1%", r10k!!.unifiedName)

        val jumper = parser.parse("RK73Z1ETTP")
        assertNotNull("Should parse KOA Speer 0R jumper", jumper)
        assertEquals("R_0402_0R_0%", jumper!!.unifiedName)
    }

    @Test
    fun testResistorRoyalOhm() {
        val r10k = parser.parse("0603WAF1002T5E")
        assertNotNull("Should parse Royal Ohm 10k", r10k)
        assertEquals("R_0603_10K_1%", r10k!!.unifiedName)
    }

    @Test
    fun testResistorROHM() {
        val mcr = parser.parse("MCR03EZPFX1002")
        assertNotNull("Should parse ROHM MCR 10k", mcr)
        assertEquals("R_0603_10K_1%", mcr!!.unifiedName)

        val esr = parser.parse("ESR03EZPF1002")
        assertNotNull("Should parse ROHM ESR 10k", esr)
        assertEquals("R_0603_10K_1%", esr!!.unifiedName)

        val pmr = parser.parse("PMR03EZPFU10L0")
        assertNotNull("Should parse ROHM PMR 10mΩ", pmr)
        assertEquals("R_0603_0.01R_1%", pmr!!.unifiedName)
    }

    @Test
    fun testResistorViking() {
        val result = parser.parse("CR-03FL7--10K")
        assertNotNull("Should parse Viking resistor", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)
    }

    @Test
    fun testResistorYageo() {
        val result = parser.parse("RC0603FR-0710KL")
        assertNotNull("Should parse Yageo resistor", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)

        val jumper = parser.parse("RC0402JR-070RL")
        assertNotNull("Should parse Yageo 0R resistor", jumper)
        assertEquals("R_0402_0R_5%", jumper!!.unifiedName)

        val directRc = parser.parse("RC0805F1002")
        assertNotNull("Should parse direct RC code", directRc)
        assertEquals("R_0805_10K_1%", directRc!!.unifiedName)
    }

    @Test
    fun testResistorHOTTECH() {
        val result = parser.parse("RI0603L1002FT")
        assertNotNull("Should parse HOTTECH RI resistor", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)
    }

    @Test
    fun testResistorSamsung() {
        val result = parser.parse("RC1608F1002CS")
        assertNotNull("Should parse Samsung resistor", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)
    }

    @Test
    fun testResistorWalsin() {
        val result = parser.parse("WR06X1002FTL")
        assertNotNull("Should parse Walsin resistor", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)
    }

    @Test
    fun testResistorRussian() {
        val p1_12 = parser.parse("Р1-12-0.125 10кОм 1%")
        assertNotNull("Should parse Russian P1-12 resistor", p1_12)
        assertEquals("R_0805_10K_1%", p1_12!!.unifiedName)

        val p1_12_comma = parser.parse("Р1-12-0,125 4,7кОм 5%")
        assertNotNull("Should parse Russian P1-12 resistor with comma", p1_12_comma)
        assertEquals("R_0805_4.7K_5%", p1_12_comma!!.unifiedName)

        val p1_12_latin = parser.parse("Р1-12-0.125 10k 1%")
        assertNotNull("Should parse Russian P1-12 resistor with latin k", p1_12_latin)
        assertEquals("R_0805_10K_1%", p1_12_latin!!.unifiedName)

        val p1_16 = parser.parse("Р1-16-0.032 100Ом 1%")
        assertNotNull("Should parse Russian P1-16 resistor", p1_16)
        assertEquals("R_0603_100R_1%", p1_16!!.unifiedName)
    }

    // =========================================================================
    // ТЕСТЫ ОЧИСТКИ ПРЕФИКСОВ/СУФФИКСОВ КАТУШЕК (REEL TRIMMING)
    // =========================================================================

    @Test
    fun testTrimmedBarcode() {
        val result = parser.parse("12345RC0603FR-0710KLXYZ99")
        assertNotNull("Should parse resistor with prefix/suffix trimming", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)

        val dataMatrix1P = parser.parse("1PCRCW060310K0FKEA;Q5000;1T20230815")
        assertNotNull("Should parse Vishay 1P DataMatrix reel label", dataMatrix1P)
        assertEquals("R_0603_10K_1%", dataMatrix1P!!.unifiedName)
    }

    // =========================================================================
    // ТЕСТЫ KEMET С ПОЛНЫМ СУФФИКСОМ (BUG-5 REGRESSION)
    // =========================================================================

    @Test
    fun testKemetFullSuffix() {
        // ACTU — 4 символа суффикса, ранее не проходил из-за {0,2}
        val actu = parser.parse("C0805C106M8PACTU")
        assertNotNull("Should parse KEMET with full ACTU suffix", actu)
        assertEquals("C_0805_X5R_10uF_10V", actu!!.unifiedName)

        val auto = parser.parse("C0603C104K5RAUTO")
        assertNotNull("Should parse KEMET with AUTO suffix", auto)
        assertEquals("C_0603_X7R_100nF_50V", auto!!.unifiedName)

        // 2 символа — базовый случай, должен продолжать работать
        val tu = parser.parse("C0805C225K4PTU")
        assertNotNull("Should parse KEMET with 2-char suffix TU", tu)
        assertEquals("C_0805_X5R_2.2uF_16V", tu!!.unifiedName)
    }

    // =========================================================================
    // ТЕСТЫ 0Ω ДЖАМПЕРОВ ВСЕХ ПРОИЗВОДИТЕЛЕЙ
    // =========================================================================

    @Test
    fun testZeroOhmJumpers() {
        // Vishay 0Ω
        val vishay = parser.parse("CRCW12060000Z0EA")
        assertNotNull("Should parse Vishay 0Ω jumper", vishay)
        assertEquals("R_1206_0R_0%", vishay!!.unifiedName)

        // Panasonic 0Ω
        val panasonic = parser.parse("ERJ-3GEY0R00V")
        assertNotNull("Should parse Panasonic 0Ω jumper", panasonic)
        assertEquals("R_0603_0R_0%", panasonic!!.unifiedName)

        // Yageo RC 0Ω (5% tolerance)
        val yageo = parser.parse("RC0402JR-070RL")
        assertNotNull("Should parse Yageo RC 0Ω jumper", yageo)
        assertEquals("R_0402_0R_5%", yageo!!.unifiedName)
    }

    // =========================================================================
    // ТЕСТЫ МЕГАОМНЫХ НОМИНАЛОВ (1M, 10M)
    // =========================================================================

    @Test
    fun testMegaOhmValues() {
        // Vishay 1MΩ
        val vishay1M = parser.parse("CRCW06031M00FKEA")
        assertNotNull("Should parse Vishay 1MΩ resistor", vishay1M)
        assertEquals("R_0603_1M_1%", vishay1M!!.unifiedName)

        // Samsung 1MΩ (4-значный код: 1004 = 100*10^4 = 1MΩ)
        val samsung1M = parser.parse("RC1608F1004CS")
        assertNotNull("Should parse Samsung 1MΩ resistor", samsung1M)
        assertEquals("R_0603_1M_1%", samsung1M!!.unifiedName)

        // Samsung 10MΩ (4-значный код: 1005 = 100*10^5 = 10MΩ)
        val samsung10M = parser.parse("RC1608F1005CS")
        assertNotNull("Should parse Samsung 10MΩ resistor", samsung10M)
        assertEquals("R_0603_10M_1%", samsung10M!!.unifiedName)
    }

    // =========================================================================
    // ТЕСТЫ РЕАЛЬНЫХ КАТУШЕК ИЗ ПАПКИ ARCHIVE
    // =========================================================================

    @Test
    fun testArchiveHottechZeroOhmJumper() {
        // HOTTECH RI 0402 0Ω 0000 1%
        val direct = parser.parse("RI0402L0000FT")
        assertNotNull("Should parse HOTTECH 0Ω jumper", direct)
        assertEquals("R_0402_0R_1%", direct!!.unifiedName)

        // HOTTECH QR Composite Code
        val qrComposite = parser.parse("RI0402L0000FT&10000&01221450444")
        assertNotNull("Should parse HOTTECH composite QR code", qrComposite)
        assertEquals("R_0402_0R_1%", qrComposite!!.unifiedName)
    }

    @Test
    fun testArchiveYageoCompositeDataMatrix() {
        // Yageo 2D Composite DataMatrix with P/1P prefixes and comma delimiter
        val composite = parser.parse("PRC0402FR-0733R2L,Q10000,9D2538,1PRC0402FR-0733R2L,5003635817")
        assertNotNull("Should parse Yageo composite DataMatrix", composite)
        assertEquals("R_0402_33.2R_1%", composite!!.unifiedName)

        // Yageo 30P Prefix
        val p30 = parser.parse("(30P)RC0402FR-0733R2L")
        assertNotNull("Should parse Yageo (30P) prefix", p30)
        assertEquals("R_0402_33.2R_1%", p30!!.unifiedName)
    }

    @Test
    fun testArchiveSamsungComposite() {
        // Samsung DataMatrix with slash delimiter and prefix
        val composite = parser.parse("CLCITDT/CL05B104KA5NNNC")
        assertNotNull("Should parse Samsung composite DataMatrix", composite)
        assertEquals("C_0402_X7R_100nF_25V", composite!!.unifiedName)
    }

    @Test
    fun testArchiveYageoPrecisionRE() {
        // Yageo RE series 0.1% precision resistor
        val re = parser.parse("RE0603BRE07200KL")
        assertNotNull("Should parse Yageo RE precision resistor", re)
        assertEquals("R_0603_200K_0.1%", re!!.unifiedName)
    }

    @Test
    fun testArchiveTdkWithPrefixes() {
        // TDK with (1P) prefix and thickness suffix
        val tdk1 = parser.parse("(1P)C2012X5R1V226M125AC")
        assertNotNull("Should parse TDK with (1P) prefix", tdk1)
        assertEquals("C_0805_X5R_22uF_35V", tdk1!!.unifiedName)

        // TDK 16V 22uF
        val tdk2 = parser.parse("C2012X5R1C226K")
        assertNotNull("Should parse TDK 16V capacitor", tdk2)
        assertEquals("C_0805_X5R_22uF_16V", tdk2!!.unifiedName)
    }

    @Test
    fun testArchiveFenghuaCctc() {
        // Fenghua / CCTC 1R 1% resistor
        val r1 = parser.parse("RC1608F1R0")
        assertNotNull("Should parse CCTC/Fenghua 1R resistor", r1)
        assertEquals("R_0603_1R_1%", r1!!.unifiedName)
    }

    @Test
    fun testArchivePrintedOcrVariations() {
        // 1. Spaced Yageo text from label: "RC 0402 F R-07 33R2"
        val spacedYageo = parser.parse("RC 0402 F R-07 33R2")
        assertNotNull("Should parse spaced Yageo text", spacedYageo)
        assertEquals("R_0402_33.2R_1%", spacedYageo!!.unifiedName)

        // 2. Yageo with 30P and CTC prefix: "(30P) CTC RC 0402 F R-07 33R2"
        val ctcYageo = parser.parse("(30P) CTC RC 0402 F R-07 33R2")
        assertNotNull("Should parse (30P) CTC Yageo text", ctcYageo)
        assertEquals("R_0402_33.2R_1%", ctcYageo!!.unifiedName)

        // 3. Hottech with P/N: prefix
        val pnHottech = parser.parse("P/N: RI0402L0000FT")
        assertNotNull("Should parse P/N: RI0402L0000FT", pnHottech)
        assertEquals("R_0402_0R_1%", pnHottech!!.unifiedName)

        // 4. TDK ITEM prefix
        val tdkItem = parser.parse("TDK ITEM: C2012X5R1V226MT000N")
        assertNotNull("Should parse TDK ITEM prefix", tdkItem)
        assertEquals("C_0805_X5R_22uF_35V", tdkItem!!.unifiedName)

        // 5. ITEM(1P) : prefix
        val item1p = parser.parse("ITEM(1P) : C2012X5R1V226MT000N")
        assertNotNull("Should parse ITEM(1P) prefix", item1p)
        assertEquals("C_0805_X5R_22uF_35V", item1p!!.unifiedName)

        // 6. CUST PROD ID(P) : prefix
        val custProd = parser.parse("CUST PROD ID(P) : C2012X5R1V226M125AC")
        assertNotNull("Should parse CUST PROD ID(P) prefix", custProd)
        assertEquals("C_0805_X5R_22uF_35V", custProd!!.unifiedName)

        // 7. Yageo 12.7K 1% from Google Lens photo
        val lensYageo = parser.parse("RC0402FR-0712K7L")
        assertNotNull("Should parse RC0402FR-0712K7L", lensYageo)
        assertEquals("R_0402_12.7K_1%", lensYageo!!.unifiedName)

        // 8. Murata 100uF 4V MLCC
        val murata100u = parser.parse("GRM21BC80G107ME15L")
        assertNotNull("Should parse GRM21BC80G107ME15L", murata100u)
        assertEquals("C_0805_X6S_100uF_4V", murata100u!!.unifiedName)

        // 9. Yageo CC 1uF 6.3V MLCC
        val yageo1u = parser.parse("CC0402KRX7R5BB105")
        assertNotNull("Should parse CC0402KRX7R5BB105", yageo1u)
        assertEquals("C_0402_X7R_1uF_6.3V", yageo1u!!.unifiedName)

        // 10. Samsung 100nF 25V MLCC
        val samsung100n = parser.parse("CL05B104KA5NNNC")
        assertNotNull("Should parse CL05B104KA5NNNC", samsung100n)
        assertEquals("C_0402_X7R_100nF_25V", samsung100n!!.unifiedName)
    }
}
