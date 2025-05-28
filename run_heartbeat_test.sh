#!/bin/bash
# filepath: /Users/Brandon/Desktop/Bot/run_heartbeat_test.sh

# This script starts the dedicated heartbeat process for testing

echo "===== Heartbeat System Test ====="
echo "Starting dedicated Azure heartbeat process..."

# Check if azure_heartbeat.py exists
if [ -f "azure_heartbeat.py" ]; then
    # Make sure it's executable
    chmod +x azure_heartbeat.py
    
    # Run the Azure heartbeat in the background
    python azure_heartbeat.py &
    HEARTBEAT_PID=$!
    echo "✅ Azure heartbeat process started with PID: $HEARTBEAT_PID"
    
    # Let it run for a bit to see the initial heartbeats
    echo "Waiting for initial heartbeats (10 seconds)..."
    sleep 10
    
    # View logs if they exist
    if [ -d "logs" ] && [ -f "logs/azure_heartbeat.log" ]; then
        echo -e "\n===== Recent Heartbeat Logs ====="
        tail -n 10 logs/azure_heartbeat.log
    fi
    
    # Tell user how to stop it
    echo -e "\n✅ Heartbeat system is running!"
    echo "Press Ctrl+C to stop the test"
    echo "The process will continue running until stopped"
    echo "To stop it later, run: kill $HEARTBEAT_PID"
    
    # Wait for user to press Ctrl+C
    wait $HEARTBEAT_PID
else
    echo "❌ Error: azure_heartbeat.py not found"
    exit 1
fi
