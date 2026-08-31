package com.barcodedecoder

import com.barcodedecoder.engine.RuleFactory
import com.barcodedecoder.engine.VendorParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class VendorEngineTest {

    private val parser = VendorParser(RuleFactory.createAllRules())

    // --- CAPACITORS ---

    @Test
    fun testCapacitorYageo() {
        val result = parser.parse("CC0603KRX7R9BB104")
        assertNotNull("Should parse Yageo capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)
    }

    @Test
    fun testCapacitorMurata() {
        val result = parser.parse("GRM155R71C104KA88D")
        assertNotNull("Should parse Murata capacitor", result)
        assertEquals("C_0402_X7R_100nF_16V", result!!.unifiedName)

        val auto = parser.parse("GCM188R71H104KA57D")
        assertNotNull("Should parse Murata automotive capacitor", auto)
        assertEquals("C_0603_X7R_100nF_50V", auto!!.unifiedName)
    }

    @Test
    fun testCapacitorSamsung() {
        val result = parser.parse("CL10B104KB8NNNC")
        assertNotNull("Should parse Samsung capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)
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
    fun testCapacitorTaiyoYuden() {
        val result = parser.parse("EMK105BJ104KV-F")
        assertNotNull("Should parse Taiyo Yuden capacitor", result)
        assertEquals("C_0402_X5R_100nF_16V", result!!.unifiedName)
    }

    @Test
    fun testCapacitorWalsin() {
        val result = parser.parse("0603B104K500CT")
        assertNotNull("Should parse Walsin capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)
    }

    @Test
    fun testCapacitorKemet() {
        val result = parser.parse("C0603C104K5RACTU")
        assertNotNull("Should parse Kemet capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)
    }

    // --- RESISTORS ---

    @Test
    fun testResistorYageo() {
        val result = parser.parse("RC0603FR-0710KL")
        assertNotNull("Should parse Yageo resistor", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)

        val jumper = parser.parse("RC0402JR-070RL")
        assertNotNull("Should parse Yageo 0R resistor", jumper)
        assertEquals("R_0402_0R", jumper!!.unifiedName)
    }

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
        assertEquals("R_1206_0R", jumper!!.unifiedName)
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
        assertEquals("R_0603_0R", jumper!!.unifiedName)
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
        assertEquals("R_0402_0R", jumper!!.unifiedName)
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
    }

    @Test
    fun testResistorRussian() {
        val p1_12 = parser.parse("Р1-12-0.125 10кОм 1%")
        assertNotNull("Should parse Russian P1-12 resistor", p1_12)
        assertEquals("R_0805_10K_1%", p1_12!!.unifiedName)

        val p1_16 = parser.parse("Р1-16-0.032 100Ом 1%")
        assertNotNull("Should parse Russian P1-16 resistor", p1_16)
        assertEquals("R_0603_100R_1%", p1_16!!.unifiedName)
    }

    // --- BARCODE REEL TRIMMING ---

    @Test
    fun testTrimmedBarcode() {
        val result = parser.parse("12345RC0603FR-0710KLXYZ99")
        assertNotNull("Should parse resistor with prefix/suffix trimming", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)

        val dataMatrix1P = parser.parse("1PCRCW060310K0FKEA;Q5000;1T20230815")
        assertNotNull("Should parse Vishay 1P DataMatrix reel label", dataMatrix1P)
        assertEquals("R_0603_10K_1%", dataMatrix1P!!.unifiedName)
    }
}
