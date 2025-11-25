# How to View Logs

## Log File Location
```
C:\Users\teme2\Binance Bot\logs\bot.log
```

## Viewing Logs

### Method 1: View in PowerShell (Real-time)
```powershell
# View last 50 lines
Get-Content logs\bot.log -Tail 50

# Follow logs in real-time (like tail -f)
Get-Content logs\bot.log -Wait -Tail 50
```

### Method 2: View in Notepad
1. Open File Explorer
2. Navigate to: `C:\Users\teme2\Binance Bot\logs\`
3. Double-click `bot.log`
4. The file will open in Notepad

### Method 3: View in VS Code
1. Open VS Code
2. File → Open File
3. Navigate to: `C:\Users\teme2\Binance Bot\logs\bot.log`

### Method 4: View in Command Prompt
```cmd
type logs\bot.log
```

## Log Levels

- **INFO**: General information (shown in console)
- **DEBUG**: Detailed debugging info (only in file)
- **WARNING**: Warnings
- **ERROR**: Errors

## If You Don't See Logs

1. **Check if the bot is running**: Logs only appear when the bot is active
2. **Restart the bot**: Stop and start the bot to generate new logs
3. **Check the file size**: If it's 0 bytes, the bot hasn't written anything yet
4. **Refresh the file**: Close and reopen the log file to see new entries

## View Latest Logs
```powershell
# Get last 20 lines
Get-Content logs\bot.log -Tail 20

# Get all logs from today
Get-Content logs\bot.log | Select-String "2025-11-24"
```

