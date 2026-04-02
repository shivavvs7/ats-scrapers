#!/bin/bash
# Monitor continuous discovery progress

echo "========================================"
echo "Continuous Discovery Monitor"
echo "========================================"
echo ""

# Check if process is running
if pgrep -f "continuous_discovery.py" > /dev/null; then
    PID=$(pgrep -f "continuous_discovery.py")
    echo "✅ Discovery is RUNNING (PID: $PID)"
    echo ""
    
    # Show recent log entries
    echo "📊 Recent Activity (last 20 lines):"
    echo "----------------------------------------"
    tail -20 continuous_discovery.log 2>/dev/null || echo "No log file yet"
    echo ""
    
    # Show current CSV stats
    echo "📈 Current Dataset Sizes:"
    echo "----------------------------------------"
    wc -l */\*_companies.csv 2>/dev/null | tail -9
    echo ""
    
    # Show log file location
    echo "📁 Log Files:"
    echo "----------------------------------------"
    ls -lh logs/*.log 2>/dev/null | tail -5 || echo "No log files yet"
    
else
    echo "❌ Discovery is NOT running"
    echo ""
    echo "Last 30 lines of log:"
    echo "----------------------------------------"
    tail -30 continuous_discovery.log 2>/dev/null || echo "No log file found"
fi

echo ""
echo "========================================"
echo "Commands:"
echo "  Stop:    pkill -f continuous_discovery.py"
echo "  Logs:    tail -f continuous_discovery.log"
echo "  Monitor: watch -n 10 ./monitor_discovery.sh"
echo "========================================"
