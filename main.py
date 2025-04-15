import asyncio
import os
import logging
import importlib.util
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

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
            await api_module.start_api()
        else:
            logger.error("Patcher_API.py does not have expected 'start_api' function")
    except Exception as e:
        logger.error(f"Failed to start Patcher API: {e}")
        raise

async def main():
    """Main entry point to run both services concurrently"""
    logger.info("Starting services...")
    
    # Since Patcher_API already starts its own Discord client,
    # we don't need to start the Discord.py client separately
    # Just run the Patcher_API
    try:
        await run_api_server()
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logger.info("Application starting...")
    asyncio.run(main())