package com.mrpl.wristband.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

object HistoryManager {
    private const val PREFS_NAME = "exposure_history"
    private const val KEY_RECORDS = "records_json"

    fun saveRecord(context: Context, result: ScanUiResult) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val records = getRecords(context).toMutableList()

        // Exact timestamp match to prevent duplicates but allow multiple scans per day
        val existingIndex = records.indexOfFirst { 
            it.wristbandId == result.wristbandId && it.timestamp == result.timestamp
        }

        if (existingIndex >= 0) {
            records[existingIndex] = result
        } else {
            records.add(0, result) // Add to top (newest first)
        }
        
        val jsonArray = JSONArray()
        records.forEach { jsonArray.put(toJson(it)) }
        
        prefs.edit().putString(KEY_RECORDS, jsonArray.toString()).apply()
    }

    fun getRecords(context: Context): List<ScanUiResult> {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        val jsonString = prefs.getString(KEY_RECORDS, null) ?: return emptyList()
        
        val list = mutableListOf<ScanUiResult>()
        try {
            val jsonArray = JSONArray(jsonString)
            for (i in 0 until jsonArray.length()) {
                list.add(fromJson(jsonArray.getJSONObject(i)))
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
        
        if (list.isEmpty()) {
            val cal = java.util.Calendar.getInstance()
            val doses = listOf(3.5, 12.0, 24.0, 5.0, 42.0, 9.0, 15.0)
            val demoAreas = com.mrpl.wristband.data.DemoAreas.AREAS
            
            var generatedCount = 0
            var daysAgo = 1
            while (generatedCount < 7) {
                cal.time = java.util.Date()
                cal.add(java.util.Calendar.DAY_OF_YEAR, -daysAgo)
                val dayOfWeek = cal.get(java.util.Calendar.DAY_OF_WEEK)
                if (dayOfWeek != java.util.Calendar.SATURDAY && dayOfWeek != java.util.Calendar.SUNDAY) {
                    val df = java.text.SimpleDateFormat("dd MMM yyyy - 17:00:00", java.util.Locale.US)
                    list.add(ScanUiResult(
                        wristbandId = "WB-DEMO-001",
                        timestamp = df.format(cal.time),
                        dosePpmHr = doses[generatedCount],
                        twaPpm = doses[generatedCount]/8.0,
                        deltaLStar = 30.0,
                        deltaE00 = 25.0,
                        zone = demoAreas[generatedCount % demoAreas.size],
                        isMock = true
                    ))
                    generatedCount++
                }
                daysAgo++
            }
            list.sortByDescending { it.timestamp }
            val jsonArray = org.json.JSONArray()
            list.forEach { jsonArray.put(toJson(it)) }
            prefs.edit().putString(KEY_RECORDS, jsonArray.toString()).apply()
        }
        return list
    }

    private fun toJson(r: ScanUiResult): JSONObject {
        val obj = JSONObject()
        obj.put("wristbandId", r.wristbandId ?: "")
        obj.put("timestamp", r.timestamp)
        r.dosePpmHr?.let { obj.put("dosePpmHr", it) }
        r.twaPpm?.let { obj.put("twaPpm", it) }
        r.deltaLStar?.let { obj.put("deltaLStar", it) }
        r.deltaE00?.let { obj.put("deltaE00", it) }
        r.zone?.let { obj.put("zone", it) }
        obj.put("verdict", r.verdict ?: "")
        obj.put("isMock", r.isMock)
        return obj
    }

    private fun fromJson(obj: JSONObject): ScanUiResult {
        return ScanUiResult(
            wristbandId = obj.optString("wristbandId", ""),
            timestamp = obj.optString("timestamp", ""),
            dosePpmHr = if (obj.has("dosePpmHr")) obj.getDouble("dosePpmHr") else null,
            twaPpm = if (obj.has("twaPpm")) obj.getDouble("twaPpm") else null,
            deltaLStar = if (obj.has("deltaLStar")) obj.getDouble("deltaLStar") else null,
            deltaE00 = if (obj.has("deltaE00")) obj.getDouble("deltaE00") else null,
            zone = obj.optString("zone", null).takeIf { it.isNotEmpty() },
            verdict = obj.optString("verdict", null).takeIf { it.isNotEmpty() },
            isMock = obj.optBoolean("isMock", false),
            scanState = ScanState.SUCCESS
        )
    }
}
