import os
import discord
from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import uvicorn
from typing import Optional, Callable
import aiohttp
from fastapi.security import APIKeyHeader
import json
import logging
import sys
import requests
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse
import markdown
import re
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Configure logging for Azure
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Get the root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove any existing handlers
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Add stdout handler to root logger
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
root_logger.addHandler(stdout_handler)

logger = logging.getLogger(__name__)

# Initial startup log
logger.info("=== Bot Starting Up ===")
logger.info("Python version: %s", sys.version)
logger.info("Current working directory: %s", os.getcwd())

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANGELOG_CHANNEL_ID = int(os.getenv('CHANGELOG_CHANNEL_ID')) 
EXP_BOOST_CHANNEL_ID = os.getenv('EXP_BOOST_CHANNEL_ID')
PATCHER_TOKEN = os.getenv('PATCHER_TOKEN')

# Convert EXP_BOOST_CHANNEL_ID to int if it exists
if EXP_BOOST_CHANNEL_ID:
    EXP_BOOST_CHANNEL_ID = int(EXP_BOOST_CHANNEL_ID)
else:
    logger.warning("EXP_BOOST_CHANNEL_ID not set - exp boost functionality will be disabled")

# Wiki variables
WIKI_API_URL = os.getenv('WIKI_API_URL')
WIKI_API_KEY = os.getenv('WIKI_API_KEY')
WIKI_PAGE_ID = os.getenv('WIKI_PAGE_ID') 

# Ensure we use the port provided by Azure
PORT = int(os.getenv('PORT', '80'))

WIKI_HEADER = """![change-logs.webp](/change-logs.webp){.align-center}
# THJ Change-Logs
(Newest is up top, Oldest is at the bottom.)"""

# Add this constant near the top with other constants
VALUE_CHANNEL_ID = 1319011465960882197

API_BASE_URL = os.getenv('API_BASE_URL')

CHANGELOG_PATH = "/app/changelog.md"
# Add path for ServerStatus.md
SERVER_STATUS_PATH = "/app/ServerStatus.md"

def mask_sensitive_string(s: str) -> str:
    """Mask sensitive string by showing only first and last 4 characters"""
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"

# Verify required environment variables
print("\n=== Environment Check ===")
required_vars = {
    'DISCORD_TOKEN': TOKEN,
    'CHANGELOG_CHANNEL_ID': CHANGELOG_CHANNEL_ID,
    'PATCHER_TOKEN': PATCHER_TOKEN
}

for var_name, var_value in required_vars.items():
    if not var_value:
        print(f"❌ {var_name} is missing!")
        raise ValueError(f"{var_name} environment variable is required")
    else:
        print(f"✓ {var_name} configured")

# Log Wiki variables status
print("\n=== Optional Wiki Variables ===")
wiki_vars = {
    'WIKI_API_URL': WIKI_API_URL,
    'WIKI_API_KEY': WIKI_API_KEY,
    'WIKI_PAGE_ID': WIKI_PAGE_ID,
    'EXP_BOOST_CHANNEL_ID': EXP_BOOST_CHANNEL_ID
}

for var_name, var_value in wiki_vars.items():
    status = "✓ configured" if var_value else "⚪ not set (optional)"
    print(f"{var_name}: {status}")

print("=== Environment Check Complete ===\n")

# Set up Discord client
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
client = discord.Client(intents=intents)

# Global variables for channels
changelog_channel = None
exp_boost_channel = None

@client.event
async def on_ready():
    """Handle Discord client ready event"""
    global changelog_channel, exp_boost_channel
    logger.info('🤖 Bot connected successfully!')
    
    for guild in client.guilds:
        for channel in guild.channels:
            if channel.id == CHANGELOG_CHANNEL_ID:
                changelog_channel = channel
                logger.info('✅ Found changelog channel: %s', channel.name)
            elif channel.id == EXP_BOOST_CHANNEL_ID:
                exp_boost_channel = channel
                logger.info('✅ Found exp boost channel: %s', channel.name)
    
    if not changelog_channel:
        logger.error('❌ Could not find changelog channel!')
    if not exp_boost_channel:
        logger.error('❌ Could not find exp boost channel!')

class APILoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests with detailed information"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get client IP - works with X-Forwarded-For header for proxied requests
        client_ip = request.client.host
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        
        # Get auth status (authenticated or anonymous)
        auth_status = "anonymous"
        if "X-Patcher-Token" in request.headers:
            # Mask the token in logs for security
            token_value = request.headers["X-Patcher-Token"]
            masked_token = mask_sensitive_string(token_value)
            auth_status = "authenticated" if token_value == PATCHER_TOKEN else f"invalid_token({masked_token})"
        
        # Log the request start
        request_id = f"{int(time.time() * 1000)}-{os.urandom(4).hex()}"
        logger.info(f"API Request #{request_id} | {request.method} {request.url.path} | From: {client_ip} | Auth: {auth_status}")
        
        # Process the request and measure time
        start_time = time.time()
        try:
            response = await call_next(request)
            process_time = time.time() - start_time
            
            # Log successful response
            logger.info(
                f"API Response #{request_id} | {request.method} {request.url.path} | "
                f"Status: {response.status_code} | Time: {process_time:.3f}s | Size: {response.headers.get('content-length', 'unknown')}"
            )
            
            return response
        except Exception as e:
            # Log exceptions
            process_time = time.time() - start_time
            logger.error(
                f"API Error #{request_id} | {request.method} {request.url.path} | "
                f"Error: {str(e)} | Time: {process_time:.3f}s"
            )
            raise

# Set up FastAPI
app = FastAPI()

# Add API logging middleware
app.add_middleware(APILoggingMiddleware)

# Set up security
api_key_header = APIKeyHeader(name="X-Patcher-Token", auto_error=True)

async def verify_token(api_key: str = Security(api_key_header)):
    if api_key != PATCHER_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )
    return api_key

@app.on_event("startup")
async def on_startup():
    """Initialize the application."""
    logger.info("FastAPI application starting up...")

@app.on_event("startup")
async def create_changelog_on_startup():
    """Create and populate the changelog.md file during startup."""
    try:
        logger.info("Checking for changelog.md file...")
        file_existed = os.path.exists(CHANGELOG_PATH)
        
        if not file_existed:
            logger.info("changelog.md not found. Creating initial file...")
            
            # Create a simple initial markdown file
            markdown_content = "# Changelog\n\n"
            markdown_content += "This file will be populated with changelog entries.\n\n"
            
            # Save to a Markdown file
            with open(CHANGELOG_PATH, "w") as md_file:
                md_file.write(markdown_content)
            
            logger.info("✅ Initial changelog.md created successfully!")
        else:
            logger.info(f"✓ changelog.md already exists at {CHANGELOG_PATH}")
        
        # Now populate the file with changelog data from Discord
        logger.info("Fetching all changelogs to populate the file...")
        try:
            # Wait a bit for the Discord client to be ready
            await asyncio.sleep(5)
            
            if client.is_ready() and changelog_channel:
                # Fetch all messages directly from Discord
                logger.info("Fetching messages from Discord changelog channel...")
                messages = []
                async for message in changelog_channel.history(limit=None):
                    # Check if the message has meaningful content
                    if message.content.strip():
                        messages.append({
                            "id": str(message.id),
                            "content": message.content,
                            "author": message.author.display_name,
                            "timestamp": message.created_at.isoformat()
                        })
                
                if messages:
                    logger.info(f"Found {len(messages)} changelog entries, updating the file...")
                    
                    # Sort messages by ID (chronological order)
                    messages.sort(key=lambda x: int(x["id"]))
                    
                    # Generate Markdown content
                    markdown_content = "# Changelog\n\n"
                    for log in messages:
                        markdown_content += f"## Entry {log['id']}\n"
                        markdown_content += f"**Author:** {log['author']}\n"
                        markdown_content += f"**Date:** {log['timestamp']}\n\n"
                        markdown_content += f"{log['content']}\n\n"
                        markdown_content += "---\n\n"
                    
                    # Save to the markdown file
                    with open(CHANGELOG_PATH, "w") as md_file:
                        md_file.write(markdown_content)
                    
                    logger.info("✅ Successfully populated changelog.md with all entries!")
                else:
                    logger.info("No changelog entries found to populate the file.")
            else:
                logger.warning("Discord client or changelog channel not ready, skipping automatic population")
                logger.info("The file will be populated when you call /generate-markdown endpoint manually")
        except Exception as e:
            logger.error(f"Error populating changelog.md with entries: {str(e)}")
            logger.info("You can still manually update using the /generate-markdown endpoint")
            
    except Exception as e:
        logger.error(f"Error managing changelog.md file: {str(e)}")

@app.on_event("startup")
async def create_server_status_on_startup():
    """Create and populate the ServerStatus.md file during startup."""
    try:
        logger.info("Checking for ServerStatus.md file...")
        file_existed = os.path.exists(SERVER_STATUS_PATH)
        
        if not file_existed:
            logger.info("ServerStatus.md not found. Creating initial file...")
            
            # Create a simple initial markdown file
            markdown_content = "# Server Status\n\n"
            markdown_content += "## EXP Boost Status\n\n"
            markdown_content += "No EXP boost status available yet.\n"
            
            # Save to a Markdown file
            with open(SERVER_STATUS_PATH, "w") as md_file:
                md_file.write(markdown_content)
            
            logger.info("✅ Initial ServerStatus.md created successfully!")
        else:
            logger.info(f"✓ ServerStatus.md already exists at {SERVER_STATUS_PATH}")
        
        # Now populate the file with the latest EXP boost data from Discord
        logger.info("Fetching latest EXP boost status to populate the file...")
        try:
            # Wait a bit for the Discord client to be ready
            await asyncio.sleep(5)
            
            if client.is_ready() and exp_boost_channel:
                # Fetch the latest message directly from Discord
                logger.info("Fetching message from Discord EXP boost channel...")
                messages = [message async for message in exp_boost_channel.history(limit=1)]
                
                if messages:
                    latest_message = messages[0]
                    
                    # Generate the entry
                    logger.info("Creating ServerStatus.md entry from latest message...")
                    markdown_content = "# Server Status\n\n"
                    markdown_content += "## EXP Boost Status\n\n"
                    markdown_content += f"**Message ID:** {latest_message.id}\n"
                    markdown_content += f"**Author:** {latest_message.author.display_name}\n"
                    markdown_content += f"**Last Updated:** {latest_message.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    markdown_content += f"**Status:** {latest_message.content.strip()}\n"
                    
                    # Save to the markdown file
                    with open(SERVER_STATUS_PATH, "w") as md_file:
                        md_file.write(markdown_content)
                    
                    # Also save the last EXP boost message info
                    data = {
                        "id": str(latest_message.id),
                        "author": latest_message.author.display_name,
                        "content": latest_message.content.strip(),
                        "timestamp": latest_message.created_at.isoformat(),
                        "processed_at": datetime.now().isoformat()
                    }
                    
                    try:
                        with open("/app/last_exp_boost.json", "w") as f:
                            json.dump(data, f, indent=2)
                    except Exception as e:
                        logger.error(f"Error saving last_exp_boost.json: {str(e)}")
                    
                    logger.info("✅ Successfully populated ServerStatus.md with latest EXP boost status!")
                else:
                    logger.info("No EXP boost entries found to populate the file.")
            else:
                logger.warning("Discord client or exp_boost_channel not ready, skipping automatic population")
                logger.info("The file will be populated when a new message arrives in the EXP boost channel")
        except Exception as e:
            logger.error(f"Error populating ServerStatus.md with latest status: {str(e)}")
            
    except Exception as e:
        logger.error(f"Error managing ServerStatus.md file: {str(e)}")

@app.get("/changelog/markdown", dependencies=[Depends(verify_token)])
async def serve_changelog_markdown(download: bool = False):
    """
    Serve the generated changelog.md file.
    Requires X-Patcher-Token header for authentication.
    Use ?download=true to download the file instead of viewing it.
    """
    if not os.path.exists(CHANGELOG_PATH):
        await create_changelog_on_startup()
    
    filename = "changelog.md"
    
    if download:
        # Set Content-Disposition to attachment to force download
        return FileResponse(
            CHANGELOG_PATH, 
            media_type="text/markdown",
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        # Default behavior - view in browser
        return FileResponse(CHANGELOG_PATH, media_type="text/markdown")

@app.get("/serverstatus/markdown", dependencies=[Depends(verify_token)])
async def serve_server_status_markdown(download: bool = False):
    """
    Serve the generated ServerStatus.md file.
    Requires X-Patcher-Token header for authentication.
    Use ?download=true to download the file instead of viewing it.
    """
    if not os.path.exists(SERVER_STATUS_PATH):
        await create_server_status_on_startup()
    
    filename = "ServerStatus.md"
    
    if download:
        # Set Content-Disposition to attachment to force download
        return FileResponse(
            SERVER_STATUS_PATH, 
            media_type="text/markdown",
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    else:
        # Default behavior - view in browser
        return FileResponse(SERVER_STATUS_PATH, media_type="text/markdown")

@app.post("/generate-markdown", dependencies=[Depends(verify_token)])
async def generate_markdown():
    """
    Endpoint to generate/update the Markdown file from changelogs.
    Requires X-Patcher-Token header for authentication.
    """
    try:
        # Get changelogs
        changelogs_response = await get_changelog(all=True)
        changelogs = changelogs_response.get("changelogs", [])
        
        # Generate Markdown content
        markdown_content = "# Changelog\n\n"
        for log in changelogs:
            markdown_content += f"## Entry {log['id']}\n{log['content']}\n\n"
        
        # Save to a Markdown file
        with open(CHANGELOG_PATH, "w") as md_file:
            md_file.write(markdown_content)
        
        return {"status": "success", "message": "Markdown file generated."}
    except Exception as e:
        logger.error(f"Error generating markdown: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/exp-boost", dependencies=[Depends(verify_token)])
async def get_exp_boost():
    """
    Get the current EXP boost status from the ServerStatus.md file.
    Requires X-Patcher-Token header for authentication.
    """
    try:
        # Check if the ServerStatus file exists
        if not os.path.exists(SERVER_STATUS_PATH):
            await create_server_status_on_startup()
            
            # If we still don't have a file, return an error
            if not os.path.exists(SERVER_STATUS_PATH):
                raise HTTPException(status_code=404, detail="ServerStatus.md file not found")
        
        # Read the ServerStatus file content
        with open(SERVER_STATUS_PATH, "r") as md_file:
            content = md_file.read()
        
        # Extract the EXP boost status information using regex
        # Updated pattern to match the new format that captures the channel name
        exp_boost_pattern = r"## EXP Boost Status\s+\n\*\*Channel ID:\*\* (\d+)\s+\n\*\*Channel Name:\*\* (.*?)\s+\n\*\*Last Updated:\*\* (.*?)\s+\n\*\*Status:\*\* (.*?)(?=\n\n|\Z)"
        match = re.search(exp_boost_pattern, content)
        
        if match:
            channel_id = match.group(1)
            channel_name = match.group(2)
            last_updated = match.group(3)
            status = match.group(4).strip()
            
            return {
                "status": "success",
                "exp_boost": {
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "last_updated": last_updated,
                    "value": channel_name  # The EXP boost value is contained in the channel name itself
                }
            }
        else:
            return {
                "status": "success",
                "exp_boost": {
                    "channel_id": None,
                    "channel_name": None,
                    "last_updated": None,
                    "value": "No EXP boost status available"
                }
            }
        
    except Exception as e:
        logger.error(f"Error fetching EXP boost status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/expbonus", dependencies=[Depends(verify_token)])
async def get_exp_bonus():
    """
    Alias for /exp-boost endpoint to maintain compatibility with clients using /expbonus
    Requires X-Patcher-Token header for authentication.
    """
    logger.info("Redirecting /expbonus request to /exp-boost endpoint")
    return await get_exp_boost()

@app.get("/serverstatus", dependencies=[Depends(verify_token)])
async def get_server_status():
    """
    Get the current server status from Project EQ API
    Requires X-Patcher-Token header for authentication.
    """
    try:
        logger.info("\n=== Fetching Server Status ===")
        
        # Use the same proxy URL as the JS code
        proxy_url = "https://api.codetabs.com/v1/proxy?quest=http://login.projecteq.net/servers/list"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(proxy_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch server status. Status: {response.status}")
                    raise HTTPException(
                        status_code=503,
                        detail="Failed to fetch server status"
                    )
                
                data = await response.json()
                logger.info("Successfully fetched server data")
                
                # Find the Heroes' Journey server
                server = next(
                    (s for s in data if "Heroes' Journey [Multiclass" in s.get('server_long_name', '')),
                    None
                )
                
                if not server:
                    logger.warning("Heroes' Journey server not found in response")
                    return {
                        "status": "success",
                        "found": False,
                        "message": "Server not found in response"
                    }
                
                        "last_updated": datetime.now().isoformat()
                    }
                }
                
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching server status: {str(e)}")
        raise HTTPException(
            status_code=503,
            detail="Failed to connect to server status API"
        )
    except Exception as e:
        logger.error(f"Error fetching server status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

def format_changelog_for_wiki(content, timestamp, author):
    """Format changelog content for wiki presentation"""
    # Clean and validate the content
    if not content or not isinstance(content, str):
        logger.error(f"Invalid content type: {type(content)}")
        return ""
        
    # Remove Discord markdown code blocks and trim
    content = content.replace('```', '').strip()
    
    # Format the entry with consistent spacing
    formatted = f"# {timestamp.strftime('%B %d, %Y')}\n"
    formatted += f"## {author}\n\n"
    formatted += f"{content}\n\n"
    formatted += "---"  # No extra newlines after horizontal rule
    
    return formatted

@app.get("/last-message", dependencies=[Depends(verify_token)])
async def get_last_message():
    """
    Get the last message from the changelog channel
    Requires X-Patcher-Token header for authentication.
    """
    try:
        print("\n=== Attempting to read last message ===")
        print(f"Channel ID we're looking for: {CHANGELOG_CHANNEL_ID}")
        
        if not client.is_ready():
            print("Discord client is not ready")
            return {"status": "error", "message": "Discord client is not ready"}
            
        if not changelog_channel:
            print("Changelog channel not found")
            return {"status": "error", "message": "Changelog channel not found"}
            
        print(f"Found channel: {changelog_channel.name}")
        
        # Get the last message
        messages = [message async for message in changelog_channel.history(limit=1)]
        
        if not messages:
            print("No messages found")
            return {"status": "success", "message": "No messages found"}
            
        last_message = messages[0]
        print(f"Found message: {last_message.content[:100]}...")
        
        return {
            "status": "success",
            "message": {
                "content": last_message.content,
                "author": last_message.author.display_name,
                "created_at": last_message.created_at.isoformat(),
                "id": last_message.id
            }
        }
        
    except Exception as e:
        print(f"Error reading last message: {str(e)}")
        print(f"Full error details: {repr(e)}")
        return {"status": "error", "message": str(e)}

@app.get("/patcher/latest", dependencies=[Depends(verify_token)])
async def get_latest_for_patcher():
    """
    Secure endpoint for the patcher to get the latest changelog entry.
    Requires X-Patcher-Token header for authentication.
    Returns the latest changelog message in a formatted structure.
    """
    try:
        print("\n=== Patcher requesting latest changelog ===")
        
        if not client.is_ready():
            raise HTTPException(status_code=503, detail="Discord client is not ready")
            
        if not changelog_channel:
            raise HTTPException(status_code=503, detail="Changelog channel not found")
            
        messages = [message async for message in changelog_channel.history(limit=1)]
        
        if not messages:
            return {
                "status": "success",
                "found": False,
                "message": "No changelog entries found"
            }
            
        last_message = messages[0]
        
        formatted_content = format_changelog_for_wiki(
            last_message.content,
            last_message.created_at,
            last_message.author.display_name
        )
        
        return {
            "status": "success",
            "found": True,
            "changelog": {
                "raw_content": last_message.content,
                "formatted_content": formatted_content,
                "author": last_message.author.display_name,
                "timestamp": last_message.created_at.isoformat(),
                "message_id": str(last_message.id)
            }
        }
        
    except Exception as e:
        print(f"Error in patcher endpoint: {str(e)}")
        print(f"Full error details: {repr(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/changelog/{message_id}", dependencies=[Depends(verify_token)])
@app.get("/changelog", dependencies=[Depends(verify_token)])
async def get_changelog(message_id: Optional[str] = None, all: Optional[bool] = False):
    """
    Get changelogs from the local changelog.md file.
    Can be called as either:
    - /changelog?message_id=1234567890
    - /changelog/1234567890
    - /changelog?all=true (to get all changelogs)
    If message_id is provided, returns all changelogs after that message.
    If no message_id is provided and all=false, returns the latest changelog.
    If all=true, returns all available changelogs.
    Requires X-Patcher-Token header for authentication.
    """
    try:
        logger.info("\n=== Fetching Changelogs from local file ===")
        
        # Check if the changelog file exists
        if not os.path.exists(CHANGELOG_PATH):
            logger.error("Changelog file not found")
            raise HTTPException(status_code=404, detail="Changelog file not found")
        
        # Read the changelog file content
        with open(CHANGELOG_PATH, "r") as md_file:
            content = md_file.read()
        
        # Parse the content into changelog entries
        # Use a more precise regex pattern to split entries
        entries_pattern = r"## Entry (\d+)\s+\*\*Author:\*\* (.*?)\s+\*\*Date:\*\* (.*?)\s+\n([\s\S]*?)(?=\n---\n|\Z)"
        entry_matches = re.finditer(entries_pattern, content)
        
        messages = []
        entry_ids = []
        for match in entry_matches:
            entry_id = match.group(1)
            author = match.group(2)
            timestamp = match.group(3)
            entry_content = match.group(4).strip()
            
            messages.append({
                "id": entry_id,
                "content": entry_content,
                "author": author,
                "timestamp": timestamp
            })
            entry_ids.append(entry_id)
        
        # Log a summary instead of each individual entry
        if entry_ids:
            logger.info(f"Found {len(entry_ids)} changelog entries (IDs from {entry_ids[0]} to {entry_ids[-1]})")
        else:
            logger.info("No changelog entries found")
        
        # Sort messages by ID (chronological order)
        messages.sort(key=lambda x: int(x["id"]))
        
        # Filter based on message_id if provided
        if message_id:
            try:
                reference_id = int(message_id)
                filtered_messages = [m for m in messages if int(m["id"]) > reference_id]
                logger.info(f"Filtered to {len(filtered_messages)} entries after ID: {reference_id}")
                messages = filtered_messages
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid message ID format")
        elif not all:
            # If not all and no message_id, get only the latest
            if messages:
                messages = [messages[-1]]
                logger.info(f"Returning only the latest changelog: {messages[0]['id']}")
        
        return {
            "status": "success",
            "changelogs": messages,
            "total": len(messages)
        }
        
    except Exception as e:
        logger.error(f"Error fetching changelogs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/wiki/update-changelog", dependencies=[Depends(verify_token)])
async def update_wiki_with_all_changelogs():
    """
    Fetch all changelogs and update the wiki page with them.
    Requires X-Patcher-Token header for authentication.
    """
    print("\n=== Starting Wiki Changelog Update ===")
    
    # Check if wiki integration is configured
    if not all([WIKI_API_URL, WIKI_API_KEY, WIKI_PAGE_ID]):
        raise HTTPException(
            status_code=500,
            detail="Wiki integration is not fully configured. Please set WIKI_API_URL, WIKI_API_KEY, and WIKI_PAGE_ID."
        )
    
    try:
        # Get all changelogs using existing endpoint logic
        changelogs = await get_changelog(all=True)
        
        if not changelogs["total"]:
            return {
                "status": "success",
                "message": "No changelogs found to update"
            }
        
        # Format all changelogs for wiki
        formatted_content = "# Changelog\n\n"
        for changelog in changelogs["changelogs"]:
            formatted_content += changelog["formatted_content"]
        
        # Update the wiki page
        page_id = int(WIKI_PAGE_ID)
        success = await update_wiki_page(formatted_content, page_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Successfully updated wiki with {changelogs['total']} changelog entries",
                "total_entries": changelogs["total"]
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to update wiki page"
            )
            
    except Exception as e:
        print(f"❌ Error updating wiki with changelogs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def update_wiki_page(content: str, page_id: int) -> bool:
    """
    Update the specified wiki page with new content and render it to make it visible.
    Returns True if successful, False otherwise.
    """
    try:
        logger.info(f"\n=== Wiki Page Update Process ===")
        logger.info(f"Target Page ID: {page_id}")
        
        # Validate content
        if not content or not isinstance(content, str):
            logger.error("Invalid content provided to update_wiki_page")
            return False
        
        headers = {
            'Authorization': f'Bearer {WIKI_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Log detailed content analysis
        logger.info("Content Analysis:")
        logger.info(f"- Total length: {len(content)} characters")
        logger.info(f"- First 100 chars: {content[:100]}")
        logger.info(f"- Last 100 chars: {content[-100:] if len(content) > 100 else content}")
        logger.info("- Number of lines: {}".format(content.count('\n') + 1))
        
        # Update mutation with isPublished
        update_mutation = """
        mutation UpdatePage($id: Int!, $content: String!) {
          pages {
            update(id: $id, content: $content, isPublished: true) {
              responseResult {
                succeeded
                errorCode
                slug
                message
              }
            }
          }
        }
        """
        
        variables = {
            "id": page_id,
            "content": content
        }
        
        # Log request details
        logger.info("\nRequest Details:")
        logger.info(f"- API URL: {WIKI_API_URL}")
        logger.info(f"- Update Mutation: {update_mutation.strip()}")
        logger.info(f"- Variables: id={page_id}, content_length={len(content)}")
        
        async with aiohttp.ClientSession() as session:
            # Step 1: Update content with isPublished
            logger.info("\nExecuting update mutation...")
            async with session.post(
                WIKI_API_URL,
                json={"query": update_mutation, "variables": variables},
                headers=headers
            ) as response:
                response_status = response.status
                response_data = await response.json()
                
                logger.info(f"\nUpdate Response Analysis:")
                logger.info(f"- HTTP Status: {response_status}")
                logger.info(f"- Raw Response: {json.dumps(response_data, indent=2)}")
                
                if 'errors' in response_data:
                    logger.error("\nGraphQL Errors in update:")
                    for error in response_data['errors']:
                        logger.error(f"- Path: {error.get('path', 'N/A')}")
                        logger.error(f"- Message: {error.get('message', 'N/A')}")
                        logger.error(f"- Extensions: {error.get('extensions', {})}")
                    return False
                
                update_result = response_data.get('data', {}).get('pages', {}).get('update', {}).get('responseResult', {})
                
                # Continue even if we get the map error, as we know the update still works
                if update_result.get('message') == "Cannot read properties of undefined (reading 'map')":
                    logger.warning("\n⚠️ Received 'map' error but continuing as this is expected")
                elif not update_result.get('succeeded', False):
                    logger.error(f"\n❌ Failed to update page: {update_result.get('message', 'Unknown error')}")
                    return False
                
                # Step 2: Render the page
                render_mutation = """
                mutation RenderPage($id: Int!) {
                  pages {
                    render(id: $id) {
                      responseResult {
                        succeeded
                        message
                      }
                    }
                  }
                }
                """
                
                render_variables = {
                    "id": page_id
                }
                
                logger.info("\nExecuting render mutation...")
                async with session.post(
                    WIKI_API_URL,
                    json={"query": render_mutation, "variables": render_variables},
                    headers=headers
                ) as render_response:
                    render_status = render_response.status
                    render_data = await render_response.json()
                    
                    logger.info(f"\nRender Response Analysis:")
                    logger.info(f"- HTTP Status: {render_status}")
                    logger.info(f"- Raw Response: {json.dumps(render_data, indent=2)}")
                    
                    if 'errors' in render_data:
                        logger.error("\nGraphQL Errors in render:")
                        for error in render_data['errors']:
                            logger.error(f"- Path: {error.get('path', 'N/A')}")
                            logger.error(f"- Message: {error.get('message', 'N/A')}")
                            logger.error(f"- Extensions: {error.get('extensions', {})}")
                        return False
                    
                    render_result = render_data.get('data', {}).get('pages', {}).get('render', {}).get('responseResult', {})
                    
                    if not render_result.get('succeeded', False):
                        logger.error(f"\n❌ Failed to render page: {render_result.get('message', 'Unknown error')}")
                        return False
                    
                    logger.info("\n✅ Successfully rendered page")
                    return True
                
    except Exception as e:
        logger.error(f"❌ Error in update_wiki_page: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        return False

async def start_discord():
    """Start the Discord client"""
    try:
        print("\n🔄 Starting Discord client...")
        await client.start(TOKEN)
    except discord.LoginFailure:
        print("\n❌ Failed to log in to Discord!")
        raise
    except Exception as e:
        print(f"\n❌ Connection error: {type(e).__name__}")
        raise

async def start_api():
    """Start the FastAPI server"""
    try:
        # Log configuration clearly for debugging
        logger.info("\n=== FastAPI Server Configuration ===")
        logger.info(f"Host: 0.0.0.0")
        logger.info(f"PORT env variable: {os.getenv('PORT')}")
        port_to_use = int(os.getenv('PORT', '80'))
        logger.info(f"Using port: {port_to_use}")
        
        # Add a health check endpoint
        @app.get("/health")
        async def health_check():
            """Health check endpoint for Azure"""
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
        
        # Configure Uvicorn with proper settings for Azure
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",  # Bind to all interfaces
            port=port_to_use,
            log_level="info",
            access_log=True,
            timeout_keep_alive=65,  # Increased timeout for Azure health checks
        )
        
        logger.info("Starting Discord client in background...")
        asyncio.create_task(start_discord())
        
        logger.info(f"🚀 Starting FastAPI server...")
        server = uvicorn.Server(config)
        await server.serve()
    except Exception as e:
        logger.error(f"❌ Failed to start FastAPI server: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        raise

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_discord())
    loop.run_until_complete(start_api())
