#!/usr/bin/env python
"""
Azure Logging Force Script

This script helps ensure logs are visible in Azure by periodically forcing log output
through multiple channels. It runs independently and complements other services.
"""

import os
import sys
import time
import logging
import threading
import signal
from datetime import datetime
import requests
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [AZURE_LOGGER] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("azure_logger")

# Constants
CHECK_INTERVAL = 60  # Check every minute
API_ENDPOINTS = [
    "/health",
    "/heartbeat",
    "/changelog",
    "/serverstatus"  
]

def force_log(message, level="INFO", use_separator=True):
    """Force log output through multiple channels"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"{timestamp} [AZURE_LOGGER] {level}: {message}"
    
    # Log through standard logger
    if level == "INFO":
        logger.info(message)
    elif level == "WARNING":
        logger.warning(message)
    elif level == "ERROR":
        logger.error(message)
    elif level == "CRITICAL":
        logger.critical(message)
    
    # Format for console
    if use_separator:
        separator = "-" * 80
        formatted_message = f"\n{separator}\n{log_message}\n{separator}\n"
    else:
        formatted_message = log_message
    
    # Print directly to stderr and stdout
    print(formatted_message, flush=True)
    print(formatted_message, file=sys.stderr, flush=True)
    
    # Write to dedicated log file
    log_dir = "/app/logs"
    os.makedirs(log_dir, exist_ok=True)
    with open(f"{log_dir}/azure_forced_logs.log", "a") as f:
        f.write(f"{log_message}\n")

def check_api_endpoints():
    """Check API endpoints and log responses"""
    base_url = f"http://localhost:{os.getenv('PORT', '80')}"
    
    for endpoint in API_ENDPOINTS:
        try:
            # Log the attempt
            force_log(f"Checking API endpoint: {endpoint}", "INFO", False)
            
            # Make the request
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            
            # Log the response
            status = response.status_code
            force_log(
                f"API endpoint {endpoint}: Status {status} - Response size: {len(response.content)} bytes", 
                "INFO" if status == 200 else "WARNING"
            )
            
        except Exception as e:
            force_log(f"Error checking {endpoint}: {str(e)}", "ERROR")

def log_system_info():
    """Log system information"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent(interval=1)
        disk = psutil.disk_usage('/')
        
        info = [
            f"System Memory: {memory.percent}% used ({memory.used / (1024**3):.1f}GB/{memory.total / (1024**3):.1f}GB)",
            f"CPU Usage: {cpu_percent}%",
            f"Disk Usage: {disk.percent}% used ({disk.used / (1024**3):.1f}GB/{disk.total / (1024**3):.1f}GB)",
            f"Process Count: {len(psutil.pids())}"
        ]
        
        force_log("System Information:\n" + "\n".join(info))
    except ImportError:
        force_log("Cannot collect system information: psutil not available", "WARNING")
    except Exception as e:
        force_log(f"Error collecting system information: {str(e)}", "ERROR")

def main_loop():
    """Main monitoring loop"""
    force_log("Starting Azure Logger forcing utility", "INFO")
    
    count = 0
    while True:
        try:
            count += 1
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Log a standard heartbeat
            force_log(f"Logger heartbeat #{count} at {current_time}")
            
            # Every 5 cycles, log system info
            if count % 5 == 0:
                log_system_info()
                
            # Check API endpoints
            check_api_endpoints()
                
            # Sleep until next check
            time.sleep(CHECK_INTERVAL)
            
        except KeyboardInterrupt:
            force_log("Logger stopped by user", "WARNING")
            break
        except Exception as e:
            force_log(f"Error in main loop: {str(e)}", "ERROR")
            force_log(traceback.format_exc(), "ERROR")
            # Brief pause before continuing
            time.sleep(5)

def signal_handler(sig, frame):
    """Handle termination signals"""
    force_log(f"Received signal {sig}, shutting down logger", "WARNING")
    sys.exit(0)

if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run in the main thread
    force_log("Azure Logging Force utility started", "INFO")
    main_loop()
