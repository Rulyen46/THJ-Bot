import os
import discord
from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from dotenv import load_dotenv
from datetime import datetime, timedelta
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
import importlib.util
import traceback
from collections import defaultdict

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
stdout_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'))
root_logger.addHandler(stdout_handler)

logger = logging.getLogger(__name__)

# Initial startup log
logger.info("=== API LOGGING TEST: This should appear in Azure ===")
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
    logger.warning(
        "EXP_BOOST_CHANNEL_ID not set - exp boost functionality will be disabled")

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

# Add path for changelog processing state
PROCESSING_STATE_PATH = "/app/changelog_processing_state.json"


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
        request_log = f"API Request #{request_id} | {request.method} {request.url.path} | From: {client_ip} | Auth: {auth_status}"
        
        # Use both logging methods for maximum visibility
        logger.info(request_log)
        print(request_log, file=sys.stderr, flush=True)

        # Process the request and measure time
        start_time = time.time()
        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            # Log successful response
            response_log = (
                f"API Response #{request_id} | {request.method} {request.url.path} | "
                f"Status: {response.status_code} | Time: {process_time:.3f}s | Size: {response.headers.get('content-length', 'unknown')}"
            )
            
            # Use multiple logging methods to ensure visibility in Azure
            logger.info(response_log)
            # Also print directly to stderr for maximum visibility in Azure logs
            print(response_log, file=sys.stderr, flush=True)

            return response
        except Exception as e:
            # Log exceptions
            process_time = time.time() - start_time
            error_log = (
                f"API Error #{request_id} | {request.method} {request.url.path} | "
                f"Error: {str(e)} | Time: {process_time:.3f}s"
            )
            
            # Use both logging methods for visibility
            logger.error(error_log)
            print(f"\n❌ {error_log}\n", file=sys.stderr, flush=True)
            # Log the traceback as well for better debugging
            logger.error(traceback.format_exc())
            print(traceback.format_exc(), file=sys.stderr, flush=True)
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
                logger.info(
                    "Fetching messages from Discord changelog channel...")
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
                    logger.info(
                        f"Found {len(messages)} changelog entries, updating the file...")

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

                    logger.info(
                        "✅ Successfully populated changelog.md with all entries!")
                else:
                    logger.info(
                        "No changelog entries found to populate the file.")
            else:
                logger.warning(
                    "Discord client or changelog channel not ready, skipping automatic population")
                logger.info(
                    "The file will be populated when you call /generate-markdown endpoint manually")
        except Exception as e:
            logger.error(
                f"Error populating changelog.md with entries: {str(e)}")
            logger.info(
                "You can still manually update using the /generate-markdown endpoint")

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
            logger.info(
                f"✓ ServerStatus.md already exists at {SERVER_STATUS_PATH}")

        # Now populate the file with the latest EXP boost data from Discord
        logger.info("Fetching latest EXP boost status to populate the file...")
        try:
            # Wait a bit for the Discord client to be ready
            await asyncio.sleep(5)

            if client.is_ready() and exp_boost_channel:
                # Fetch the latest message directly from Discord
                logger.info(
                    "Fetching message from Discord EXP boost channel...")
                messages = [message async for message in exp_boost_channel.history(limit=1)]

                if messages:
                    latest_message = messages[0]

                    # Generate the entry
                    logger.info(
                        "Creating ServerStatus.md entry from latest message...")
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
                        logger.error(
                            f"Error saving last_exp_boost.json: {str(e)}")

                    logger.info(
                        "✅ Successfully populated ServerStatus.md with latest EXP boost status!")
                else:
                    logger.info(
                        "No EXP boost entries found to populate the file.")
            else:
                logger.warning(
                    "Discord client or exp_boost_channel not ready, skipping automatic population")
                logger.info(
                    "The file will be populated when a new message arrives in the EXP boost channel")
        except Exception as e:
            logger.error(
                f"Error populating ServerStatus.md with latest status: {str(e)}")

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
                raise HTTPException(
                    status_code=404, detail="ServerStatus.md file not found")

        # Read the ServerStatus file content
        with open(SERVER_STATUS_PATH, "r") as md_file:
            content = md_file.read()

        # Extract the EXP boost status information using regex
        # Improved regex pattern to handle different line endings and optional whitespace
        exp_boost_pattern = r"## EXP Boost Status\s*\r?\n\*\*Channel ID:\*\* (\d+)\s*\r?\n\*\*Channel Name:\*\* (.*?)\s*\r?\n\*\*Last Updated:\*\* (.*?)\s*\r?\n\*\*Status:\*\* (.*?)(?=\n\n|\r\n\r\n|\Z)"
        match = re.search(exp_boost_pattern, content, re.DOTALL)

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
                    logger.error(
                        f"Failed to fetch server status. Status: {response.status}")
                    raise HTTPException(
                        status_code=503,
                        detail="Failed to fetch server status"
                    )

                data = await response.json()
                logger.info("Successfully fetched server data")

                # Find the Heroes' Journey server
                server = next(
                    (s for s in data if "Heroes' Journey [Multiclass" in s.get(
                        'server_long_name', '')),
                    None
                )

                if not server:
                    logger.warning(
                        "Heroes' Journey server not found in response")
                    return {
                        "status": "success",
                        "found": False,
                        "message": "Server not found in response"
                    }

                logger.info(f"Found server: {server.get('server_long_name')}")
                logger.info(f"Players online: {server.get('players_online')}")

                return {
                    "status": "success",
                    "found": True,
                    "server": {
                        "name": server.get('server_long_name'),
                        "players_online": server.get('players_online'),
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
            raise HTTPException(
                status_code=503, detail="Discord client is not ready")

        if not changelog_channel:
            raise HTTPException(
                status_code=503, detail="Changelog channel not found")

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
            raise HTTPException(
                status_code=404, detail="Changelog file not found")

        # Read the changelog file content
        with open(CHANGELOG_PATH, "r") as md_file:
            content = md_file.read()

        # Parse the content into changelog entries with complete raw content
        messages = []

        # Use regex pattern to find entries
        entry_pattern = r"## Entry (\d+)[\s\S]*?(?=\n## Entry|$)"
        entry_matches = re.finditer(entry_pattern, content)

        for match in entry_matches:
            full_entry = match.group(0).strip()
            entry_id = match.group(1)

            # Extract author and date
            author_match = re.search(r"\*\*Author:\*\* (.*?)\n", full_entry)
            date_match = re.search(r"\*\*Date:\*\* (.*?)\n", full_entry)

            author = author_match.group(1) if author_match else "Unknown"
            timestamp = date_match.group(1) if date_match else "Unknown"

            # Get content part (everything after the header metadata)
            content_part = re.sub(
                r"^## Entry \d+\s+\*\*Author:\*\* .*?\s+\*\*Date:\*\* .*?\s+\n", "", full_entry, flags=re.DOTALL)

            messages.append({
                "id": entry_id,
                "content": content_part.strip(),
                "author": author,
                "timestamp": timestamp,
                "raw": full_entry
            })

        # Log a summary instead of each individual entry
        entry_ids = [m["id"] for m in messages]
        if entry_ids:
            logger.info(
                f"Found {len(entry_ids)} changelog entries (IDs from {entry_ids[0]} to {entry_ids[-1]})")
        else:
            logger.info("No changelog entries found")

        # Sort messages by ID (chronological order)
        messages.sort(key=lambda x: int(x["id"]))

        # Filter based on message_id if provided
        if message_id:
            try:
                reference_id = int(message_id)
                filtered_messages = [
                    m for m in messages if int(m["id"]) > reference_id]
                logger.info(
                    f"Filtered to {len(filtered_messages)} entries after ID: {reference_id}")
                messages = filtered_messages
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid message ID format")
        elif not all:
            # If not all and no message_id, get only the latest
            if messages:
                messages = [messages[-1]]
                logger.info(
                    f"Returning only the latest changelog: {messages[0]['id']}")

        return {
            "status": "success",
            "changelogs": messages,
            "total": len(messages)
        }

    except Exception as e:
        logger.error(f"Error fetching changelogs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
async def create_wiki_page(title: str, path: str, content: str) -> bool:
    """
    Create a new wiki page or update if it exists.
    Returns True if successful, False otherwise.
    """
    try:
        headers = {
            'Authorization': f'Bearer {WIKI_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # First, check if page exists
        check_query = """
        query GetPageByPath($path: String!) {
          pages {
            singleByPath(path: $path, locale: "en") {
              id
            }
          }
        }
        """
        
        check_variables = {
            "path": path
        }
        
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Check if page exists
            async with session.post(
                WIKI_API_URL,
                json={"query": check_query, "variables": check_variables},
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    existing_page = data.get('data', {}).get('pages', {}).get('singleByPath')
                    
                    if existing_page and existing_page.get('id'):
                        # Page exists, update it
                        logger.info(f"Page {path} exists with ID {existing_page['id']}, updating...")
                        return await update_wiki_page(content, existing_page['id'])
                    else:
                        # Page doesn't exist, create it
                        logger.info(f"Page {path} doesn't exist, creating...")
                        
                        create_mutation = """
                        mutation CreatePage($input: PageCreateInput!) {
                          pages {
                            create(input: $input) {
                              responseResult {
                                succeeded
                                errorCode
                                message
                              }
                              page {
                                id
                                path
                                title
                              }
                            }
                          }
                        }
                        """
                        
                        create_variables = {
                            "input": {
                                "title": title,
                                "path": path,
                                "content": content,
                                "locale": "en",
                                "isPublished": True,
                                "isPrivate": False
                            }
                        }
                        
                        async with session.post(
                            WIKI_API_URL,
                            json={"query": create_mutation, "variables": create_variables},
                            headers=headers
                        ) as create_response:
                            if create_response.status == 200:
                                create_data = await create_response.json()
                                
                                if 'errors' in create_data:
                                    logger.error(f"GraphQL errors creating page: {create_data['errors']}")
                                    return False
                                
                                result = create_data.get('data', {}).get('pages', {}).get('create', {})
                                response_result = result.get('responseResult', {})
                                
                                if response_result.get('succeeded', False):
                                    logger.info(f"Successfully created page: {path}")
                                    return True
                                else:
                                    logger.error(f"Failed to create page: {response_result.get('message', 'Unknown error')}")
                                    return False
                            else:
                                logger.error(f"HTTP error creating page: {create_response.status}")
                                return False
                else:
                    error_text = await create_response.text()
                    logger.error(f"HTTP error creating page: {create_response.status} - {error_text}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error in create_wiki_page: {str(e)}")
        logger.error(traceback.format_exc())
        return False
    
async def organize_changelogs_by_month(all_entries):
    """
    Organize changelog entries by month for creating separate wiki pages.
    """
    entries_by_month = defaultdict(list)
    
    for entry in all_entries:
        try:
            entry_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
            month_key = entry_date.strftime("%Y-%m")
            entries_by_month[month_key].append(entry)
        except:
            # Fallback for entries with invalid timestamps
            entries_by_month["unknown"].append(entry)
    
    return entries_by_month
    
async def get_wiki_page_content(page_id: int) -> str:
    """
    Fetch the current content of a wiki page.
    Returns the page content as a string, or None if failed.
    """
    try:
        headers = {
            'Authorization': f'Bearer {WIKI_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # GraphQL query to fetch page content
        query = """
        query GetPage($id: Int!) {
          pages {
            single(id: $id) {
              content
              updatedAt
            }
          }
        }
        """
        
        variables = {
            "id": page_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                WIKI_API_URL,
                json={"query": query, "variables": variables},
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'errors' in data:
                        logger.error(f"GraphQL errors fetching wiki page: {data['errors']}")
                        return None
                    
                    page_data = data.get('data', {}).get('pages', {}).get('single', {})
                    return page_data.get('content', '')
                else:
                    logger.error(f"Failed to fetch wiki page: HTTP {response.status}")
                    return None
                    
    except Exception as e:
        logger.error(f"Error fetching wiki page content: {str(e)}")
        return None

def parse_existing_changelog_ids(wiki_content: str) -> set:
    """
    Parse the wiki content to extract existing changelog entry IDs.
    Returns a set of entry IDs that are already in the wiki.
    """
    existing_ids = set()
    
    # Look for entry IDs in the wiki content
    import re
    
    # Multiple patterns to catch different formats
    patterns = [
        r'Entry ID:\s*(\d+)',  # Entry ID: 1234567890
        r'Entry\s+(\d+)',      # Entry 1234567890
        r'Message ID:\s*(\d+)', # Message ID: 1234567890
        r'## Entry (\d+)',     # ## Entry 1234567890 (changelog.md format)
        r'## \d{4}-\d{2}-\d{2} \d{2}:\d{2} - Entry (\d+)',  # ## 2024-02-24 02:59 - Entry 1234567890 (wiki format)
        r'- Entry (\d+)',      # - Entry 1234567890
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, wiki_content, re.IGNORECASE)
        existing_ids.update(matches)
    
    logger.info(f"Found {len(existing_ids)} existing entries in wiki")
    return existing_ids

async def update_wiki_with_new_entries(new_entries):
    """
    Update the wiki with new changelog entries while maintaining monthly archive structure.
    """
    if not all([WIKI_API_URL, WIKI_API_KEY, WIKI_PAGE_ID]):
        logger.info("Wiki integration not configured, skipping wiki update")
        return False
        
    try:
        # First, check if we should update the monthly archives
        # (This happens if new entries span multiple months or are older than 30 days)
        needs_archive_update = False
        cutoff_date = datetime.now() - timedelta(days=30)
        
        months_affected = set()
        for entry in new_entries:
            try:
                entry_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                month_key = entry_date.strftime("%Y-%m")
                months_affected.add(month_key)
                
                if entry_date < cutoff_date:
                    needs_archive_update = True
            except:
                pass
        
        # If entries affect multiple months or are old, recreate the entire structure
        if needs_archive_update or len(months_affected) > 1:
            logger.info("New entries affect archives, rebuilding monthly structure...")
            # Call the create monthly archives function
            result = await create_wiki_monthly_archives()
            return result.get("status") == "success"
        
        # Otherwise, just update the main page with recent entries
        logger.info("Updating main page with recent entries only...")
        
        # Get all changelogs to build the complete recent view
        changelogs_response = await get_changelog(all=True)
        all_entries = changelogs_response.get("changelogs", [])
        
        # Filter to last 30 days
        recent_entries = []
        for entry in all_entries:
            try:
                entry_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                if entry_date >= cutoff_date:
                    recent_entries.append(entry)
            except:
                pass
        
        # Sort by ID descending
        recent_entries.sort(key=lambda x: int(x['id']), reverse=True)
        
        # Build main page content
        main_page_content = WIKI_HEADER + "\n\n"
        main_page_content += "## Recent Updates (Last 30 Days)\n\n"
        
        if recent_entries:
            for entry in recent_entries:
                try:
                    entry_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
                except:
                    entry_time = entry["timestamp"]
                    
                main_page_content += f"### {entry_time} - Entry {entry['id']}\n"
                main_page_content += f"**Author:** {entry['author']}\n\n"
                
                # Clean Discord mentions
                content = entry['content'].strip()
                cleaned_content = clean_discord_mentions(content)
                
                # Truncate very long entries
                if len(cleaned_content) > 500:
                    cleaned_content = cleaned_content[:500] + "..."
                    try:
                        entry_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                        entry_month = entry_date.strftime("%Y-%m")
                        cleaned_content += f"\n\n[View full entry →](/en/changelog-{entry_month}#entry-{entry['id']})"
                    except:
                        pass
                
                main_page_content += cleaned_content + "\n\n---\n\n"
        else:
            main_page_content += "*No updates in the last 30 days.*\n\n"
        
        # Add archive links section
        main_page_content += "\n## Monthly Archives\n\n"
        main_page_content += "Browse older updates organized by month:\n\n"
        
        # Get all entries to build archive list
        entries_by_month = await organize_changelogs_by_month(all_entries)
        
        # Group archives by year
        archives_by_year = defaultdict(list)
        for month_key in sorted(entries_by_month.keys(), reverse=True):
            if month_key == "unknown":
                continue
            try:
                month_date = datetime.strptime(month_key, "%Y-%m")
                month_name = month_date.strftime("%B %Y")
                year = month_key[:4]
                
                # Check if this month has recent entries
                has_recent = False
                for entry in entries_by_month[month_key]:
                    try:
                        entry_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                        if entry_date >= cutoff_date:
                            has_recent = True
                            break
                    except:
                        pass
                
                archives_by_year[year].append({
                    "month_key": month_key,
                    "month_name": month_name,
                    "entry_count": len(entries_by_month[month_key]),
                    "has_recent": has_recent
                })
            except:
                pass
        
        # Display archives grouped by year
        for year in sorted(archives_by_year.keys(), reverse=True):
            main_page_content += f"\n### {year}\n"
            for archive in archives_by_year[year]:
                page_path = f"changelog-{archive['month_key']}"
                icon = "📍" if archive['has_recent'] else "📄"
                main_page_content += f"- {icon} [{archive['month_name']}](/en/{page_path}) - {archive['entry_count']} updates\n"
        
        # Add search tip
        main_page_content += "\n---\n\n"
        main_page_content += "*💡 Tip: Use the search function (top right) to find specific updates across all archives.*\n"
        
        # Update main page
        page_id = int(WIKI_PAGE_ID)
        success = await update_wiki_page(main_page_content, page_id)
        
        if success:
            logger.info(f"Successfully updated wiki main page with {len(recent_entries)} recent entries")
            
            # If this is a new month, create its archive page
            for month_key in months_affected:
                if month_key in entries_by_month and month_key != "unknown":
                    month_entries = entries_by_month[month_key]
                    month_entries.sort(key=lambda x: int(x['id']), reverse=True)
                    
                    try:
                        month_date = datetime.strptime(month_key, "%Y-%m")
                        month_name = month_date.strftime("%B %Y")
                        page_title = f"Changelog - {month_name}"
                        page_path = f"changelog-{month_key}"
                        
                        # Build month page content
                        month_content = f"# {page_title}\n\n"
                        month_content += f"[← Back to Recent Updates](/en/Change-log-history)\n\n"
                        month_content += "---\n\n"
                        month_content += f"*{len(month_entries)} updates in {month_name}*\n\n"
                        
                        for entry in month_entries:
                            try:
                                entry_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
                            except:
                                entry_time = entry["timestamp"]
                                
                            month_content += f"<a name=\"entry-{entry['id']}\"></a>\n\n"
                            month_content += f"## {entry_time} - Entry {entry['id']}\n"
                            month_content += f"**Author:** {entry['author']}\n\n"
                            
                            content = entry['content'].strip()
                            cleaned_content = clean_discord_mentions(content)
                            
                            month_content += cleaned_content + "\n\n---\n\n"
                        
                        # Create or update the monthly page
                        logger.info(f"Creating/updating archive page for {month_name}...")
                        await create_wiki_page(page_title, page_path, month_content)
                        
                    except Exception as e:
                        logger.error(f"Error creating archive for month {month_key}: {str(e)}")
            
            return True
        else:
            logger.error("Failed to update wiki main page")
            return False
        
    except Exception as e:
        logger.error(f"Error updating wiki with new entries: {str(e)}")
        logger.error(traceback.format_exc())
        return False

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
        logger.info(
            f"- Last 100 chars: {content[-100:] if len(content) > 100 else content}")
        logger.info("- Number of lines: {}".format(content.count('\n') + 1))

        # Update mutation with isPublished
        update_mutation = """
        mutation UpdatePage($id: Int!, $input: PageUpdateInput!) {
          pages {
            update(id: $id, input: $input) {
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
            "input": {
                "content": content,
                "isPublished": True
            }
        }

        # Log request details
        logger.info("\nRequest Details:")
        logger.info(f"- API URL: {WIKI_API_URL}")
        logger.info(f"- Update Mutation: {update_mutation.strip()}")
        logger.info(
            f"- Variables: id={page_id}, content_length={len(content)}")

        # Add timeout to prevent hanging
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Step 1: Update content with isPublished
            logger.info("\nExecuting update mutation...")
            try:
                async with session.post(
                    WIKI_API_URL,
                    json={"query": update_mutation, "variables": variables},
                    headers=headers
                ) as response:
                    response_status = response.status
                    response_text = await response.text()
                    
                    logger.info(f"\nUpdate Response Analysis:")
                    logger.info(f"- HTTP Status: {response_status}")
                    
                    # Try to parse as JSON
                    try:
                        response_data = json.loads(response_text)
                        logger.info(
                            f"- Raw Response: {json.dumps(response_data, indent=2)}")
                    except json.JSONDecodeError:
                        logger.error(f"- Raw Response (not JSON): {response_text[:500]}")
                        return False

                    if 'errors' in response_data:
                        logger.error("\nGraphQL Errors in update:")
                        for error in response_data['errors']:
                            logger.error(f"- Path: {error.get('path', 'N/A')}")
                            logger.error(
                                f"- Message: {error.get('message', 'N/A')}")
                            logger.error(
                                f"- Extensions: {error.get('extensions', {})}")
                        return False

                    update_result = response_data.get('data', {}).get(
                        'pages', {}).get('update', {}).get('responseResult', {})

                    # Check if update was successful
                    if update_result.get('succeeded', False):
                        logger.info(f"\n✅ Successfully updated page")
                        logger.info(f"- Slug: {update_result.get('slug', 'N/A')}")
                        logger.info(f"- Message: {update_result.get('message', 'N/A')}")
                        return True
                    else:
                        # Handle the known 'map' error
                        if update_result.get('message') == "Cannot read properties of undefined (reading 'map')":
                            logger.warning(
                                "\n⚠️ Received 'map' error - this might be a Wiki.js bug but the update may have succeeded")
                            # You might want to verify the update by fetching the page
                            return True
                        else:
                            logger.error(
                                f"\n❌ Failed to update page: {update_result.get('message', 'Unknown error')}")
                            logger.error(f"- Error Code: {update_result.get('errorCode', 'N/A')}")
                            return False
                            
            except asyncio.TimeoutError:
                logger.error("\n❌ Request timed out after 30 seconds")
                return False
            except aiohttp.ClientError as e:
                logger.error(f"\n❌ HTTP Client Error: {str(e)}")
                return False

    except Exception as e:
        logger.error(f"❌ Error in update_wiki_page: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        logger.error(traceback.format_exc())
        return False
    
def clean_discord_mentions(content):
    """
    Remove Discord user mentions from changelog content.
    Removes patterns like ( <@123456789> ) from the end of lines.
    Also handles @ mentions like (@Username).
    """
    # Remove Discord user ID mentions in format ( <@123456789> )
    # This regex matches the pattern with optional spaces
    content = re.sub(r'\s*\(\s*<@\d+>\s*\)', '', content)
    
    # Remove @ mentions in format ( @Username)
    content = re.sub(r'\s*\(\s*@[\w\s]+\)', '', content)
    
    # Clean up any trailing spaces left behind
    lines = content.split('\n')
    cleaned_lines = [line.rstrip() for line in lines]
    
    return '\n'.join(cleaned_lines)

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


# Changelog monitoring with debouncing
class ChangelogMonitor:
    """Monitor changelog.md for changes and batch process updates with debouncing"""
    
    def __init__(self):
        self.last_processed_entry_id = None
        self.pending_entries = []
        self.debounce_timer = None
        self.file_last_modified = None
        self.monitoring_active = True
        self.file_hash = None
        self.load_state()
        
    def load_state(self):
        """Load processing state from file"""
        try:
            if os.path.exists(PROCESSING_STATE_PATH):
                with open(PROCESSING_STATE_PATH, 'r') as f:
                    state = json.load(f)
                    self.last_processed_entry_id = state.get('last_processed_entry_id')
                    logger.info(f"Loaded state: last processed entry {self.last_processed_entry_id}")
        except Exception as e:
            logger.error(f"Error loading processing state: {str(e)}")
    
    def save_state(self):
        """Save processing state to file"""
        try:
            state = {
                'last_processed_entry_id': self.last_processed_entry_id,
                'last_updated': datetime.now().isoformat()
            }
            with open(PROCESSING_STATE_PATH, 'w') as f:
                json.dump(state, f, indent=2)
            logger.info(f"Saved state: last processed entry {self.last_processed_entry_id}")
        except Exception as e:
            logger.error(f"Error saving processing state: {str(e)}")
    
    async def detect_new_entries(self):
        """Detect new entries in changelog.md"""
        try:
            if not os.path.exists(CHANGELOG_PATH):
                return []
            
            # Read the changelog file
            with open(CHANGELOG_PATH, 'r') as f:
                content = f.read()
            
            # Parse entries
            new_entries = []
            entry_pattern = r"## Entry (\d+)\n\*\*Author:\*\* (.*?)\n\*\*Date:\*\* (.*?)\n\n([\s\S]*?)(?=\n---\n|$)"
            
            for match in re.finditer(entry_pattern, content):
                entry_id = match.group(1)
                author = match.group(2)
                timestamp = match.group(3)
                entry_content = match.group(4).strip()
                
                # Check if this is a new entry
                if self.last_processed_entry_id is None or int(entry_id) > int(self.last_processed_entry_id):
                    new_entries.append({
                        'id': entry_id,
                        'author': author,
                        'timestamp': timestamp,
                        'content': entry_content
                    })
            
            # Sort by ID to ensure correct order
            new_entries.sort(key=lambda x: int(x['id']))
            
            if new_entries:
                logger.info(f"Detected {len(new_entries)} new entries")
                
            return new_entries
            
        except Exception as e:
            logger.error(f"Error detecting new entries: {str(e)}")
            logger.error(traceback.format_exc())
            return []
    
    async def monitor_changelog_file(self):
        """Monitor changelog.md for changes with debouncing"""
        logger.info("Starting changelog file monitor")
        
        # Initial check for any unprocessed entries
        initial_entries = await self.detect_new_entries()
        if initial_entries:
            logger.info(f"Found {len(initial_entries)} unprocessed entries on startup")
            await self.handle_new_entries(initial_entries)
        
        while self.monitoring_active:
            try:
                if not os.path.exists(CHANGELOG_PATH):
                    await asyncio.sleep(5)
                    continue
                
                # Check file modification time
                current_mtime = os.path.getmtime(CHANGELOG_PATH)
                
                # Also check file content hash for more reliable change detection
                with open(CHANGELOG_PATH, 'rb') as f:
                    import hashlib
                    current_hash = hashlib.md5(f.read()).hexdigest()
                
                if (self.file_last_modified and current_mtime > self.file_last_modified) or \
                   (self.file_hash and current_hash != self.file_hash):
                    # File has changed
                    logger.info("Changelog file change detected")
                    new_entries = await self.detect_new_entries()
                    
                    if new_entries:
                        await self.handle_new_entries(new_entries)
                
                self.file_last_modified = current_mtime
                self.file_hash = current_hash
                
                await asyncio.sleep(5)  # Check every 5 seconds
                
            except Exception as e:
                logger.error(f"Error monitoring changelog: {str(e)}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(5)
    
    async def handle_new_entries(self, new_entries):
        """Handle new entries with debouncing"""
        # Add new entries to pending list (avoid duplicates)
        existing_ids = {e['id'] for e in self.pending_entries}
        for entry in new_entries:
            if entry['id'] not in existing_ids:
                self.pending_entries.append(entry)
        
        # Log the first entry if this is a new batch
        if self.debounce_timer is None and self.pending_entries:
            logger.info(f"First new entry detected: {self.pending_entries[0]['id']} by {self.pending_entries[0]['author']}")
        
        # Cancel existing timer if any
        if self.debounce_timer and not self.debounce_timer.done():
            self.debounce_timer.cancel()
            logger.info(f"Timer reset. Now tracking {len(self.pending_entries)} pending entries")
        
        # Start new 5-minute timer
        logger.info(f"Starting 5-minute timer for {len(self.pending_entries)} entries")
        self.debounce_timer = asyncio.create_task(self.process_after_delay())
    
    async def process_after_delay(self):
        """Wait for 5 minutes then process all pending entries"""
        try:
            logger.info(f"Waiting 5 minutes before processing {len(self.pending_entries)} entries")
            await asyncio.sleep(300)  # 5 minutes
            
            # Process all pending entries
            await self.process_pending_entries()
            
        except asyncio.CancelledError:
            logger.info("Timer cancelled - new entries detected")
            raise
    
    async def process_pending_entries(self):
        """Process all accumulated entries"""
        if not self.pending_entries:
            return
        
        logger.info(f"Processing {len(self.pending_entries)} changelog entries")
        force_azure_log(f"Processing batch of {len(self.pending_entries)} changelog entries")
        
        try:
            # Sort by ID to ensure correct order (ascending for processing)
            self.pending_entries.sort(key=lambda x: int(x['id']))
            
            # Get the latest entry for primary operations
            latest_entry = self.pending_entries[-1]
            
            # Process Reddit posting if configured
            if await self.should_post_to_reddit():
                await self.post_batch_to_reddit(latest_entry)
            
            # Update Wiki with new entries if configured
            # The wiki update function will handle reverse ordering internally
            if await self.should_update_wiki():
                await update_wiki_with_new_entries(self.pending_entries)
            
            # Update last processed ID
            self.last_processed_entry_id = latest_entry['id']
            self.save_state()
            
            logger.info(f"Successfully processed entries up to {self.last_processed_entry_id}")
            
            # Clear pending entries and timer
            self.pending_entries = []
            self.debounce_timer = None
            
        except Exception as e:
            logger.error(f"Error processing entries: {str(e)}")
            logger.error(traceback.format_exc())
            # Don't clear pending entries on error - we'll retry
    
    async def should_post_to_reddit(self):
        """Check if Reddit posting is configured and enabled"""
        return all([
            os.getenv('REDDIT_CLIENT_ID'),
            os.getenv('REDDIT_CLIENT_SECRET'),
            os.getenv('REDDIT_USERNAME'),
            os.getenv('REDDIT_PASSWORD'),
            os.getenv('REDDIT_SUBREDDIT')
        ])
    
    async def should_update_wiki(self):
        """Check if Wiki updating is configured and enabled"""
        return all([WIKI_API_URL, WIKI_API_KEY, WIKI_PAGE_ID])
    
    async def post_batch_to_reddit(self, latest_entry):
        """Post the latest entry to Reddit (which will check for batching)"""
        try:
            reddit_poster = import_reddit_poster()
            if not reddit_poster:
                logger.error("Failed to import Reddit poster")
                return
            
            logger.info(f"Posting to Reddit: entry {latest_entry['id']}")
            success, message = await reddit_poster.post_changelog_to_reddit(latest_entry)
            
            if success:
                logger.info(f"Reddit post successful: {message}")
            else:
                logger.error(f"Reddit post failed: {message}")
                
        except Exception as e:
            logger.error(f"Error posting to Reddit: {str(e)}")
            logger.error(traceback.format_exc())
    
    async def update_wiki_with_entries(self):
        """Update Wiki with all changelogs"""
        try:
            logger.info("Updating Wiki with latest changelogs")
            
            # Get all changelogs
            changelogs = await get_changelog(all=True)
            
            if not changelogs["total"]:
                logger.warning("No changelogs found for Wiki update")
                return
            
            # Format all changelogs for wiki
            formatted_content = WIKI_HEADER + "\n\n"
            for changelog in changelogs["changelogs"]:
                # Add formatted content
                formatted_content += f"## {changelog['timestamp']}\n"
                formatted_content += f"**Author:** {changelog['author']}\n\n"
                formatted_content += changelog['content'] + "\n\n"
                formatted_content += "---\n\n"
            
            # Update the wiki page
            page_id = int(WIKI_PAGE_ID)
            success = await update_wiki_page(formatted_content, page_id)
            
            if success:
                logger.info(f"Wiki updated with {changelogs['total']} entries")
            else:
                logger.error("Failed to update Wiki")
                
        except Exception as e:
            logger.error(f"Error updating Wiki: {str(e)}")
            logger.error(traceback.format_exc())
    
    async def force_process(self):
        """Force immediate processing of pending entries"""
        if self.debounce_timer and not self.debounce_timer.done():
            self.debounce_timer.cancel()
        
        if self.pending_entries:
            await self.process_pending_entries()
            return True
        return False


async def start_api():
    """Start the FastAPI server"""
    try:
        # Global startup time for uptime tracking
        global startup_time
        startup_time = time.time()
        
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
            now = datetime.now()
            
            # Log the health check with our enhanced logging
            force_azure_log(f"Health check request received at {now.isoformat()}")
            
            # Collect additional health data
            health_data = {
                "status": "healthy",
                "timestamp": now.isoformat(),
                "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "discord_connected": client.is_ready() if hasattr(client, "is_ready") else False,
                "api_version": "1.0.1",
                "uptime": time.time() - startup_time if 'startup_time' in globals() else 0
            }
            
            # Add API endpoint metrics
            if hasattr(app, "routes"):
                health_data["endpoints"] = len(app.routes)
                
            # Force log the response too
            force_azure_log(f"Health check response: {json.dumps(health_data)}")
            
            return health_data

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

# Create the changelog monitor instance
changelog_monitor = ChangelogMonitor()

# Changelog monitoring startup
@app.on_event("startup")
async def start_changelog_monitor():
    """Start the changelog monitoring task"""
    asyncio.create_task(changelog_monitor.monitor_changelog_file())
    logger.info("Changelog monitor started with 5-minute debouncing")
    force_azure_log("Changelog monitor started - will batch process updates with 5-minute delay")

# Monitor endpoints
@app.post("/process-pending", dependencies=[Depends(verify_token)])
async def process_pending_manually():
    """Manually trigger processing of pending entries"""
    if await changelog_monitor.force_process():
        return {
            "status": "success", 
            "message": f"Processed {len(changelog_monitor.pending_entries)} entries"
        }
    return {"status": "success", "message": "No pending entries to process"}

@app.get("/monitor-status", dependencies=[Depends(verify_token)])
async def get_monitor_status():
    """Get current monitoring status"""
    timer_remaining = None
    if changelog_monitor.debounce_timer and not changelog_monitor.debounce_timer.done():
        # This is approximate since we can't easily track exact remaining time
        timer_remaining = "Active (up to 5 minutes remaining)"
    
    return {
        "monitoring_active": changelog_monitor.monitoring_active,
        "last_processed_entry": changelog_monitor.last_processed_entry_id,
        "pending_entries_count": len(changelog_monitor.pending_entries),
        "pending_entries": [
            {"id": e['id'], "author": e['author'], "timestamp": e['timestamp']} 
            for e in changelog_monitor.pending_entries
        ],
        "timer_active": changelog_monitor.debounce_timer is not None and not changelog_monitor.debounce_timer.done(),
        "timer_status": timer_remaining,
        "file_last_modified": datetime.fromtimestamp(changelog_monitor.file_last_modified).isoformat() if changelog_monitor.file_last_modified else None
    }

@app.post("/monitor-control", dependencies=[Depends(verify_token)])
async def control_monitor(action: str):
    """Control the monitoring system"""
    if action == "pause":
        changelog_monitor.monitoring_active = False
        return {"status": "success", "message": "Monitoring paused"}
    elif action == "resume":
        changelog_monitor.monitoring_active = True
        return {"status": "success", "message": "Monitoring resumed"}
    elif action == "reset":
        # Reset state but keep last processed ID
        changelog_monitor.pending_entries = []
        if changelog_monitor.debounce_timer:
            changelog_monitor.debounce_timer.cancel()
        changelog_monitor.debounce_timer = None
        return {"status": "success", "message": "Monitor state reset"}
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'pause', 'resume', or 'reset'")

# Reddit posting with duplicate checking and batching
def import_reddit_poster():
    """Import the Reddit poster module."""
    try:
        spec = importlib.util.spec_from_file_location(
            "reddit_poster", "/app/reddit_poster.py")
        reddit_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reddit_module)
        return reddit_module
    except Exception as e:
        logger.error(f"Error importing Reddit poster: {str(e)}")
        logger.error(traceback.format_exc())
        return None


@app.post("/reddit/post-changelog", dependencies=[Depends(verify_token)])
async def post_to_reddit(entry_id: Optional[str] = None, force: bool = False, batch: bool = True):
    """
    Post a changelog entry to Reddit with duplicate checking and optional batching.
    If no entry_id is provided, posts the latest entry.
    
    Parameters:
    - entry_id: Specific entry ID to post (optional)
    - force: If True, bypasses duplicate checking and monitor warnings (optional)
    - batch: If True, includes nearby entries in the same post (default: True)
    
    Requires X-Patcher-Token header for authentication.
    """
    try:
        # Check monitor state first
        if changelog_monitor.pending_entries and not force:
            raise HTTPException(
                status_code=409,
                detail=f"Monitor has {len(changelog_monitor.pending_entries)} pending entries. "
                       f"Use force=true to override or wait for automatic processing."
            )
        
        if changelog_monitor.pending_entries and force:
            logger.warning(f"Force posting despite {len(changelog_monitor.pending_entries)} pending entries")
        
        logger.info("\n=== Posting to Reddit ===")
        logger.info(f"Entry ID: {entry_id if entry_id else 'Latest'}")
        logger.info(f"Force mode: {force}")
        logger.info(f"Batch mode: {batch}")

        # Import the Reddit poster
        reddit_poster = import_reddit_poster()
        if not reddit_poster:
            raise HTTPException(
                status_code=500, detail="Failed to import Reddit poster module")

        # Get the entry to post
        if entry_id:
            # Get specific entry
            changelogs = await get_changelog(all=True)
            entry = next(
                (e for e in changelogs["changelogs"] if e["id"] == entry_id), None)
            if not entry:
                raise HTTPException(
                    status_code=404, detail=f"Changelog entry {entry_id} not found")
        else:
            # Get latest entry
            changelogs = await get_changelog(all=False)
            if not changelogs["changelogs"]:
                raise HTTPException(
                    status_code=404, detail="No changelog entries found")
            entry = changelogs["changelogs"][0]

        logger.info(f"Processing entry: {entry['id']} by {entry['author']}")

        # If batch mode is disabled, use the original single-entry logic
        if not batch:
            # Check for duplicates and post single entry
            # (Keep existing single-entry logic here)
            pass
        
        # Post to Reddit using the batching function
        success, message = await reddit_poster.post_changelog_to_reddit(entry, force=force)

        if success:
            # Get the updated post info to return
            posted_entries = reddit_poster.get_posted_entries()
            latest_post = None
            for post in posted_entries.get("posts", []):
                # Check both single entries and batches
                if post.get("entry_id") == entry["id"] or entry["id"] in post.get("entry_ids", []):
                    latest_post = post
                    break
            
            response = {
                "status": "success", 
                "message": message,
                "entry_id": entry["id"]
            }
            
            if latest_post:
                response["post_details"] = {
                    "post_id": latest_post["post_id"],
                    "url": latest_post["url"],
                    "posted_at": latest_post["posted_at"],
                    "flair": latest_post.get("flair", "None"),
                    "batched": latest_post.get("entry_count", 1) > 1,
                    "entry_count": latest_post.get("entry_count", 1)
                }
            
            return response
        else:
            raise HTTPException(status_code=500, detail=message)
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Error posting to Reddit: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/reddit/post-all-entries", dependencies=[Depends(verify_token)])
async def post_all_entries_to_reddit(force: bool = False):
    """
    Post all unpublished changelog entries to Reddit.
    
    Parameters:
    - force: If True, bypasses monitor warnings (optional)
    
    Requires X-Patcher-Token header for authentication.
    """
    try:
        # Check monitor state first
        if changelog_monitor.pending_entries and not force:
            raise HTTPException(
                status_code=409,
                detail=f"Monitor has {len(changelog_monitor.pending_entries)} pending entries. "
                       f"Use force=true to override or wait for automatic processing."
            )
        
        if changelog_monitor.pending_entries and force:
            logger.warning(f"Force posting all entries despite {len(changelog_monitor.pending_entries)} pending entries")
        
        logger.info("\n=== Posting All Unpublished Entries to Reddit ===")

        # Import the Reddit poster
        reddit_poster = import_reddit_poster()
        if not reddit_poster:
            raise HTTPException(
                status_code=500, detail="Failed to import Reddit poster module")

        # Get all changelogs
        changelogs = await get_changelog(all=True)

        if not changelogs["total"]:
            return {"status": "success", "message": "No changelogs found to post"}

        # Get already posted entries
        posted_entries = reddit_poster.get_posted_entries()
        posted_ids = [post["entry_id"]
                      for post in posted_entries.get("posts", [])]

        # Filter out already posted entries
        to_post = [entry for entry in changelogs["changelogs"]
                   if entry["id"] not in posted_ids]

        if not to_post:
            return {"status": "success", "message": "All entries have already been posted"}

        # Post each entry using async function
        results = []
        for entry in to_post:
            success, message = await reddit_poster.post_changelog_to_reddit(entry)
            results.append({
                "entry_id": entry["id"],
                "success": success,
                "message": message
            })

            # Add a small delay to avoid hitting Reddit rate limits
            await asyncio.sleep(2)

        return {
            "status": "success",
            "message": f"Posted {len([r for r in results if r['success']])} of {len(to_post)} entries",
            "results": results
        }
    except Exception as e:
        logger.error(f"Error posting to Reddit: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def check_recent_reddit_posts(entry_id):
    """
    Check if a changelog entry has already been posted to Reddit by scanning recent posts.
    This is a backup check in case our local tracking gets out of sync.
    
    Returns True if duplicate found, False otherwise.
    """
    try:
        # Import the Reddit poster to access functions and variables
        reddit_poster = import_reddit_poster()
        if not reddit_poster:
            logger.warning("Could not import Reddit poster for duplicate checking")
            return False
            
        # Access the functions and constants from the reddit_poster module
        initialize_reddit = reddit_poster.initialize_reddit
        REDDIT_SUBREDDIT = reddit_poster.REDDIT_SUBREDDIT
        
        # Initialize Reddit API
        reddit = await initialize_reddit()
        if not reddit:
            logger.warning("Could not initialize Reddit for duplicate checking")
            return False
        
        subreddit = await reddit.subreddit(REDDIT_SUBREDDIT)
        
        # Check the last 25 posts for duplicates
        post_count = 0
        async for submission in subreddit.new(limit=25):
            post_count += 1
            # Check if the post body contains our entry ID
            if hasattr(submission, 'selftext') and f"Entry ID:** {entry_id}" in submission.selftext:
                logger.warning(f"Found duplicate post for entry {entry_id}: {submission.url}")
                await reddit.close()
                return True
        
        logger.info(f"Checked {post_count} recent posts, no duplicates found for entry {entry_id}")
        await reddit.close()
        return False
        
    except Exception as e:
        logger.error(f"Error checking for duplicate posts: {str(e)}")
        # Don't block posting if duplicate check fails
        return False
    
@app.get("/reddit/posted-entries", dependencies=[Depends(verify_token)])
async def get_posted_entries():
    """
    Get list of all entries that have been posted to Reddit.
    Requires X-Patcher-Token header for authentication.
    """
    try:
        reddit_poster = import_reddit_poster()
        if not reddit_poster:
            raise HTTPException(status_code=500, detail="Failed to import Reddit poster module")
        
        posted_entries = reddit_poster.get_posted_entries()
        
        return {
            "status": "success",
            "total_posted": len(posted_entries.get("posts", [])),
            "posts": posted_entries.get("posts", [])
        }
    except Exception as e:
        logger.error(f"Error getting posted entries: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reddit/test", dependencies=[Depends(verify_token)])
async def test_reddit_posting(background_tasks: BackgroundTasks, 
                              test_mode: bool = True,
                              use_real_data: bool = False,
                              entry_id: Optional[str] = None):
    """
    Test endpoint for Reddit posting functionality.
    
    Parameters:
    - test_mode: If True, runs in simulation mode without actually posting to Reddit
    - use_real_data: If True, uses real changelog data; otherwise uses test data
    - entry_id: If provided, tests with a specific changelog entry
    
    Requires X-Patcher-Token header for authentication.
    """
    try:
        logger.info("\n=== TESTING REDDIT INTEGRATION ===")
        logger.info(f"Test Mode: {test_mode}")
        logger.info(f"Using Real Data: {use_real_data}")
        logger.info(f"Entry ID: {entry_id if entry_id else 'Not specified'}")
        
        # Import the Reddit poster
        reddit_poster = import_reddit_poster()
        if not reddit_poster:
            raise HTTPException(status_code=500, detail="Failed to import Reddit poster module")
        
        # Get test data
        if use_real_data:
            if entry_id:
                changelogs = await get_changelog(all=True)
                test_data = next((e for e in changelogs["changelogs"] if e["id"] == entry_id), None)
                if not test_data:
                    raise HTTPException(status_code=404, detail=f"Changelog entry {entry_id} not found")
            else:
                changelogs = await get_changelog(all=False)
                if not changelogs["changelogs"]:
                    raise HTTPException(status_code=404, detail="No changelog entries found")
                test_data = changelogs["changelogs"][0]
        else:
            # Use dummy test data
            test_data = {
                "id": "test123",
                "content": "This is a test changelog entry for Reddit integration.",
                "author": "TestUser",
                "timestamp": datetime.now().isoformat(),
                "raw": "Test raw content"
            }
        
        logger.info(f"Test data prepared: Entry ID '{test_data['id']}' by {test_data['author']}")
        
        if test_mode:
            # Simulate posting
            logger.info("Simulating Reddit post (no actual post will be made)...")
            return {"status": "success", "message": "Simulated Reddit post", "test_data": test_data}
        else:
            # Actually post to Reddit
            success, message = await reddit_poster.post_changelog_to_reddit(test_data)
            return {"status": "success" if success else "error", "message": message}
    except Exception as e:
        logger.error(f"Error in test_reddit_posting: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reddit/test-pin/{post_id}", dependencies=[Depends(verify_token)])
async def test_pin_reddit_post(post_id: str):
    """
    Test pinning a Reddit post by post_id. This is a stub for integration testing.
    Requires X-Patcher-Token header for authentication.
    """
    try:
        reddit_poster = import_reddit_poster()
        if not reddit_poster:
            raise HTTPException(status_code=500, detail="Failed to import Reddit poster module")
        # Simulate pinning (replace with actual logic if available)
        logger.info(f"Simulating pinning Reddit post with ID: {post_id}")
        # If reddit_poster has a pin_post method, call it here
        if hasattr(reddit_poster, "pin_post"):
            success, message = await reddit_poster.pin_post(post_id)
            return {"status": "success" if success else "error", "message": message}
        else:
            return {"status": "success", "message": f"Simulated pin for post {post_id}"}
    except Exception as e:
        logger.error(f"Error in test_pin_reddit_post: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reddit/test-flair", dependencies=[Depends(verify_token)])
async def test_reddit_flair():
    """
    Test setting a Reddit flair. This is a stub for integration testing.
    Requires X-Patcher-Token header for authentication.
    """
    try:
        reddit_poster = import_reddit_poster()
        if not reddit_poster:
            raise HTTPException(status_code=500, detail="Failed to import Reddit poster module")
        # Simulate setting flair (replace with actual logic if available)
        logger.info("Simulating setting Reddit flair...")
        # If reddit_poster has a set_flair method, call it here
        if hasattr(reddit_poster, "set_flair"):
            success, message = await reddit_poster.set_flair()
            return {"status": "success" if success else "error", "message": message}
        else:
            return {"status": "success", "message": "Simulated setting Reddit flair"}
    except Exception as e:
        logger.error(f"Error in test_reddit_flair: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/wiki/sync-changelog", dependencies=[Depends(verify_token)])
async def sync_wiki_changelog():
    """
    Manually sync all changelog entries to wiki, checking for duplicates.
    Requires X-Patcher-Token header for authentication.
    """
    if not all([WIKI_API_URL, WIKI_API_KEY, WIKI_PAGE_ID]):
        raise HTTPException(
            status_code=500,
            detail="Wiki integration is not fully configured"
        )
    
    try:
        # Get all changelogs
        changelogs_response = await get_changelog(all=True)
        all_entries = changelogs_response.get("changelogs", [])
        
        if not all_entries:
            return {
                "status": "success",
                "message": "No changelogs found to sync"
            }
        
        # Update wiki with all entries (function will check for duplicates)
        success = await update_wiki_with_new_entries(all_entries)
        
        if success:
            return {
                "status": "success",
                "message": f"Wiki sync completed. Checked {len(all_entries)} entries."
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to sync wiki"
            )
            
    except Exception as e:
        logger.error(f"Error syncing wiki: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/wiki/rebuild-changelog", dependencies=[Depends(verify_token)])
async def rebuild_wiki_changelog():
    """
    Rebuild the entire wiki changelog page with all entries in correct order (newest first).
    This will replace all content on the wiki page.
    Discord mentions are cleaned before posting.
    Requires X-Patcher-Token header for authentication.
    """
    if not all([WIKI_API_URL, WIKI_API_KEY, WIKI_PAGE_ID]):
        raise HTTPException(
            status_code=500,
            detail="Wiki integration is not fully configured"
        )
    
    try:
        # Get all changelogs
        changelogs_response = await get_changelog(all=True)
        all_entries = changelogs_response.get("changelogs", [])
        
        if not all_entries:
            return {
                "status": "success",
                "message": "No changelogs found"
            }
        
        # Sort all entries by ID in DESCENDING order (newest first)
        all_entries.sort(key=lambda x: int(x['id']), reverse=True)
        
        # Build the complete wiki content
        wiki_content = WIKI_HEADER + "\n\n"
        
        for entry in all_entries:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
            except:
                entry_time = entry["timestamp"]
                
            wiki_content += f"## {entry_time} - Entry {entry['id']}\n"
            wiki_content += f"**Author:** {entry['author']}\n\n"
            
            # Clean Discord mentions from content
            content = entry['content'].strip()
            cleaned_content = clean_discord_mentions(content)
            
            if cleaned_content.startswith('```'):
                wiki_content += cleaned_content + "\n\n"
            else:
                wiki_content += cleaned_content + "\n\n"
            wiki_content += "---\n\n"
        
        # Update the wiki page
        page_id = int(WIKI_PAGE_ID)
        success = await update_wiki_page(wiki_content, page_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Wiki rebuilt with {len(all_entries)} entries (newest first, Discord mentions cleaned)"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to update wiki page"
            )
            
    except Exception as e:
        logger.error(f"Error rebuilding wiki: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/wiki/create-monthly-archives", dependencies=[Depends(verify_token)])
async def create_wiki_monthly_archives():
    """
    Create monthly archive structure for wiki changelogs.
    Main page shows last 30 days, with links to monthly archives.
    Requires X-Patcher-Token header for authentication.
    """
    if not all([WIKI_API_URL, WIKI_API_KEY, WIKI_PAGE_ID]):
        raise HTTPException(
            status_code=500,
            detail="Wiki integration is not fully configured"
        )
        
    try:
        # Get all changelogs
        changelogs_response = await get_changelog(all=True)
        all_entries = changelogs_response.get("changelogs", [])
        
        if not all_entries:
            return {"status": "success", "message": "No changelogs found"}
        
        # Sort all entries by ID in DESCENDING order (newest first)
        all_entries.sort(key=lambda x: int(x['id']), reverse=True)
        
        # Organize by month
        entries_by_month = await organize_changelogs_by_month(all_entries)
        
        # Create main page with recent entries (last 30 days)
        main_page_content = WIKI_HEADER + "\n\n"
        main_page_content += "## Recent Updates (Last 30 Days)\n\n"
        
        # Get entries from last 30 days
        cutoff_date = datetime.now() - timedelta(days=30)
        recent_entries = []
        archive_links = []
        
        # Process months in reverse chronological order
        for month_key in sorted(entries_by_month.keys(), reverse=True):
            if month_key == "unknown":
                continue
                
            month_entries = entries_by_month[month_key]
            month_entries.sort(key=lambda x: int(x['id']), reverse=True)
            
            # Check if any entries in this month are recent
            month_has_recent = False
            for entry in month_entries:
                try:
                    entry_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if entry_date >= cutoff_date:
                        recent_entries.append(entry)
                        month_has_recent = True
                except:
                    pass
            
            # Create archive link for this month
            try:
                month_date = datetime.strptime(month_key, "%Y-%m")
                month_name = month_date.strftime("%B %Y")
                archive_links.append({
                    "month_key": month_key,
                    "month_name": month_name,
                    "entry_count": len(month_entries),
                    "has_recent": month_has_recent
                })
            except:
                pass
        
        # Sort recent entries by ID descending
        recent_entries.sort(key=lambda x: int(x['id']), reverse=True)
        
        # Add recent entries to main page
        if recent_entries:
            for entry in recent_entries:
                try:
                    entry_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
                except:
                    entry_time = entry["timestamp"]
                    
                main_page_content += f"### {entry_time} - Entry {entry['id']}\n"
                main_page_content += f"**Author:** {entry['author']}\n\n"
                
                # Clean Discord mentions
                content = entry['content'].strip()
                cleaned_content = clean_discord_mentions(content)
                
                # Truncate very long entries on main page
                if len(cleaned_content) > 500:
                    cleaned_content = cleaned_content[:500] + "..."
                    # Find which month this entry belongs to
                    entry_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    entry_month = entry_date.strftime("%Y-%m")
                    cleaned_content += f"\n\n[View full entry →](/en/changelog-{entry_month}#entry-{entry['id']})"
                
                main_page_content += cleaned_content + "\n\n---\n\n"
        else:
            main_page_content += "*No updates in the last 30 days.*\n\n"
        
        # Add archive section
        main_page_content += "\n## Monthly Archives\n\n"
        main_page_content += "Browse older updates organized by month:\n\n"
        
        # Group archives by year for better organization
        archives_by_year = defaultdict(list)
        for archive in archive_links:
            year = archive['month_key'][:4]
            archives_by_year[year].append(archive)
        
        # Display archives grouped by year
        for year in sorted(archives_by_year.keys(), reverse=True):
            main_page_content += f"\n### {year}\n"
            for archive in archives_by_year[year]:
                page_path = f"changelog-{archive['month_key']}"
                icon = "📍" if archive['has_recent'] else "📄"
                main_page_content += f"- {icon} [{archive['month_name']}](/en/{page_path}) - {archive['entry_count']} updates\n"
        
        # Add search tip
        main_page_content += "\n---\n\n"
        main_page_content += "*💡 Tip: Use the search function (top right) to find specific updates across all archives.*\n"
        
        # Update main page
        logger.info("Updating main changelog page...")
        success = await update_wiki_page(main_page_content, int(WIKI_PAGE_ID))
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Failed to update main page"
            )
        
        # Create/update monthly archive pages
        pages_created = 0
        pages_updated = 0
        pages_failed = 0
        
        for month_key, month_entries in entries_by_month.items():
            if month_key == "unknown":
                continue
                
            month_entries.sort(key=lambda x: int(x['id']), reverse=True)
            
            # Create monthly page content
            try:
                month_date = datetime.strptime(month_key, "%Y-%m")
                month_name = month_date.strftime("%B %Y")
                page_title = f"Changelog - {month_name}"
                page_path = f"changelog-{month_key}"
                
                month_content = f"# {page_title}\n\n"
                month_content += f"[← Back to Recent Updates](/en/Change-log-history) | "
                
                # Add navigation to previous/next month
                all_months = sorted([k for k in entries_by_month.keys() if k != "unknown"])
                current_index = all_months.index(month_key)
                
                if current_index > 0:
                    prev_month = all_months[current_index - 1]
                    prev_date = datetime.strptime(prev_month, "%Y-%m")
                    month_content += f"[← {prev_date.strftime('%B %Y')}](/en/changelog-{prev_month}) | "
                
                if current_index < len(all_months) - 1:
                    next_month = all_months[current_index + 1]
                    next_date = datetime.strptime(next_month, "%Y-%m")
                    month_content += f"[{next_date.strftime('%B %Y')} →](/en/changelog-{next_month})"
                
                month_content += "\n\n---\n\n"
                month_content += f"*{len(month_entries)} updates in {month_name}*\n\n"
                
                # Add entries
                for entry in month_entries:
                    try:
                        entry_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
                    except:
                        entry_time = entry["timestamp"]
                        
                    # Add anchor for direct linking
                    month_content += f"<a name=\"entry-{entry['id']}\"></a>\n\n"
                    month_content += f"## {entry_time} - Entry {entry['id']}\n"
                    month_content += f"**Author:** {entry['author']}\n\n"
                    
                    # Clean Discord mentions
                    content = entry['content'].strip()
                    cleaned_content = clean_discord_mentions(content)
                    
                    month_content += cleaned_content + "\n\n---\n\n"
                
                # Create or update the page
                logger.info(f"Creating/updating page '{page_path}' with {len(month_entries)} entries...")
                if await create_wiki_page(page_title, page_path, month_content):
                    pages_created += 1
                else:
                    pages_failed += 1
                    logger.error(f"Failed to create page for {month_name}")
                    
            except Exception as e:
                logger.error(f"Error processing month {month_key}: {str(e)}")
                pages_failed += 1
        
        return {
            "status": "success",
            "message": f"Updated main page and created/updated {pages_created} monthly archives ({pages_failed} failed)",
            "details": {
                "total_entries": len(all_entries),
                "recent_entries": len(recent_entries),
                "months_processed": len(entries_by_month) - (1 if "unknown" in entries_by_month else 0),
                "pages_created": pages_created,
                "pages_failed": pages_failed
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating monthly archives: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/wiki/test-connection", dependencies=[Depends(verify_token)])
async def test_wiki_connection():
    """
    Test the connection to Wiki.js and verify authentication.
    Requires X-Patcher-Token header for authentication.
    """
    if not all([WIKI_API_URL, WIKI_API_KEY, WIKI_PAGE_ID]):
        raise HTTPException(
            status_code=500,
            detail="Wiki integration is not fully configured"
        )
    
    try:
        headers = {
            'Authorization': f'Bearer {WIKI_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Simple query to test connection
        test_query = """
        query {
          pages {
            list {
              id
              title
            }
          }
        }
        """
        
        timeout = aiohttp.ClientTimeout(total=10)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                WIKI_API_URL,
                json={"query": test_query},
                headers=headers
            ) as response:
                status = response.status
                data = await response.json()
                
                if status == 200 and 'data' in data:
                    page_count = len(data.get('data', {}).get('pages', {}).get('list', []))
                    return {
                        "status": "success",
                        "message": "Wiki.js connection successful",
                        "api_url": WIKI_API_URL,
                        "page_id": WIKI_PAGE_ID,
                        "pages_found": page_count
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Wiki.js connection failed",
                        "http_status": status,
                        "response": data
                    }
                    
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Connection to Wiki.js timed out"
        )
    except Exception as e:
        logger.error(f"Error testing wiki connection: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/heartbeat")
async def heartbeat():
    """
    Simple heartbeat endpoint for healthchecks.
    Does not require authentication.
    """
    try:
        # Log this heartbeat to ensure it's visible in Azure logs
        timestamp = datetime.now().isoformat()
        heartbeat_msg = f"External heartbeat check received at {timestamp}"
        logger.info(heartbeat_msg)
        # Also log to stderr for visibility in Azure
        print(heartbeat_msg, file=sys.stderr, flush=True)
        
        return {
            "status": "alive", 
            "timestamp": timestamp, 
            "service": "Patcher API", 
            "version": "1.0"
        }
    except Exception as e:
        logger.error(f"Error in heartbeat endpoint: {str(e)}")
        return {"status": "error", "message": str(e)}


@app.get("/heartbeat/detail", dependencies=[Depends(verify_token)])
async def detailed_heartbeat():
    """
    Detailed heartbeat check - authenticated.
    Requires X-Patcher-Token header for authentication.
    Returns detailed system status.
    """
    try:
        logger.info("\n=== DETAILED HEARTBEAT CHECK ===")
        
        # Basic system stats without requiring psutil
        system_stats = {
            "timestamp": datetime.now().isoformat(),
            "process_id": os.getpid(),
            "python_version": sys.version
        }
        
        # Get log files if they exist
        log_files = []
        try:
            log_dir = "/app/logs"
            if os.path.exists(log_dir):
                log_files = [f for f in os.listdir(log_dir) if f.endswith('.log')]
                log_files = [{"name": f, "size": os.path.getsize(os.path.join(log_dir, f))} for f in log_files]
        except Exception as e:
            logger.error(f"Error reading log files: {str(e)}")
        
        # Last heartbeats (placeholder)
        last_heartbeats = {
            "discord": datetime.now().isoformat(),
            "api": datetime.now().isoformat()
        }

        # Reddit status info
        reddit_info = {"status": "unknown"}
        try:
            # Import the Reddit poster
            reddit_poster = import_reddit_poster()
            if reddit_poster:
                # Get Reddit info using async function if available
                if hasattr(reddit_poster, "get_reddit_info"):
                    result = await reddit_poster.get_reddit_info()
                    if result:
                        reddit_info = result
        except Exception as e:
            reddit_info = {"status": "error", "message": str(e)}
            logger.error(f"Error getting Reddit info: {str(e)}")
        
        return {
            "status": "alive",
            "timestamp": datetime.now().isoformat(),
            "system": system_stats,
            "environment": {
                "python_version": sys.version,
                "working_directory": os.getcwd(),
                "log_files": log_files
            },
            "last_heartbeats": last_heartbeats,
            "reddit_info": reddit_info
        }
    except Exception as e:
        logger.error(f"Error in detailed_heartbeat: {str(e)}")
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Error in detailed heartbeat: {str(e)}")
        logger.error(traceback.format_exc())
        return {"status": "error", "message": str(e), "traceback": traceback.format_exc()}

# Add a special function to ensure logs are visible in Azure
def force_azure_log(message, level="info", include_timestamp=True):
    """Force log to multiple outputs to ensure visibility in Azure"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if include_timestamp else ""
    
    # Use standard logger first
    if level.lower() == "info":
        logger.info(message)
    elif level.lower() == "warning":
        logger.warning(message)
    elif level.lower() == "error":
        logger.error(message)
    elif level.lower() == "critical":
        logger.critical(message)
    else:
        logger.info(message)
    
    # Then force output to stderr for Azure visibility
    if timestamp:
        output = f"{timestamp} [{level.upper()}]: {message}"
    else:
        output = message
        
    # Print directly to both stdout and stderr with flush
    print(output, flush=True)
    print(output, file=sys.stderr, flush=True)
    
    # For important events, make them visually distinct
    if level.lower() in ["warning", "error", "critical"]:
        visual_marker = "❌" if level.lower() in ["error", "critical"] else "⚠️"
        separator = "-" * 80
        distinctive_output = f"\n{separator}\n{visual_marker} {output}\n{separator}\n"
        print(distinctive_output, file=sys.stderr, flush=True)