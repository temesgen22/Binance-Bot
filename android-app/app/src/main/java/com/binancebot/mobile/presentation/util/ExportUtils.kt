package com.binancebot.mobile.presentation.util

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import androidx.core.content.FileProvider
import com.binancebot.mobile.data.remote.dto.LogEntryDto
import com.binancebot.mobile.data.remote.dto.TradingReportDto
import java.io.File
import java.io.FileWriter
import java.text.SimpleDateFormat
import java.util.*

/**
 * Utility functions for exporting data to files and sharing
 */
object ExportUtils {
    
    /**
     * Export trading report to CSV format
     */
    fun exportReportToCsv(
        context: Context,
        report: TradingReportDto,
        fileName: String = "trading_report_${System.currentTimeMillis()}.csv"
    ): Uri? {
        return try {
            val file = File(context.getExternalFilesDir(null), fileName)
            FileWriter(file).use { writer ->
                // Write header with more columns
                writer.append("Strategy ID,Strategy Name,Symbol,Type,Total Trades,Wins,Losses,Win Rate (%),Total Profit,Total Loss,Net PnL,Profit Factor,Trading Fees,Funding Fees\n")
                
                // Write strategy summaries
                report.strategies.forEach { strategyReport ->
                    writer.append("${strategyReport.strategyId},")
                    writer.append("\"${strategyReport.strategyName}\",")
                    writer.append("${strategyReport.symbol},")
                    writer.append("\"${strategyReport.strategyType ?: ""}\",")
                    writer.append("${strategyReport.totalTrades},")
                    writer.append("${strategyReport.wins},")
                    writer.append("${strategyReport.losses},")
                    // Backend returns 0-100, format correctly
                    val winRatePct = if (strategyReport.winRate > 1.0) strategyReport.winRate else strategyReport.winRate * 100
                    writer.append("${String.format("%.2f", winRatePct)},")
                    writer.append("${strategyReport.totalProfitUsd},")
                    writer.append("${strategyReport.totalLossUsd},")
                    writer.append("${strategyReport.netPnl},")
                    val profitFactor = if (strategyReport.totalLossUsd != 0.0) {
                        strategyReport.totalProfitUsd / kotlin.math.abs(strategyReport.totalLossUsd)
                    } else if (strategyReport.totalProfitUsd > 0) Double.MAX_VALUE else 0.0
                    writer.append("${if (profitFactor == Double.MAX_VALUE) "Infinity" else String.format("%.4f", profitFactor)},")
                    writer.append("${strategyReport.totalFee},")
                    writer.append("${strategyReport.totalFundingFee}\n")
                }
                
                // Add summary row
                writer.append("\n")
                writer.append("TOTAL,,,")
                writer.append(",${report.totalTrades}")
                val totalWins = report.strategies.sumOf { it.wins }
                val totalLosses = report.strategies.sumOf { it.losses }
                writer.append(",${totalWins},${totalLosses}")
                val overallWinRate = if (report.overallWinRate > 1.0) report.overallWinRate else report.overallWinRate * 100
                writer.append(",${String.format("%.2f", overallWinRate)}")
                val totalProfit = report.strategies.sumOf { it.totalProfitUsd }
                val totalLoss = report.strategies.sumOf { it.totalLossUsd }
                writer.append(",${totalProfit},${totalLoss}")
                writer.append(",${report.overallNetPnl}")
                writer.append(",")  // Skip profit factor for total
                val totalFees = report.strategies.sumOf { it.totalFee }
                val totalFundingFees = report.strategies.sumOf { it.totalFundingFee }
                writer.append(",${totalFees},${totalFundingFees}\n")
            }
            
            getUriForFile(context, file)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }
    
    /**
     * Export trading report to JSON format
     */
    fun exportReportToJson(
        context: Context,
        report: TradingReportDto,
        fileName: String = "trading_report_${System.currentTimeMillis()}.json"
    ): Uri? {
        return try {
            val file = File(context.getExternalFilesDir(null), fileName)
            FileWriter(file).use { writer ->
                // Simple JSON serialization (for production, use Gson)
                writer.append("{\n")
                writer.append("  \"totalStrategies\": ${report.totalStrategies},\n")
                writer.append("  \"totalTrades\": ${report.totalTrades},\n")
                writer.append("  \"totalPnL\": ${report.overallNetPnl},\n")
                writer.append("  \"strategies\": [\n")
                report.strategies.forEachIndexed { index, strategyReport ->
                    if (index > 0) writer.append(",\n")
                    writer.append("    {\n")
                    writer.append("      \"strategyId\": \"${strategyReport.strategyId}\",\n")
                    writer.append("      \"strategyName\": \"${strategyReport.strategyName}\",\n")
                    writer.append("      \"symbol\": \"${strategyReport.symbol}\",\n")
                    writer.append("      \"totalTrades\": ${strategyReport.totalTrades},\n")
                    writer.append("      \"winRate\": ${strategyReport.winRate},\n")
                    writer.append("      \"totalPnL\": ${strategyReport.netPnl}\n")
                    writer.append("    }")
                }
                writer.append("\n  ]\n")
                writer.append("}\n")
            }
            
            getUriForFile(context, file)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }
    
    /**
     * Export logs to text file
     */
    fun exportLogsToText(
        context: Context,
        logs: List<LogEntryDto>,
        fileName: String = "logs_${System.currentTimeMillis()}.txt"
    ): Uri? {
        return try {
            val file = File(context.getExternalFilesDir(null), fileName)
            FileWriter(file).use { writer ->
                logs.forEach { logEntry ->
                    writer.append("[${logEntry.timestamp ?: "N/A"}] ")
                    writer.append("[${logEntry.level ?: "UNKNOWN"}] ")
                    logEntry.symbol?.let { writer.append("[$it] ") }
                    writer.append("${logEntry.message ?: ""}\n")
                }
            }
            
            getUriForFile(context, file)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }
    
    /**
     * Export logs to CSV format
     */
    fun exportLogsToCsv(
        context: Context,
        logs: List<LogEntryDto>,
        fileName: String = "logs_${System.currentTimeMillis()}.csv"
    ): Uri? {
        return try {
            val file = File(context.getExternalFilesDir(null), fileName)
            FileWriter(file).use { writer ->
                // Write header
                writer.append("Timestamp,Level,Symbol,Message\n")
                
                // Write log entries
                logs.forEach { logEntry ->
                    writer.append("${logEntry.timestamp ?: "N/A"},")
                    writer.append("${logEntry.level ?: "UNKNOWN"},")
                    writer.append("\"${logEntry.symbol ?: ""}\",")
                    writer.append("\"${(logEntry.message ?: "").replace("\"", "\"\"")}\"\n")
                }
            }
            
            getUriForFile(context, file)
        } catch (e: Exception) {
            e.printStackTrace()
            null
        }
    }
    
    /**
     * Share file using Android's share intent
     */
    fun shareFile(context: Context, uri: Uri, mimeType: String = "text/plain", title: String = "Share File") {
        val shareIntent = Intent().apply {
            action = Intent.ACTION_SEND
            putExtra(Intent.EXTRA_STREAM, uri)
            type = mimeType
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        }
        
        context.startActivity(Intent.createChooser(shareIntent, title))
    }
    
    /**
     * Share text content directly
     */
    fun shareText(context: Context, text: String, title: String = "Share") {
        val shareIntent = Intent().apply {
            action = Intent.ACTION_SEND
            putExtra(Intent.EXTRA_TEXT, text)
            type = "text/plain"
        }
        
        context.startActivity(Intent.createChooser(shareIntent, title))
    }
    
    /**
     * Get URI for file using FileProvider
     */
    private fun getUriForFile(context: Context, file: File): Uri {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
            FileProvider.getUriForFile(
                context,
                "${context.packageName}.fileprovider",
                file
            )
        } else {
            Uri.fromFile(file)
        }
    }
    
    /**
     * Helper to format win rate correctly.
     * Backend returns 0-100 (e.g., 65.5 for 65.5%), not 0-1.
     */
    private fun formatWinRate(winRate: Double): String {
        // If value > 1, it's already a percentage; otherwise convert
        val percentage = if (winRate > 1.0) winRate else winRate * 100
        return String.format("%.1f%%", percentage)
    }
    
    /**
     * Format trading report as shareable text
     */
    fun formatReportAsText(report: TradingReportDto): String {
        val sb = StringBuilder()
        sb.append("Trading Report\n")
        sb.append("=============\n\n")
        
        // Overall Summary
        sb.append("Overall Summary\n")
        sb.append("Total Strategies: ${report.totalStrategies}\n")
        sb.append("Total Trades: ${report.totalTrades}\n")
        sb.append("Overall Win Rate: ${formatWinRate(report.overallWinRate)}\n")
        sb.append("Net PnL: ${FormatUtils.formatCurrency(report.overallNetPnl)}\n\n")
        
        sb.append("Strategy Details:\n")
        sb.append("----------------\n")
        report.strategies.forEach { strategyReport ->
            sb.append("\n${strategyReport.strategyName} (${strategyReport.symbol})\n")
            sb.append("  Trades: ${strategyReport.totalTrades} (W: ${strategyReport.wins} / L: ${strategyReport.losses})\n")
            sb.append("  Win Rate: ${formatWinRate(strategyReport.winRate)}\n")
            sb.append("  Profit: ${FormatUtils.formatCurrency(strategyReport.totalProfitUsd)}\n")
            sb.append("  Loss: ${FormatUtils.formatCurrency(strategyReport.totalLossUsd)}\n")
            sb.append("  Net PnL: ${FormatUtils.formatCurrency(strategyReport.netPnl)}\n")
            val profitFactor = if (strategyReport.totalLossUsd != 0.0) {
                strategyReport.totalProfitUsd / kotlin.math.abs(strategyReport.totalLossUsd)
            } else if (strategyReport.totalProfitUsd > 0) Double.POSITIVE_INFINITY else 0.0
            sb.append("  Profit Factor: ${if (profitFactor.isInfinite()) "∞" else String.format("%.2f", profitFactor)}\n")
            if (strategyReport.totalFee > 0) {
                sb.append("  Trading Fees: ${FormatUtils.formatCurrency(strategyReport.totalFee)}\n")
            }
            if (strategyReport.totalFundingFee != 0.0) {
                sb.append("  Funding Fees: ${FormatUtils.formatCurrency(strategyReport.totalFundingFee)}\n")
            }
        }
        
        sb.append("\nGenerated: ${report.reportGeneratedAt}\n")
        
        return sb.toString()
    }
}

