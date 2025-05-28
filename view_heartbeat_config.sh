#!/bin/bash
# Script to view current heartbeat configuration

echo "=== Current Heartbeat Configuration ==="
echo ""
echo "Discord.py heartbeat settings:"
grep -n "HEALTH_CHECK_INTERVAL\s*=\s*[0-9]*" /Users/Brandon/Desktop/Bot/Discord.py | head -1
grep -n "HEARTBEAT_INITIAL_INTERVAL\s*=\s*[0-9]*" /Users/Brandon/Desktop/Bot/Discord.py | head -1
echo ""
echo "azure_heartbeat.py heartbeat settings:"
grep -n "DEFAULT_HEARTBEAT_INTERVAL\s*=\s*[0-9]*" /Users/Brandon/Desktop/Bot/azure_heartbeat.py | head -1
grep -n "INITIAL_INTERVAL\s*=\s*[0-9]*" /Users/Brandon/Desktop/Bot/azure_heartbeat.py | head -1
grep -n "NUM_INITIAL_BEATS\s*=\s*[0-9]*" /Users/Brandon/Desktop/Bot/azure_heartbeat.py | head -1
echo ""
echo "Heartbeat task creation in on_ready event:"
grep -A 2 -B 2 "create_task(health_check" /Users/Brandon/Desktop/Bot/Discord.py

echo ""
echo "If both services are configured correctly:"
echo "1. The Azure heartbeat will run every 3 minutes (after initial startup)"
echo "2. The Discord heartbeat will run every 2 minutes (after initial startup)"
echo "3. Initial beats will be more frequent (30-45 seconds)"
echo "4. Heartbeats should be staggered to avoid log overlap"
echo ""
echo "This configuration provides redundancy while preventing excessive logging."
