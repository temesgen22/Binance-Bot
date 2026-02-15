package com.binancebot.mobile.domain.repository

import com.binancebot.mobile.data.remote.dto.CreatePriceAlertRequest
import com.binancebot.mobile.data.remote.dto.PriceAlertDto
import com.binancebot.mobile.data.remote.dto.UpdatePriceAlertRequest

interface PriceAlertsRepository {
    suspend fun getPriceAlerts(enabled: Boolean? = null): Result<List<PriceAlertDto>>
    suspend fun getPriceAlert(id: String): Result<PriceAlertDto>
    suspend fun createPriceAlert(request: CreatePriceAlertRequest): Result<PriceAlertDto>
    suspend fun updatePriceAlert(id: String, request: UpdatePriceAlertRequest): Result<PriceAlertDto>
    suspend fun deletePriceAlert(id: String): Result<Unit>
}
