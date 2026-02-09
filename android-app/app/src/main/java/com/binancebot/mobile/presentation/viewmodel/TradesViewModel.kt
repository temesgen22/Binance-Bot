package com.binancebot.mobile.presentation.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.paging.PagingData
import androidx.paging.cachedIn
import com.binancebot.mobile.domain.model.Trade
import com.binancebot.mobile.domain.repository.TradeRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.flatMapLatest
import javax.inject.Inject

@HiltViewModel
class TradesViewModel @Inject constructor(
    private val tradeRepository: TradeRepository
) : ViewModel() {
    
    private val _strategyId = MutableStateFlow<String?>(null)
    private val _symbol = MutableStateFlow<String?>(null)
    private val _dateFrom = MutableStateFlow<String?>(null)
    private val _dateTo = MutableStateFlow<String?>(null)
    
    // Recreate Flow when filters change
    val trades: Flow<PagingData<Trade>> = kotlinx.coroutines.flow.combine(
        _strategyId,
        _symbol,
        _dateFrom,
        _dateTo
    ) { strategyId, symbol, dateFrom, dateTo ->
        Pair(Pair(strategyId, symbol), Pair(dateFrom, dateTo))
    }.flatMapLatest { (filters, dates) ->
        tradeRepository.getTrades(
            strategyId = filters.first,
            symbol = filters.second,
            dateFrom = dates.first,
            dateTo = dates.second
        )
    }.cachedIn(viewModelScope)
    
    fun setFilters(
        strategyId: String? = null, 
        symbol: String? = null,
        dateFrom: String? = null,
        dateTo: String? = null
    ) {
        _strategyId.value = strategyId
        _symbol.value = symbol
        _dateFrom.value = dateFrom
        _dateTo.value = dateTo
    }
}

sealed class TradesUiState {
    object Idle : TradesUiState()
    object Loading : TradesUiState()
    object Success : TradesUiState()
    data class Error(val message: String) : TradesUiState()
}
