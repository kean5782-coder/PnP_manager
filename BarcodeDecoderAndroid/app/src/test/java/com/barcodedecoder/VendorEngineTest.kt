package com.barcodedecoder

import com.barcodedecoder.engine.RuleFactory
import com.barcodedecoder.engine.VendorParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class VendorEngineTest {

    private val parser = VendorParser(RuleFactory.createAllRules())

    @Test
    fun testCapacitorYageo() {
        val result = parser.parse("CC0603KRX7R9BB104")
        assertNotNull("Should parse Yageo capacitor", result)
        assertEquals("C_0603_X7R_100nF_50V", result!!.unifiedName)
    }

    @Test
    fun testResistorYageo() {
        val result = parser.parse("RC0603FR-0710KL")
        assertNotNull("Should parse Yageo resistor", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)
    }

    @Test
    fun testRussianResistorP1_12() {
        val result = parser.parse("Р1-12-0.125 10кОм 1%")
        assertNotNull("Should parse Russian P1-12 resistor", result)
        assertEquals("R_0805_10K_1%", result!!.unifiedName)
    }

    @Test
    fun testTrimmedBarcode() {
        // Barcode with prefix and suffix noise
        val result = parser.parse("12345RC0603FR-0710KLXYZ99")
        assertNotNull("Should parse resistor with prefix/suffix trimming", result)
        assertEquals("R_0603_10K_1%", result!!.unifiedName)
    }
}
