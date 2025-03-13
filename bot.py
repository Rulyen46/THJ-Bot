import os
import discord
from fastapi import FastAPI, HTTPException, Security, Depends
from dotenv import load_dotenv
from datetime import datetime
import asyncio
import uvicorn
from typing import Optional
import aiohttp
from fastapi.security import APIKeyHeader
import json
import logging
import sys

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
PATCHER_TOKEN = os.getenv('PATCHER_TOKEN')

# Wiki variables
WIKI_API_URL = os.getenv('WIKI_API_URL')
WIKI_API_KEY = os.getenv('WIKI_API_KEY')
WIKI_PAGE_ID = os.getenv('WIKI_PAGE_ID') 

# Ensure we use the port provided by Azure
PORT = int(os.getenv('PORT', '80'))

WIKI_HEADER = """![change-logs.webp](/change-logs.webp){.align-center}
# THJ Change-Logs
(Newest is up top, Oldest is at the bottom.)"""

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
    'WIKI_PAGE_ID': WIKI_PAGE_ID
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

# Global variable for changelog channel
changelog_channel = None

@client.event
async def on_ready():
    """Handle Discord client ready event"""
    global changelog_channel
    logger.info('🤖 Bot connected successfully!')
    
    for guild in client.guilds:
        for channel in guild.channels:
            if channel.id == CHANGELOG_CHANNEL_ID:
                changelog_channel = channel
                logger.info('✅ Found changelog channel: %s', channel.name)
                return
    
    logger.error('❌ Could not find changelog channel!')

@client.event
async def on_message(message):
    """Handle new messages in Discord"""
    if message.channel.id == CHANGELOG_CHANNEL_ID:
        logger.info('🔔 New changelog entry from: %s', message.author.display_name)

# Set up FastAPI
app = FastAPI()

# Set up security
api_key_header = APIKeyHeader(name="X-Patcher-Token", auto_error=True)

async def verify_token(api_key: str = Security(api_key_header)):
    if api_key != PATCHER_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid authentication token"
        )
    return api_key

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

async def process_wiki_content(current_content: str, new_entry: str) -> str:
    """
    Process and combine Wiki content with new changelog entry.
    Ensures header is preserved and content is properly formatted.
    
    Args:
        current_content: Current content from the Wiki page
        new_entry: New changelog entry to add
        
    Returns:
        Combined content with header and proper formatting
    """
    # Extract header and existing content
    if "![change-logs.webp" in current_content:
        # Split only on first occurrence of double newline after header
        parts = current_content.split("\n\n", 1)
        header = parts[0]  # This will be the header
        existing_content = parts[1] if len(parts) > 1 else ""
        
        # Find the first changelog entry in existing content
        if existing_content:
            # Look for the first heading that indicates a changelog entry
            content_parts = existing_content.split("# ", 1)
            if len(content_parts) > 1:
                # Preserve any spacing before the first entry
                spacing = content_parts[0]
                existing_content = "# " + content_parts[1]
            else:
                spacing = "\n\n"
                existing_content = existing_content.strip()
    else:
        header = WIKI_HEADER
        spacing = "\n\n"
        existing_content = current_content.strip()
    
    # Combine content with proper spacing
    if existing_content:
        # Add a newline after the header, then spacing, then new entry
        # Add a single newline after the new entry's horizontal rule
        # Then add the existing content
        full_content = f"{header}\n\n{spacing}{new_entry}\n{existing_content}"
    else:
        # If there's no existing content, just add the new entry with standard spacing
        full_content = f"{header}\n\n{new_entry}"
    
    # Clean up any excessive newlines (more than 2 consecutive)
    while '\n\n\n' in full_content:
        full_content = full_content.replace('\n\n\n', '\n\n')
    
    return full_content

async def check_and_update_wiki():
    """Periodically check Discord channel for new messages and update Wiki"""
    while True:
        try:
            if changelog_channel:
                logger.info(f"\n=== Checking for new messages at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
                
                # Get the most recent message
                async for message in changelog_channel.history(limit=1):
                    logger.info(f"Processing latest message from: {message.author.display_name}")
                    
                    # Get current content first
                    page_id = int(os.getenv('WIKI_PAGE_ID'))
                    try:
                        headers = {
                            'Authorization': f'Bearer {WIKI_API_KEY}',
                            'Content-Type': 'application/json'
                        }
                        query = """
                        query {
                          pages {
                            single(id: %d) {
                              content
                            }
                          }
                        }
                        """ % page_id
                        
                        logger.info(f"Fetching current Wiki content for page {page_id}...")
                        async with aiohttp.ClientSession() as session:
                            async with session.post(
                                WIKI_API_URL,
                                json={"query": query},
                                headers=headers
                            ) as response:
                                response_data = await response.json()
                                if 'data' in response_data and response_data['data']['pages']['single']:
                                    current_content = response_data['data']['pages']['single']['content']
                                    logger.info("✓ Successfully retrieved current Wiki content")
                                    
                                    # Format the new entry
                                    new_entry = format_changelog_for_wiki(
                                        message.content,
                                        message.created_at,
                                        message.author.display_name
                                    )
                                    
                                    # Check if this entry is already in the Wiki
                                    # Create a unique identifier from the date, author, and first 50 chars of content
                                    entry_date = message.created_at.strftime('%B %d, %Y')
                                    entry_identifier = f"# {entry_date}\n## {message.author.display_name}\n\n{message.content[:50]}"
                                    
                                    if entry_identifier in current_content:
                                        logger.info("⏭️ Latest changelog entry is already in the Wiki, skipping update")
                                        break
                                    
                                    # If we get here, this is a new entry that needs to be added
                                    logger.info("🆕 New changelog entry detected, updating Wiki")
                                    
                                    # Process and combine content
                                    full_content = await process_wiki_content(current_content, new_entry)
                                    logger.info("Content prepared for update")
                                    
                                    success = await update_wiki_page(full_content, page_id)
                                    if success:
                                        logger.info("✅ Successfully updated Wiki with latest changelog")
                                    else:
                                        logger.error("❌ Failed to update Wiki")
                                else:
                                    current_content = ""
                                    logger.warning("⚠️ No existing content found")
                    
                    except Exception as e:
                        logger.error(f"❌ Error getting current content: {type(e).__name__}")
                        logger.error(f"Error details: {str(e)}")
                        current_content = ""
                    break
                        
            else:
                logger.warning("⏳ Waiting for changelog channel to be ready...")
                
        except Exception as e:
            logger.error(f"❌ Error in check_and_update_wiki: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            
        logger.info("\nWaiting 1 hour before next check...")
        await asyncio.sleep(3600)  # Check every hour

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
        logger.info(f"\n🚀 Starting FastAPI server on port {PORT}...")
        logger.info(f"Host: 0.0.0.0")
        logger.info(f"Port: {PORT}")
        
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=PORT,
            log_level="info",
            access_log=True
        )
        server = uvicorn.Server(config)
        await server.serve()
    except Exception as e:
        logger.error(f"❌ Failed to start FastAPI server: {str(e)}")
        logger.error(f"Port attempted: {PORT}")
        logger.error(f"Error type: {type(e).__name__}")
        raise

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

@app.get("/changelog", dependencies=[Depends(verify_token)])
async def get_changelog(count: Optional[int] = 1, all: Optional[bool] = False):
    """
    Get the latest changelog(s) from Discord
    Requires X-Patcher-Token header for authentication.
    Optional parameters:
    - count: number of changelogs to retrieve (default: 1)
    - all: if True, retrieves all messages ever posted (ignores count parameter)
    Example: /changelog?count=3
    Example: /changelog?all=true
    """
    logger.info('Fetching changelogs...')
    
    if not client.is_ready():
        logger.error('Channel not found. Looking for ID: %s', CHANGELOG_CHANNEL_ID)
        raise HTTPException(status_code=500, detail=f"Discord bot not ready or channel {CHANGELOG_CHANNEL_ID} not found")
    
    try:
        if all:
            logger.info('Attempting to fetch ALL messages from channel %s', changelog_channel.name)
            messages = [message async for message in changelog_channel.history(limit=None, oldest_first=False)]
        else:
            logger.info('Attempting to fetch %d message(s) from channel %s', count, changelog_channel.name)
            messages = [message async for message in changelog_channel.history(limit=count)]

        if not messages:
            logger.info('No messages found in channel')
            return {
                "total": 0,
                "changelogs": []
            }

        changelogs = []
        for message in messages:
            formatted_content = format_changelog_for_wiki(
                message.content, 
                message.created_at,
                message.author.display_name
            )
            changelogs.append({
                "raw_content": message.content,
                "formatted_content": formatted_content,
                "author": message.author.display_name,
                "timestamp": message.created_at.isoformat(),
                "message_id": str(message.id)
            })
            
        logger.info('Successfully fetched %d changelog(s)', len(changelogs))
        return {
            "total": len(changelogs),
            "changelogs": sorted(changelogs, key=lambda x: x["timestamp"], reverse=True)
        }
    except Exception as e:
        logger.error('Error fetching changelogs: %s', str(e))
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
                
                logger.info("\nExecuting render mutation...")
                async with session.post(
                    WIKI_API_URL,
                    json={"query": render_mutation, "variables": {"id": page_id}},
                    headers=headers
                ) as render_response:
                    render_data = await render_response.json()
                    
                    logger.info(f"\nRender Response Analysis:")
                    logger.info(f"- Raw Response: {json.dumps(render_data, indent=2)}")
                    
                    if 'errors' in render_data:
                        logger.error("\nGraphQL Errors in render:")
                        for error in render_data['errors']:
                            logger.error(f"- Message: {error.get('message', 'N/A')}")
                        return False
                    
                    render_result = render_data.get('data', {}).get('pages', {}).get('render', {}).get('responseResult', {})
                    if not render_result.get('succeeded', False):
                        logger.error(f"\n❌ Failed to render page: {render_result.get('message', 'Unknown error')}")
                        return False
                    
                    logger.info("\n✅ Page updated and rendered successfully")
                    return True
                    
    except Exception as e:
        logger.error(f"\n❌ Error in update_wiki_page: {type(e).__name__}")
        logger.error(f"Error details: {str(e)}")
        if isinstance(e, aiohttp.ClientError):
            logger.error(f"Network error details: {str(e)}")
        return False

@app.post("/process-latest", dependencies=[Depends(verify_token)])
async def process_latest_changelog():
    """
    Process the latest changelog message and update the wiki if it's new.
    Requires X-Patcher-Token header for authentication.
    """
    logger.info("\n=== Processing Latest Changelog ===")
    
    if not client.is_ready():
        raise HTTPException(status_code=503, detail="Discord client is not ready")
        
    if not changelog_channel:
        raise HTTPException(status_code=503, detail="Changelog channel not found")
    
    try:
        messages = [message async for message in changelog_channel.history(limit=1)]
        
        if not messages:
            return {
                "status": "success",
                "message": "No changelog entries found"
            }
            
        message = messages[0]
        
        # Get current content first
        page_id = int(WIKI_PAGE_ID)
        try:
            headers = {
                'Authorization': f'Bearer {WIKI_API_KEY}',
                'Content-Type': 'application/json'
            }
            query = """
            query {
              pages {
                single(id: %d) {
                  content
                }
              }
            }
            """ % page_id
            
            logger.info(f"Fetching current Wiki content for page {page_id}...")
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    WIKI_API_URL,
                    json={"query": query},
                    headers=headers
                ) as response:
                    response_data = await response.json()
                    if 'data' in response_data and response_data['data']['pages']['single']:
                        current_content = response_data['data']['pages']['single']['content']
                        logger.info("✓ Successfully retrieved current Wiki content")
                    else:
                        current_content = ""
                        logger.warning("⚠️ No existing content found")
        
        except Exception as e:
            logger.error(f"❌ Error getting current content: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            current_content = ""
        
        new_entry = format_changelog_for_wiki(
            message.content,
            message.created_at,
            message.author.display_name
        )
        
        # Process and combine content
        full_content = await process_wiki_content(current_content, new_entry)
        logger.info("Content prepared for update")
        
        success = await update_wiki_page(full_content, page_id)
        if success:
            logger.info("✅ Successfully updated Wiki with new changelog")
            return {
                "status": "success",
                "message": f"Successfully processed and updated changelog (ID: {message.id})",
                "changelog": {
                    "author": message.author.display_name,
                    "timestamp": message.created_at.isoformat(),
                    "content": message.content
                }
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to update Wiki with new changelog"
            )
            
    except Exception as e:
        logger.error(f"❌ Error processing latest changelog: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

async def main():
    """Run both Discord client and FastAPI server"""
    try:
        print("\n=== Starting Application ===")
        print(f"PORT: {PORT}")
        print(f"CHANGELOG_CHANNEL_ID: {CHANGELOG_CHANNEL_ID}")
        print("Starting Discord client...")
        
        # Start Discord client
        discord_task = asyncio.create_task(start_discord())
        
        # Wait for Discord to be ready
        timeout = 30  # 30 seconds timeout
        start_time = asyncio.get_event_loop().time()
        while not client.is_ready():
            if asyncio.get_event_loop().time() - start_time > timeout:
                raise TimeoutError("Discord client failed to connect within timeout period")
            print("⏳ Waiting for Discord client to be ready...")
            await asyncio.sleep(1)
        
        print("✅ Discord client is ready!")
        print("🔍 Looking for changelog channel...")
        
        if changelog_channel:
            print(f"✅ Found changelog channel: {changelog_channel.name}")
        else:
            print("❌ Could not find changelog channel!")
            raise ValueError("Changelog channel not found")
        
        # Start the wiki checker task
        wiki_task = asyncio.create_task(check_and_update_wiki())
        print("✅ Started wiki update checker (1-hour intervals)")
        
        # Start FastAPI server
        print("\n=== Starting FastAPI Server ===")
        api_task = asyncio.create_task(start_api())
        
        # Wait for all tasks
        await asyncio.gather(discord_task, api_task, wiki_task)
        
    except TimeoutError as e:
        print(f"\n❌ Timeout error: {str(e)}")
        raise
    except ValueError as e:
        print(f"\n❌ Configuration error: {str(e)}")
        raise
    except Exception as e:
        print(f"\n❌ Error in main: {type(e).__name__}")
        print(f"Error details: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 