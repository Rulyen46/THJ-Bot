import asyncio
import os
import logging
import importlib.util
import sys
import time
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Log important diagnostics at startup
logger.info("=== Application Diagnostics ===")
logger.info(f"Python version: {sys.version}")
logger.info(f"Current working directory: {os.getcwd()}")
logger.info(f"Directory contents: {os.listdir('.')}")
logger.info(f"PORT environment variable: {os.getenv('PORT', '80')}")

async def run_discord_bot():
    """Import and run the Discord bot"""
    logger.info("Starting Discord bot...")
    
    # Dynamically import the Discord module
    try:
        spec = importlib.util.spec_from_file_location("Discord", "Discord.py")
        discord_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(discord_module)
        
        # If Discord.py has a client.run() call in __main__, it will block
        # So we need to access its client and run it properly in async context
        if hasattr(discord_module, 'client'):
            from dotenv import load_dotenv
            load_dotenv()
            TOKEN = os.getenv('DISCORD_TOKEN')
            logger.info(f"Discord token found: {'Yes' if TOKEN else 'No'}")
            await discord_module.client.start(TOKEN)
        else:
            logger.error("Discord.py does not expose a 'client' object")
    except Exception as e:
        logger.error(f"Failed to start Discord bot: {e}")
        raise

async def run_api_server():
    """Import and run the Patcher API"""
    logger.info("Starting Patcher API...")
    
    # Dynamically import the Patcher_API module
    try:
        spec = importlib.util.spec_from_file_location("Patcher_API", "Patcher_API.py")
        api_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api_module)
        
        # If Patcher_API.py has the start functions as we expect
        if hasattr(api_module, 'start_api'):
            # Patcher_API already has its own Discord client - we'll use that one
            logger.info(f"Starting API with PORT={os.getenv('PORT', '80')}")
            await api_module.start_api()
        else:
            logger.error("Patcher_API.py does not have expected 'start_api' function")
    except Exception as e:
        logger.error(f"Failed to start Patcher API: {e}")
        raise

async def start_dedicated_heartbeat():
    """Start the dedicated Azure heartbeat logger as a separate process"""
    logger.info("Starting dedicated Azure heartbeat logger...")
    print("AZURE_STARTUP: Starting dedicated Azure heartbeat logger process")
    sys.stdout.flush()
    
    try:
        # First, check if the dedicated heartbeat script exists
        if os.path.exists('azure_heartbeat.py'):
            # Import and use the heartbeat module directly
            try:
                import azure_heartbeat
                # Start heartbeat in a separate thread
                heartbeat_thread = azure_heartbeat.start_threaded_heartbeat()
                
                logger.info("Started dedicated Azure heartbeat thread")
                print("AZURE_STARTUP: Started dedicated heartbeat thread")
                sys.stdout.flush()
                
                return True
            except Exception as e:
                logger.error(f"Error starting heartbeat module: {e}")
                print(f"AZURE_STARTUP ERROR: Failed to start heartbeat module: {e}")
                
                # Fallback to subprocess method if module import fails
                import subprocess
                process = subprocess.Popen(
                    ['python', 'azure_heartbeat.py'],
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )
                
                logger.info(f"Started fallback heartbeat process with PID: {process.pid}")
                print(f"AZURE_STARTUP: Started fallback heartbeat process with PID: {process.pid}")
                sys.stdout.flush()
                
                return True
        else:
            logger.warning("Dedicated Azure heartbeat script not found")
            print("AZURE_STARTUP WARNING: azure_heartbeat.py not found!")
            return False
            
    except Exception as e:
        logger.error(f"Error starting Azure heartbeat logger: {e}")
        print(f"AZURE_STARTUP ERROR: Failed to start dedicated heartbeat: {e}")
        sys.stdout.flush()
        return False

async def main():
    """Main entry point to run both services concurrently"""
    logger.info("Starting services...")
    print("AZURE_STARTUP: Starting all services...")
    sys.stdout.flush()
    
    # Start the dedicated Azure heartbeat logger
    heartbeat_started = await start_dedicated_heartbeat()
    
    # Print Azure heartbeat info whether it started or not
    if heartbeat_started:
        print("AZURE_STARTUP: Dedicated heartbeat logger is running")
    else:
        print("AZURE_STARTUP: Dedicated heartbeat logger failed to start - using only internal heartbeats")
    sys.stdout.flush()
    
    # Run both the Discord bot and Patcher API as separate services
    try:
        # Start both services concurrently
        discord_task = asyncio.create_task(run_discord_bot())
        api_task = asyncio.create_task(run_api_server())
        
        # Log that tasks are created
        print("AZURE_STARTUP: Created async tasks for discord_bot and api_server")
        sys.stdout.flush()
        
        # Wait for both to complete (they should run indefinitely)
        await asyncio.gather(discord_task, api_task)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        print(f"AZURE ERROR: Error in main process: {e}")
        sys.stdout.flush()
        sys.exit(1)

if __name__ == "__main__":
    logger.info("Application starting...")
    asyncio.run(main())