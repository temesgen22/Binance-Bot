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
                // Write header
                writer.append("Strategy ID,Strategy Name,Symbol,Total Trades,Win Rate,Total PnL,Profit Factor\n")
                
                // Write strategy summaries
                report.strategies.forEach { strategyReport ->
                    writer.append("${strategyReport.strategyId},")
                    writer.append("\"${strategyReport.strategyName}\",")
                    writer.append("${strategyReport.symbol},")
                    writer.append("${strategyReport.totalTrades},")
                    writer.append("${strategyReport.winRate},")
                    writer.append("${strategyReport.netPnl},")
                    val profitFactor = if (strategyReport.totalLossUsd != 0.0) {
                        strategyReport.totalProfitUsd / strategyReport.totalLossUsd
                    } else 0.0
                    writer.append("${profitFactor}\n")
                }
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
     * Format trading report as shareable text
     */
    fun formatReportAsText(report: TradingReportDto): String {
        val sb = StringBuilder()
        sb.append("Trading Report\n")
        sb.append("=============\n\n")
        sb.append("Total Strategies: ${report.totalStrategies}\n")
        sb.append("Total Trades: ${report.totalTrades}\n")
        sb.append("Total PnL: ${FormatUtils.formatCurrency(report.overallNetPnl)}\n\n")
        
        sb.append("Strategy Details:\n")
        sb.append("----------------\n")
        report.strategies.forEach { strategyReport ->
            sb.append("\nStrategy: ${strategyReport.strategyName}\n")
            sb.append("  Symbol: ${strategyReport.symbol}\n")
            sb.append("  Total Trades: ${strategyReport.totalTrades}\n")
            sb.append("  Win Rate: ${String.format("%.2f%%", strategyReport.winRate * 100)}\n")
            sb.append("  Total PnL: ${FormatUtils.formatCurrency(strategyReport.netPnl)}\n")
            val profitFactor = if (strategyReport.totalLossUsd != 0.0) {
                strategyReport.totalProfitUsd / strategyReport.totalLossUsd
            } else 0.0
            sb.append("  Profit Factor: ${String.format("%.2f", profitFactor)}\n")
        }
        
        return sb.toString()
    }
}

