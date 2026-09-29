package com.mrpl.wristband.data

import android.content.Context
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class HistoryManagerTest {

    private lateinit var context: Context

    @Before
    fun setUp() {
        context = InstrumentationRegistry.getInstrumentation().targetContext
        // Clear preferences before each test
        context.getSharedPreferences("exposure_history", Context.MODE_PRIVATE).edit().clear().commit()
    }

    @After
    fun tearDown() {
        context.getSharedPreferences("exposure_history", Context.MODE_PRIVATE).edit().clear().commit()
    }

    @Test
    fun testRecordSurvivesSavingAndReloading() {
        val record = ScanUiResult(
            wristbandId = "TEST-01",
            timestamp = "12 NOV 2024 - 10:00:00",
            dosePpmHr = 45.5,
            twaPpm = 5.6,
            deltaLStar = 12.0,
            deltaE00 = 10.0,
            verdict = "SAFE"
        )
        HistoryManager.saveRecord(context, record)
        
        val loaded = HistoryManager.getRecords(context)
        assertEquals(1, loaded.size)
        val loadedRecord = loaded[0]
        assertEquals("TEST-01", loadedRecord.wristbandId)
        assertEquals(45.5, loadedRecord.dosePpmHr)
        assertEquals(5.6, loadedRecord.twaPpm)
        assertEquals(12.0, loadedRecord.deltaLStar)
        assertEquals(10.0, loadedRecord.deltaE00)
    }

    @Test
    fun testSameIdSameDateReplacesPreviousRecord() {
        val record1 = ScanUiResult(
            wristbandId = "TEST-01",
            timestamp = "12 NOV 2024 - 10:00:00",
            dosePpmHr = 10.0
        )
        val record2 = ScanUiResult(
            wristbandId = "TEST-01",
            timestamp = "12 NOV 2024 - 14:00:00",
            dosePpmHr = 20.0
        )
        HistoryManager.saveRecord(context, record1)
        HistoryManager.saveRecord(context, record2)
        
        val loaded = HistoryManager.getRecords(context)
        assertEquals(1, loaded.size)
        assertEquals(20.0, loaded[0].dosePpmHr) // Replaced with newer
    }

    @Test
    fun testSameIdDifferentDateCreatesAnotherRecord() {
        val record1 = ScanUiResult(
            wristbandId = "TEST-01",
            timestamp = "12 NOV 2024 - 10:00:00"
        )
        val record2 = ScanUiResult(
            wristbandId = "TEST-01",
            timestamp = "13 NOV 2024 - 10:00:00"
        )
        HistoryManager.saveRecord(context, record1)
        HistoryManager.saveRecord(context, record2)
        
        val loaded = HistoryManager.getRecords(context)
        assertEquals(2, loaded.size)
    }

    @Test
    fun testDifferentIdsOnSameDateRemainSeparate() {
        val record1 = ScanUiResult(
            wristbandId = "TEST-01",
            timestamp = "12 NOV 2024 - 10:00:00"
        )
        val record2 = ScanUiResult(
            wristbandId = "TEST-02",
            timestamp = "12 NOV 2024 - 11:00:00"
        )
        HistoryManager.saveRecord(context, record1)
        HistoryManager.saveRecord(context, record2)
        
        val loaded = HistoryManager.getRecords(context)
        assertEquals(2, loaded.size)
        assertTrue(loaded.any { it.wristbandId == "TEST-01" })
        assertTrue(loaded.any { it.wristbandId == "TEST-02" })
    }

    @Test
    fun testChronologicalSorting() {
        val recordOld = ScanUiResult(
            wristbandId = "TEST-01",
            timestamp = "11 NOV 2024 - 10:00:00"
        )
        val recordNew = ScanUiResult(
            wristbandId = "TEST-02",
            timestamp = "12 NOV 2024 - 10:00:00"
        )
        HistoryManager.saveRecord(context, recordOld)
        HistoryManager.saveRecord(context, recordNew) // Saved after
        
        val loaded = HistoryManager.getRecords(context)
        assertEquals(2, loaded.size)
        // Since HistoryManager inserts at index 0 (newest first), the newest should be first
        assertEquals("TEST-02", loaded[0].wristbandId)
        assertEquals("TEST-01", loaded[1].wristbandId)
    }
}
