package com.binancebot.mobile.data.remote.gson

import com.google.gson.JsonArray
import com.google.gson.JsonElement
import com.google.gson.JsonNull
import com.google.gson.JsonObject
import com.google.gson.JsonPrimitive
import com.google.gson.JsonSerializationContext
import com.google.gson.JsonSerializer
import java.lang.reflect.Type

/**
 * Gson does not always serialize [Map] values typed as [Any] reliably on all runtimes.
 * This ensures every strategy param key is written as JSON primitives (or nested JSON) so the API receives user values.
 */
class StrategyParamsMapJsonSerializer : JsonSerializer<Map<String, Any>?> {
    override fun serialize(
        src: Map<String, Any>?,
        typeOfSrc: Type,
        context: JsonSerializationContext
    ): JsonElement {
        if (src == null) return JsonNull.INSTANCE
        val obj = JsonObject()
        for ((key, value) in src) {
            obj.add(key, toJsonElement(value, context))
        }
        return obj
    }

    private fun toJsonElement(value: Any?, context: JsonSerializationContext): JsonElement {
        return when (value) {
            null -> JsonNull.INSTANCE
            is Boolean -> JsonPrimitive(value)
            is String -> JsonPrimitive(value)
            is Number -> JsonPrimitive(value)
            is Map<*, *> -> {
                val nested = JsonObject()
                @Suppress("UNCHECKED_CAST")
                val map = value as Map<String, Any?>
                for ((k, v) in map) {
                    nested.add(k, toJsonElement(v, context))
                }
                nested
            }
            is Iterable<*> -> {
                val arr = JsonArray()
                for (item in value) {
                    arr.add(toJsonElement(item, context))
                }
                arr
            }
            is Array<*> -> {
                val arr = JsonArray()
                for (item in value) {
                    arr.add(toJsonElement(item, context))
                }
                arr
            }
            else -> JsonPrimitive(value.toString())
        }
    }
}
