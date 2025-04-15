import os
import discord
from dotenv import load_dotenv
import logging
import json
from datetime import datetime
import asyncio

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
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the paths to the files
CHANGELOG_PATH = "/app/changelog.md"  # Using the same path as in Patcher_API.py
SERVER_STATUS_PATH = "/app/ServerStatus.md"  # New path for server status

# Set up Discord client
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True  # Needed for channel updates
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    logger.info('Bot is ready and connected to Discord!')
    
    # Check for and update EXP boost status on startup
    for guild in client.guilds:
        for channel in guild.channels:
            if channel.id == EXP_BOOST_CHANNEL_ID:
                logger.info(f"Found EXP boost channel: {channel.name}")
                await update_server_status_from_channel(channel)
                break

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
        except Exception as e:
            logger.error(f"Error updating changelog.md: {str(e)}")

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

if __name__ == "__main__":
    client.run(TOKEN)