import os
import sys
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

# Define health check intervals
HEALTH_CHECK_INTERVAL = 120  # 2 minutes for stable heartbeat
HEARTBEAT_INITIAL_INTERVAL = 30  # 30 seconds for initial heartbeats

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

def force_azure_heartbeat_log(message):
    """Write a heartbeat log in multiple ways to ensure it gets picked up in Azure"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Create a visually distinct heartbeat message with separators
    separator = "="*50
    formatted_message = f"\n{separator}\n💓 HEARTBEAT ({timestamp})\n{message}\n{separator}\n"
    heartbeat_msg = f"{timestamp} [DISCORD_HEARTBEAT] {message}"
    
    # Method 1: Standard logging (keep it simple for structured logging)
    logger.info(f"HEARTBEAT: {message}")
    
    # Method 2: Direct stdout write with flush - use the formatted version
    print(formatted_message, flush=True)
    
    # Method 3: Direct stderr write with flush (Azure sometimes prioritizes stderr)
    print(formatted_message, file=sys.stderr, flush=True)
    
    # Method 4: Write to dedicated heartbeat logfile - standard format for easy parsing
    try:
        os.makedirs('/app/logs', exist_ok=True)
        with open("/app/logs/discord_heartbeat.log", "a") as f:
            f.write(heartbeat_msg + "\n")
    except Exception as e:
        print(f"Error writing to heartbeat logfile: {e}", file=sys.stderr, flush=True)

async def health_check():
    """Periodically check connection health and log status"""
    await client.wait_until_ready()
    
    # Gradual startup - start with more frequent checks that get less frequent over time
    initial_checks = 5
    initial_interval = HEARTBEAT_INITIAL_INTERVAL  # 30 seconds by default
    current_interval = initial_interval
    max_interval = HEALTH_CHECK_INTERVAL  # Final stable interval (2 minutes)
    
    check_count = 0
    
    while not client.is_closed():
        check_count += 1
        try:
            # Calculate latency in milliseconds
            latency_ms = client.latency * 1000
            
            # Build a more detailed heartbeat message with multiple lines of information
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            heartbeat_lines = [
                f"Discord health check #{check_count}",
                f"Time: {current_time}",
                f"Bot: {client.user.name} (ID: {client.user.id})",
                f"Connection: Active, latency: {latency_ms:.2f}ms",
                f"Interval: {current_interval}s"
            ]
            
            # Add info about channels being monitored
            changelog_channel = client.get_channel(CHANGELOG_CHANNEL_ID)
            if changelog_channel:
                heartbeat_lines.append(f"Monitoring changelog channel: #{changelog_channel.name}")
            
            if EXP_BOOST_CHANNEL_ID:
                exp_channel = client.get_channel(EXP_BOOST_CHANNEL_ID)
                if exp_channel:
                    heartbeat_lines.append(f"Monitoring EXP boost channel: #{exp_channel.name}")
            
            # Join everything into a multi-line message for the heartbeat log
            heartbeat_message = "\n".join(heartbeat_lines)
            
            # Use special Azure heartbeat logging for better visibility
            force_azure_heartbeat_log(heartbeat_message)
            
            # Ping Discord's API to keep connection active
            async with aiohttp.ClientSession() as session:
                async with session.get('https://discord.com/api/v10/gateway') as resp:
                    gateway_status = "HEALTHY" if resp.status == 200 else f"WARNING ({resp.status})"
                    logger.info(f"Discord API gateway connection: {gateway_status}")
                    if resp.status != 200:
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
        
        # Calculate the interval for the next check
        # Gradually increase from initial_interval to max_interval
        if check_count < initial_checks:
            # Keep initial interval for the first few checks
            interval = initial_interval
        else:
            # Gradually increase interval
            progress = min(1.0, (check_count - initial_checks) / 10)  # Transition over 10 checks
            interval = int(initial_interval + progress * (max_interval - initial_interval))
            
            # Once we reach maximum interval, stay there
            if interval >= max_interval:
                interval = max_interval
                # Log that we've reached stable interval
                if current_interval != max_interval:
                    logger.info(f"Health check interval has reached stable value of {max_interval} seconds")
        
        # If interval changed, log it
        if interval != current_interval:
            logger.info(f"Health check interval adjusted from {current_interval} to {interval} seconds")
            current_interval = interval
        
        await asyncio.sleep(interval)

@client.event
async def on_ready():
    logger.info(f'Bot is ready and connected to Discord! Connected as {client.user.name} (ID: {client.user.id})')
    
    # Start the health check task (only once)
    client.loop.create_task(health_check())
    logger.info("Health check task started")
    
    # Force an immediate heartbeat log for Azure visibility
    force_azure_heartbeat_log(f"Discord bot ready - connected as {client.user.name}")
    
    # Add debug log for intents configuration
    logger.info(f"Bot intents configuration: message_content={intents.message_content}, guilds={intents.guilds}")
    logger.info(f"Monitoring changelog channel ID: {CHANGELOG_CHANNEL_ID}")
    
    await sync_changelog_on_startup()
    
    # Check for and update EXP boost status on startup
    for guild in client.guilds:
        for channel in guild.channels:
            if channel.id == EXP_BOOST_CHANNEL_ID:
                logger.info(f"Found EXP boost channel: {channel.name}")
                await update_server_status_from_channel(channel)
                break
    
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
    # Debug log for ALL messages
    logger.info(f"MESSAGE RECEIVED - Channel: {message.channel.id}, Author: {message.author}, Content: {message.content[:50]}...")

    # Specific handler for changelog channel
    if message.channel.id == CHANGELOG_CHANNEL_ID:
        logger.info(f"CHANGELOG MESSAGE DETECTED - Content: {message.content}")
        
        # Update the changelog.md file with the new message
        try:
            await update_changelog_file(message)
            logger.info("Successfully updated changelog.md file")
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
        # Log file path and check permissions
        logger.info(f"Attempting to update changelog file at: {CHANGELOG_PATH}")
        
        # Check file permissions if the file exists
        if os.path.exists(CHANGELOG_PATH):
            try:
                # Check if file is readable
                with open(CHANGELOG_PATH, "r") as test_read:
                    test_read.read(1)
                logger.info("Changelog file is readable")
                
                # Check if file is writable
                with open(CHANGELOG_PATH, "a") as test_write:
                    test_write.write("")
                logger.info("Changelog file is writable")
            except Exception as e:
                logger.error(f"Permission issue with changelog file: {str(e)}")
        else:
            logger.info("Changelog file does not exist yet and will be created")
            
            # Check if directory is writable
            try:
                dir_path = os.path.dirname(CHANGELOG_PATH)
                os.makedirs(dir_path, exist_ok=True)
                test_file = os.path.join(dir_path, "test_permissions.tmp")
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)
                logger.info("Directory is writable")
            except Exception as e:
                logger.error(f"Directory permission issue: {str(e)}")
        
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
@client.event
async def on_guild_available(guild):
    """Called when a guild becomes available."""
    logger.info(f"Guild available: {guild.name} (ID: {guild.id})")
    # List all visible channels to validate permissions
    visible_channels = [f"{channel.name} (ID: {channel.id})" for channel in guild.channels if isinstance(channel, discord.TextChannel)]
    logger.info(f"Visible text channels: {', '.join(visible_channels)}")
    
    # Check if our target channel is visible
    changelog_channel = client.get_channel(CHANGELOG_CHANNEL_ID)
    if changelog_channel:
        logger.info(f"Found changelog channel: {changelog_channel.name}")
        # Check permissions in the changelog channel
        permissions = changelog_channel.permissions_for(guild.me)
        logger.info(f"Bot permissions in changelog channel: read_messages={permissions.read_messages}, send_messages={permissions.send_messages}, view_channel={permissions.view_channel}")
    else:
        logger.warning(f"Cannot find changelog channel with ID {CHANGELOG_CHANNEL_ID}")

# Add a new member join event to test event handling
@client.event
async def on_member_join(member):
    logger.info(f"Member joined: {member.name} (ID: {member.id})")
    # This is just for testing Discord events - we don't need to take any action