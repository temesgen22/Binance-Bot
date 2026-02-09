package com.binancebot.mobile.data.remote.paging

import androidx.paging.PagingSource
import androidx.paging.PagingState
import com.binancebot.mobile.data.remote.api.BinanceBotApi
import com.binancebot.mobile.data.remote.dto.LogEntryDto
import com.binancebot.mobile.domain.model.LogEntry

/**
 * Paging 3 source for Logs.
 * ✅ CRITICAL FIX: Implements Paging 3 for efficient log pagination.
 */
class LogPagingSource(
    private val api: BinanceBotApi,
    private val filters: LogFilters
) : PagingSource<Int, LogEntry>() {
    
    override suspend fun load(params: LoadParams<Int>): LoadResult<Int, LogEntry> {
        return try {
            val page = params.key ?: 0
            val pageSize = params.loadSize
            
            val response = api.getLogs(
                symbol = filters.symbol,
                level = filters.level,
                dateFrom = filters.startDate,
                dateTo = filters.endDate,
                searchText = filters.search,
                limit = pageSize,
                offset = page * pageSize,
                reverse = true
            )
            
            if (response.isSuccessful) {
                val logs = response.body()?.entries?.map { dto ->
                    dto.toDomain()
                } ?: emptyList()
                
                LoadResult.Page(
                    data = logs,
                    prevKey = if (page == 0) null else page - 1,
                    nextKey = if (logs.size < pageSize) null else page + 1
                )
            } else {
                LoadResult.Error(Exception("API error: ${response.code()}"))
            }
        } catch (e: Exception) {
            LoadResult.Error(e)
        }
    }
    
    override fun getRefreshKey(state: PagingState<Int, LogEntry>): Int? {
        return state.anchorPosition?.let { anchorPosition ->
            val anchorPage = state.closestPageToPosition(anchorPosition)
            anchorPage?.prevKey?.plus(1) ?: anchorPage?.nextKey?.minus(1)
        }
    }
}

/**
 * Log filters for pagination
 */
data class LogFilters(
    val symbol: String? = null,
    val level: String? = null,
    val startDate: String? = null,
    val endDate: String? = null,
    val search: String? = null
)

// Extension to convert DTO to domain
private fun LogEntryDto.toDomain(): LogEntry {
    return LogEntry(
        id = id,
        timestamp = try {
            java.time.Instant.parse(timestamp).toEpochMilli()
        } catch (e: Exception) {
            System.currentTimeMillis()
        },
        level = level,
        message = message,
        symbol = symbol
    )
}

