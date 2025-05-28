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
import aiohttp  # For API health checks

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
DEFAULT_HEARTBEAT_INTERVAL = 90  # Default heartbeat interval in seconds (1.5 minutes)
INITIAL_INTERVAL = 30  # Initial more frequent heartbeats (30 seconds)
NUM_INITIAL_BEATS = 5  # Number of initial more frequent heartbeats
HEARTBEAT_LOGFILE = "/app/logs/azure_heartbeat.log"
# More frequent logging to ensure visibility in Azure

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
    
    # Always do the standard logging first (never throttled)
    logger.info(f"HEARTBEAT: {message}")
    
    # ALWAYS print to stdout and stderr for Azure visibility (no throttling for Azure)
    # Azure App Service sometimes has issues with buffered output
    print(formatted_message, flush=True)
    print(formatted_message, file=sys.stderr, flush=True)
    
    # For non-essential logging (file writes), we can throttle
    current_time = int(time.time())
    message_hash = hash(message[:20])  # Use first 20 chars to identify similar messages
    
    # Throttle file-based logging to prevent excessive I/O
    if not hasattr(force_azure_heartbeat_log, 'recent_logs'):
        force_azure_heartbeat_log.recent_logs = {}
    
    # Check if we've recently written this same message to file
    recently_logged = False
    if message_hash in force_azure_heartbeat_log.recent_logs:
        last_time = force_azure_heartbeat_log.recent_logs[message_hash]
        if current_time - last_time < 60:  # Within last minute
            recently_logged = True
    
    # Update the timestamp for this message hash
    force_azure_heartbeat_log.recent_logs[message_hash] = current_time
    
    # Only write to file if not recently logged (throttle file I/O)
    if not recently_logged:
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
    
    # Check for other services and log their status
    force_azure_heartbeat_log("Checking companion services...")
    
    # Check if FastAPI process is running
    try:
        api_health_status = "Unknown"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('http://localhost/health', timeout=2) as resp:
                    if resp.status == 200:
                        api_health_status = "Healthy"
                        api_data = await resp.json()
                        force_azure_heartbeat_log(f"FastAPI service is running: {api_data}")
                    else:
                        api_health_status = f"Unhealthy (Status: {resp.status})"
        except Exception as e:
            api_health_status = f"Not responding ({str(e)})"
        
        force_azure_heartbeat_log(f"API Status: {api_health_status}")
    except Exception as e:
        force_azure_heartbeat_log(f"Error checking API: {str(e)}")
    
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
            
            # Check API every 5th heartbeat
            if count % 5 == 0:
                try:
                    async with aiohttp.ClientSession() as session:
                        try:
                            async with session.get('http://localhost/health', timeout=2) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    force_azure_heartbeat_log(f"API health check: Healthy - {data}")
                                else:
                                    force_azure_heartbeat_log(f"API health check: Unhealthy - Status {resp.status}")
                        except Exception as e:
                            force_azure_heartbeat_log(f"API health check failed: {str(e)}")
                except Exception as e:
                    force_azure_heartbeat_log(f"Could not perform API check: {str(e)}")
            
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
