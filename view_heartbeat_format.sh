#!/bin/bash
# filepath: /Users/Brandon/Desktop/Bot/view_heartbeat_format.sh
# This script demonstrates the format of the enhanced heartbeat logs

# Generate colorful output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m' # No Color

echo -e "${BOLD}===== Enhanced Heartbeat Visualization Demo =====\n${NC}"
echo -e "This script demonstrates how the new heartbeat logs will appear in your console/logs."
echo -e "The actual logs will be visible among other application logs.\n"

# Example of standard log output
echo -e "${BLUE}Standard application logs would appear like this${NC}"
echo -e "${BLUE}2025-05-28 10:15:20 - app - INFO - Some application activity${NC}"
echo -e "${BLUE}2025-05-28 10:15:21 - app - INFO - Processing user request${NC}"
echo -e "${BLUE}2025-05-28 10:15:22 - app - INFO - Database query complete${NC}\n"

# Enhanced heartbeat visualization
echo -e "===================================================="
echo -e "❤️ ${GREEN}AZURE HEARTBEAT (2025-05-28 10:15:25)${NC}"
echo -e "Heartbeat #12"
echo -e "Time: 2025-05-28 10:15:25"
echo -e "Uptime: 1h 23m 45s"
echo -e "Memory: 156.2 MB"
echo -e "CPU: 2.3%"
echo -e "Threads: 8"
echo -e "System CPU: 15.7%"
echo -e "System Memory: 62.4%"
echo -e "===================================================="

echo -e "\n${BLUE}2025-05-28 10:15:26 - app - INFO - More application logs...${NC}"
echo -e "${BLUE}2025-05-28 10:15:28 - app - INFO - Processing another request${NC}\n"

# Discord heartbeat
echo -e "===================================================="
echo -e "💓 ${YELLOW}HEARTBEAT (2025-05-28 10:15:30)${NC}"
echo -e "Discord health check #8"
echo -e "Time: 2025-05-28 10:15:30"
echo -e "Bot: THJ-Bot (ID: 123456789012345678)"
echo -e "Connection: Active, latency: 42.15ms"
echo -e "Interval: 300s"
echo -e "Monitoring changelog channel: #changelog"
echo -e "Monitoring EXP boost channel: #exp-boost-30"
echo -e "===================================================="

echo -e "\n${BLUE}2025-05-28 10:15:35 - app - INFO - Processing complete${NC}"
echo -e "${BLUE}2025-05-28 10:15:37 - app - WARNING - Rate limit approaching${NC}\n"

echo -e "${BOLD}===== End of Visualization =====\n${NC}"
echo -e "Benefits of the new format:"
echo -e "  1. ${GREEN}Visual separation${NC} makes heartbeats stand out"
echo -e "  2. ${GREEN}Multi-line format${NC} provides more context at a glance"
echo -e "  3. ${GREEN}Heart emoji (💓/❤️)${NC} makes it instantly recognizable"
echo -e "  4. ${GREEN}Useful system stats${NC} for quick diagnostics"
echo ""
echo -e "To see real heartbeats, run: ./run_heartbeat_test.sh"
