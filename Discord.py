import os
import discord
from dotenv import load_dotenv
import logging
import json
from datetime import datetime
import asyncio
import re
import traceback
import aiohttp
import importlib.util

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANGELOG_CHANNEL_ID = int(os.getenv('CHANGELOG_CHANNEL_ID'))
EXP_BOOST_CHANNEL_ID = os.getenv('EXP_BOOST_CHANNEL_ID')

# Convert EXP_BOOST_CHANNEL_ID to int if it exists
if EXP_BOOST_CHANNEL_ID:
    EXP_BOOST_CHANNEL_ID = int(EXP_BOOST_CHANNEL_ID)
else:
    logging.warning("EXP_BOOST_CHANNEL_ID not set - exp boost functionality will be disabled")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/discord_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Define the paths to the files
CHANGELOG_PATH = "/app/changelog.md"  # Using the same path as in Patcher_API.py
SERVER_STATUS_PATH = "/app/ServerStatus.md"  # New path for server status

# Set up Discord client with reconnect enabled
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True  # Needed for channel updates
client = discord.Client(intents=intents, reconnect=True)

# Define a health check interval (5 minutes)
HEALTH_CHECK_INTERVAL = 300

async def sync_changelog_on_startup():
    """Fetch all messages from the changelog channel and update changelog.md with any new ones."""
    try:
        channel = client.get_channel(CHANGELOG_CHANNEL_ID)
        if not channel:
            logger.error(f"Changelog channel with ID {CHANGELOG_CHANNEL_ID} not found.")
            return
        logger.info("Syncing changelog on startup...")
        # Read existing changelog IDs
        existing_ids = set()
        if os.path.exists(CHANGELOG_PATH):
            with open(CHANGELOG_PATH, "r") as md_file:
                content = md_file.read()
                existing_ids = set([m for m in re.findall(r"## Entry (\d+)", content)])
        # Fetch all messages from the channel
        new_entries = []
        async for message in channel.history(limit=None, oldest_first=True):
            if str(message.id) not in existing_ids and message.content.strip():
                logger.info(f"Adding missed changelog entry: {message.id}")
                new_entries.append(message)
        # Add new entries to changelog.md
        if new_entries:
            logger.info(f"Adding {len(new_entries)} missed changelog entries to changelog.md")
            for msg in new_entries:
                await update_changelog_file(msg)
        else:
            logger.info("No missed changelog entries found.")
    except Exception as e:
        logger.error(f"Error syncing changelog on startup: {str(e)}")
        logger.error(traceback.format_exc())

async def health_check():
    """Periodically check connection health and log status"""
    await client.wait_until_ready()
    while not client.is_closed():
        try:
            logger.info("Health check - Bot is still connected, latency: {:.2f}ms".format(client.latency * 1000))
            
            # Ping Discord's API to keep connection active
            async with aiohttp.ClientSession() as session:
                async with session.get('https://discord.com/api/v10/gateway') as resp:
                    if resp.status == 200:
                        logger.info("Discord API gateway connection is healthy")
                    else:
                        logger.warning(f"Discord API gateway returned status code: {resp.status}")
            
            # Update bot status to show it's active
            await client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching, 
                    name=f"for updates | {datetime.now().strftime('%H:%M:%S')}"
                )
            )
            
            # Check channel access
            if client.get_channel(CHANGELOG_CHANNEL_ID) is None:
                logger.warning(f"Cannot access changelog channel {CHANGELOG_CHANNEL_ID}")
            
            if EXP_BOOST_CHANNEL_ID and client.get_channel(EXP_BOOST_CHANNEL_ID) is None:
                logger.warning(f"Cannot access exp boost channel {EXP_BOOST_CHANNEL_ID}")
                
        except Exception as e:
            logger.error(f"Error during health check: {str(e)}")
            logger.error(traceback.format_exc())
        
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)

@client.event
async def on_ready():
    logger.info(f'Bot is ready and connected to Discord! Connected as {client.user.name} (ID: {client.user.id})')
    await sync_changelog_on_startup()
    
    # Check for and update EXP boost status on startup
    for guild in client.guilds:
        for channel in guild.channels:
            if channel.id == EXP_BOOST_CHANNEL_ID:
                logger.info(f"Found EXP boost channel: {channel.name}")
                await update_server_status_from_channel(channel)
                break
    
    # Start health check task
    client.loop.create_task(health_check())
    
    # Set initial status
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name="for changelog updates"
        )
    )

@client.event
async def on_resumed():
    """Called when the client has resumed a session."""
    logger.info("Session resumed after disconnection.")
    
    # Re-sync changelog on resume to catch any missed messages
    await sync_changelog_on_startup()
    
    # Reset status
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name="for changelog updates"
        )
    )

@client.event
async def on_disconnect():
    """Called when the client has disconnected from Discord."""
    logger.warning("Bot disconnected from Discord. Will attempt to reconnect.")

@client.event
async def on_guild_channel_update(before, after):
    """Event that triggers when a channel is updated (including name changes)"""
    if after.id == EXP_BOOST_CHANNEL_ID and before.name != after.name:
        logger.info(f"EXP boost channel title changed from '{before.name}' to '{after.name}'")
        await update_server_status_from_channel(after)

@client.event
async def on_message(message):
    if message.channel.id == CHANGELOG_CHANNEL_ID:
        logger.info(f"New message in changelog channel: {message.content}")
        
        # Update the changelog.md file with the new message
        try:
            await update_changelog_file(message)
            logger.info("Successfully updated changelog.md file")

            # Post to Reddit
            try:
                reddit_poster = import_reddit_poster()
                if reddit_poster:
                    # Create entry object for the new message
                    entry = {
                        "id": str(message.id),
                        "author": message.author.display_name,
                        "timestamp": message.created_at.isoformat(),
                        "content": message.content
                    }

                    # Post to Reddit as a new post
                    success, result_message = reddit_poster.post_changelog_to_reddit(entry)
                    if success:
                        logger.info(f"Successfully posted to Reddit: {result_message}")
                    else:
                        logger.error(f"Failed to post to Reddit: {result_message}")
            except Exception as e:
                logger.error(f"Error posting to Reddit: {str(e)}")
                logger.error(traceback.format_exc())
        except Exception as e:
            logger.error(f"Error updating changelog.md: {str(e)}")
            logger.error(traceback.format_exc())

async def update_server_status_from_channel(channel):
    """Update the ServerStatus.md file with the channel title information"""
    try:
        # Extract the EXP boost value from the channel title
        channel_title = channel.name
        logger.info(f"Updating ServerStatus.md with channel title: {channel_title}")
        
        # Create the formatted entry
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        new_entry = f"**Channel ID:** {channel.id}\n"
        new_entry += f"**Channel Name:** {channel_title}\n"
        new_entry += f"**Last Updated:** {current_time}\n"
        new_entry += f"**Status:** {channel_title}\n"
        
        # Check if file exists
        if not os.path.exists(SERVER_STATUS_PATH):
            # Create initial file if it doesn't exist
            logger.info(f"Creating new ServerStatus.md file at {SERVER_STATUS_PATH}")
            content = "# Server Status\n\n"
            content += "## EXP Boost Status\n\n"
            content += new_entry
        else:
            # Read existing content
            logger.info(f"Reading existing ServerStatus.md file")
            try:
                with open(SERVER_STATUS_PATH, "r") as md_file:
                    content = md_file.read()
                
                # Replace the EXP Boost Status section
                if "## EXP Boost Status" in content:
                    parts = content.split("## EXP Boost Status\n\n", 1)
                    second_part = parts[1].split("\n\n## ", 1)
                    
                    if len(second_part) > 1:
                        # If there are other sections after EXP Boost
                        content = parts[0] + "## EXP Boost Status\n\n" + new_entry + "\n\n## " + second_part[1]
                    else:
                        # If EXP Boost is the only or last section
                        content = parts[0] + "## EXP Boost Status\n\n" + new_entry
                else:
                    # If EXP Boost section doesn't exist, add it at the end
                    content += "\n\n## EXP Boost Status\n\n" + new_entry
            except Exception as e:
                logger.error(f"Error reading ServerStatus.md: {str(e)}")
                logger.error(traceback.format_exc())
                # Create new file if reading fails
                content = "# Server Status\n\n## EXP Boost Status\n\n" + new_entry
        
        # Write updated content
        logger.info(f"Writing updated content to ServerStatus.md")
        with open(SERVER_STATUS_PATH, "w") as md_file:
            md_file.write(content)
            
        # Also save the exp boost status info
        save_exp_boost_status_info(channel)
        
        logger.info("Successfully updated ServerStatus.md with channel title")
        
    except Exception as e:
        logger.error(f"Error in update_server_status_from_channel: {str(e)}")
        logger.error(traceback.format_exc())
        raise

async def update_changelog_file(message):
    """Update the changelog.md file with a new message"""
    try:
        # Format the new entry
        new_entry = format_changelog_entry(message)
        
        # Check if file exists
        if not os.path.exists(CHANGELOG_PATH):
            # Create initial file if it doesn't exist
            logger.info(f"Creating new changelog.md file at {CHANGELOG_PATH}")
            content = "# Changelog\n\n"
            content += new_entry
        else:
            # Read existing content
            logger.info(f"Reading existing changelog.md file")
            try:
                with open(CHANGELOG_PATH, "r") as md_file:
                    content = md_file.read()
                
                # Add new entry after the header, at the top of the entries
                if "# Changelog" in content:
                    parts = content.split("# Changelog\n\n", 1)
                    content = "# Changelog\n\n" + new_entry + parts[1] if len(parts) > 1 else "# Changelog\n\n" + new_entry
                else:
                    # If for some reason header is missing, add it
                    content = "# Changelog\n\n" + new_entry + content
            except Exception as e:
                logger.error(f"Error reading changelog.md: {str(e)}")
                logger.error(traceback.format_exc())
                # Create new file if reading fails
                content = "# Changelog\n\n" + new_entry
        
        # Write updated content
        logger.info(f"Writing updated content to changelog.md")
        with open(CHANGELOG_PATH, "w") as md_file:
            md_file.write(content)
            
        # Also save the last message ID to a file for tracking
        save_last_message_info(message)
        
    except Exception as e:
        logger.error(f"Error in update_changelog_file: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def format_changelog_entry(message):
    """Format a Discord message as a changelog entry"""
    entry = f"## Entry {message.id}\n"
    entry += f"**Author:** {message.author.display_name}\n"
    entry += f"**Date:** {message.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    entry += f"{message.content}\n\n"
    entry += "---\n\n"
    return entry

def save_last_message_info(message):
    """Save information about the last processed message"""
    data = {
        "id": str(message.id),
        "author": message.author.display_name,
        "content": message.content[:100] + "..." if len(message.content) > 100 else message.content,
        "timestamp": message.created_at.isoformat(),
        "processed_at": datetime.now().isoformat()
    }
    
    try:
        with open("/app/last_message.json", "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving last_message.json: {str(e)}")
        logger.error(traceback.format_exc())

def save_exp_boost_status_info(channel):
    """Save information about the EXP boost channel status"""
    data = {
        "id": str(channel.id),
        "name": channel.name,
        "processed_at": datetime.now().isoformat()
    }
    
    try:
        with open("/app/last_exp_boost.json", "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving last_exp_boost.json: {str(e)}")
        logger.error(traceback.format_exc())

def import_reddit_poster():
    """Import the Reddit poster module."""
    try:
        spec = importlib.util.spec_from_file_location("reddit_poster", "/app/reddit_poster.py")
        reddit_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reddit_module)
        return reddit_module
    except Exception as e:
        logger.error(f"Error importing Reddit poster: {str(e)}")
        logger.error(traceback.format_exc())
        return None

# Run the client with proper reconnection handling
if __name__ == "__main__":
    # Try to handle keyboard interrupts gracefully
    try:
        logger.info("Starting Discord bot...")
        client.run(TOKEN, reconnect=True)
    except discord.errors.LoginFailure:
        logger.critical("Invalid Discord token. Please check your .env file.")
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}")
        logger.critical(traceback.format_exc())
        # Wait a bit before exiting to allow logs to be written
        asyncio.run(asyncio.sleep(1))
