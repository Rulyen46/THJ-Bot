#!/usr/bin/env python
# filepath: /Users/Brandon/Desktop/Bot/azure_heartbeat.py
"""
Azure Heartbeat Module

This module provides a dedicated heartbeat mechanism for Azure App Service to prevent it from
thinking the application is frozen. It uses multiple logging approaches to ensure visibility
in Azure's log stream.

The module can be run as a standalone script or imported and used within another application.
"""

import os
import sys
import time
import logging
import asyncio
import traceback
from datetime import datetime
import threading
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [HEARTBEAT] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("azure_heartbeat")

# Constants
DEFAULT_HEARTBEAT_INTERVAL = 300  # Default heartbeat interval in seconds (5 minutes)
INITIAL_INTERVAL = 30  # Initial more frequent heartbeats (30 seconds)
NUM_INITIAL_BEATS = 5  # Number of initial more frequent heartbeats
HEARTBEAT_LOGFILE = "/app/logs/azure_heartbeat.log"

# Ensure logs directory exists
os.makedirs(os.path.dirname(HEARTBEAT_LOGFILE), exist_ok=True)


def force_azure_heartbeat_log(message):
    """Write a heartbeat log in multiple ways to ensure it gets picked up in Azure"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Create a standard log message for file
    heartbeat_msg = f"{timestamp} [AZURE_HEARTBEAT] {message}"
    
    # Create a visually distinct message for console output
    separator = "="*50
    formatted_message = f"\n{separator}\n❤️ AZURE HEARTBEAT ({timestamp})\n{message}\n{separator}\n"
    
    # Method 1: Standard logging (keep it simple for structured logging)
    logger.info(f"HEARTBEAT: {message}")
    
    # Method 2: Direct stdout write with flush - use the formatted version
    print(formatted_message, flush=True)
    
    # Method 3: Direct stderr write with flush (Azure sometimes prioritizes stderr)
    print(formatted_message, file=sys.stderr, flush=True)
    
    # Method 4: Write to dedicated heartbeat logfile - standard format for easy parsing
    try:
        with open(HEARTBEAT_LOGFILE, "a") as f:
            f.write(heartbeat_msg + "\n")
    except Exception as e:
        print(f"Error writing to heartbeat logfile: {e}", file=sys.stderr, flush=True)


async def dedicated_heartbeat_logger():
    """Log heartbeats at regular intervals"""
    startup_msg = "Starting dedicated Azure heartbeat logger"
    force_azure_heartbeat_log(startup_msg)
    
    # More frequent initial heartbeats to ensure Azure sees them quickly
    for i in range(NUM_INITIAL_BEATS):
        beat_msg = f"Initial heartbeat {i+1}/{NUM_INITIAL_BEATS} - Application is running"
        force_azure_heartbeat_log(beat_msg)
        await asyncio.sleep(INITIAL_INTERVAL)
    
    # Fetch interval from environment or use default
    interval = int(os.getenv('HEARTBEAT_INTERVAL', DEFAULT_HEARTBEAT_INTERVAL))
    interval_msg = f"Switching to regular heartbeat interval: {interval}s"
    force_azure_heartbeat_log(interval_msg)
    
    # Counter for heartbeats
    count = NUM_INITIAL_BEATS
    start_time = time.time()
    
    # Main heartbeat loop
    try:
        while True:
            count += 1
            now = datetime.now()
            uptime_seconds = int(time.time() - start_time)
            uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m {uptime_seconds % 60}s"
            
            # Build multi-line status message
            status_lines = [
                f"Heartbeat #{count}",
                f"Time: {now.strftime('%Y-%m-%d %H:%M:%S')}",
                f"Uptime: {uptime_str}"
            ]
            
            # Get system stats if available
            try:
                import psutil
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                cpu_percent = process.cpu_percent(interval=1)
                
                status_lines.extend([
                    f"Memory: {memory_mb:.1f} MB",
                    f"CPU: {cpu_percent:.1f}%",
                    f"Threads: {process.num_threads()}"
                ])
                
                # Add system-wide stats
                status_lines.extend([
                    f"System CPU: {psutil.cpu_percent(interval=0.5)}%",
                    f"System Memory: {psutil.virtual_memory().percent}%"
                ])
            except ImportError:
                status_lines.append("Memory/CPU stats unavailable (psutil not installed)")
            
            # Join all status lines and log
            status_message = "\n".join(status_lines)
            force_azure_heartbeat_log(status_message)
            
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        force_azure_heartbeat_log("Heartbeat task was cancelled")
    except Exception as e:
        error_msg = f"Error in heartbeat loop: {str(e)}"
        force_azure_heartbeat_log(error_msg)
        force_azure_heartbeat_log(traceback.format_exc())


class HeartbeatManager:
    """Manages the heartbeat task"""
    
    def __init__(self):
        self.task = None
        self.running = False
    
    async def start(self):
        """Start the heartbeat task"""
        if not self.running:
            self.running = True
            self.task = asyncio.create_task(dedicated_heartbeat_logger())
            force_azure_heartbeat_log("Heartbeat manager started")
    
    async def stop(self):
        """Stop the heartbeat task"""
        if self.running and self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.running = False
            force_azure_heartbeat_log("Heartbeat manager stopped")


# Global heartbeat manager instance
heartbeat_manager = HeartbeatManager()


def run_in_thread():
    """Run the heartbeat in a separate thread"""
    force_azure_heartbeat_log("Starting heartbeat in thread")
    
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(dedicated_heartbeat_logger())
    except Exception as e:
        force_azure_heartbeat_log(f"Error in heartbeat thread: {str(e)}")
        force_azure_heartbeat_log(traceback.format_exc())
    finally:
        loop.close()


def start_threaded_heartbeat():
    """Start the heartbeat in a background thread"""
    thread = threading.Thread(target=run_in_thread, daemon=True)
    thread.start()
    return thread


# Handle termination signals gracefully
def signal_handler(sig, frame):
    force_azure_heartbeat_log(f"Received signal {sig}, shutting down heartbeat")
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# Main function when run directly
async def main():
    """Main function when run as a script"""
    force_azure_heartbeat_log("Starting Azure heartbeat as standalone process")
    await dedicated_heartbeat_logger()


if __name__ == "__main__":
    force_azure_heartbeat_log("Azure heartbeat module started directly")
    asyncio.run(main())
