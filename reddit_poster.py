import os
import logging
from datetime import datetime
import json
import traceback
import asyncpraw
import re

# Ensure the logs directory exists before any logging
os.makedirs('/app/logs', exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/reddit_poster.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Reddit credentials from environment variables
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_USERNAME = os.getenv('REDDIT_USERNAME')
REDDIT_PASSWORD = os.getenv('REDDIT_PASSWORD')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'ChangelogPoster by /u/YourUsername')
REDDIT_SUBREDDIT = os.getenv('REDDIT_SUBREDDIT')
REDDIT_FLAIR_NAME = os.getenv('REDDIT_FLAIR_NAME', 'Change-Log')

# Path to store Reddit posts information
REDDIT_POSTS_PATH = "/app/reddit_posts.json"

async def initialize_reddit():
    """Initialize and return an async Reddit API instance."""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD, REDDIT_SUBREDDIT]):
        logger.error("Reddit credentials not fully configured!")
        return None
    
    try:
        reddit = asyncpraw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=REDDIT_USER_AGENT
        )
        
        # Test the connection
        user = await reddit.user.me()
        logger.info(f"Successfully authenticated with Reddit as {user.name}")
        return reddit
    except Exception as e:
        logger.error(f"Error initializing Reddit API: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def get_posted_entries():
    """Get information about already posted changelog entries."""
    try:
        if os.path.exists(REDDIT_POSTS_PATH):
            with open(REDDIT_POSTS_PATH, 'r') as f:
                return json.load(f)
        return {"posts": []}
    except Exception as e:
        logger.error(f"Error reading Reddit posts: {str(e)}")
        return {"posts": []}

def save_post_info(entry_id, post_id, title, url, flair_applied=None, force_used=False):
    """Save information about a posted changelog entry."""
    posts_data = get_posted_entries()
    
    posts_data["posts"].append({
        "entry_id": entry_id,
        "post_id": post_id,
        "title": title,
        "url": url,
        "flair": flair_applied,
        "posted_at": datetime.now().isoformat(),
        "pinned": True,
        "force_used": force_used
    })
    
    posts_data["posts"].sort(key=lambda x: x["posted_at"], reverse=True)
    
    try:
        with open(REDDIT_POSTS_PATH, 'w') as f:
            json.dump(posts_data, f, indent=2)
        logger.info(f"Saved post info for entry {entry_id}: {post_id}")
    except Exception as e:
        logger.error(f"Error saving post info: {str(e)}")

def update_pin_status(post_id, pinned):
    """Update the pin status of a post in our records."""
    posts_data = get_posted_entries()
    
    for post in posts_data["posts"]:
        if post["post_id"] == post_id:
            post["pinned"] = pinned
    
    try:
        with open(REDDIT_POSTS_PATH, 'w') as f:
            json.dump(posts_data, f, indent=2)
        logger.info(f"Updated pin status for post {post_id}: {pinned}")
    except Exception as e:
        logger.error(f"Error updating pin status: {str(e)}")

def clean_discord_mentions(content: str) -> str:
    """Remove Discord user mentions and clean up the content for Reddit posting."""
    # Remove Discord-specific mentions
    content = re.sub(r'<@\d+>', '', content)  # User mentions
    content = re.sub(r'<@&\d+>', '', content)  # Role mentions  
    content = re.sub(r'<#\d+>', '', content)  # Channel mentions
    
    # Clean up extra whitespace left by removed mentions
    content = re.sub(r' +', ' ', content)  # Multiple spaces -> single space
    content = re.sub(r'\n +', '\n', content)  # Remove spaces at start of lines
    content = re.sub(r' +\n', '\n', content)  # Remove spaces at end of lines
    
    return content.strip()

def format_changelog_for_reddit(message_content, timestamp, author, entry_id):
    """Format a changelog entry for Reddit with enhanced markdown."""
    try:
        # Convert timestamp to datetime if it's a string
        if isinstance(timestamp, str):
            try:
                formatted_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).strftime("%Y-%m-%d %H:%M:%S UTC")
            except ValueError:
                formatted_date = timestamp
        else:
            formatted_date = timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    except:
        formatted_date = str(timestamp)
    
    # Clean Discord mentions from the content
    cleaned_content = clean_discord_mentions(message_content)
    
    # Build the formatted post with enhanced markdown
    formatted_parts = []
    
    # Header with emoji
    formatted_parts.append("## 🎮 Heroes' Journey Changelog Update")
    formatted_parts.append("")
    
    # Metadata table
    formatted_parts.append("| Field | Value |")
    formatted_parts.append("|-------|-------|")
    formatted_parts.append(f"| 👤 **Author** | {author} |")
    formatted_parts.append(f"| 📅 **Date** | {formatted_date} |")
    formatted_parts.append(f"| 🔗 **Entry ID** | `{entry_id}` |")
    formatted_parts.append("")
    
    # Main separator
    formatted_parts.append("---")
    formatted_parts.append("")
    
    # Main content
    formatted_parts.append("### 📋 Changelog Details")
    formatted_parts.append("")
    formatted_parts.append(cleaned_content)
    formatted_parts.append("")
    
    # Footer
    formatted_parts.append("---")
    formatted_parts.append("")
    formatted_parts.append("*This post was automatically generated from the official changelog.*")
    
    return "\n".join(formatted_parts)

async def check_recent_reddit_posts(entry_id):
    """Check if a changelog entry has already been posted to Reddit by scanning recent posts."""
    try:
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
            if hasattr(submission, 'selftext') and f"Entry ID** | `{entry_id}`" in submission.selftext:
                logger.warning(f"Found duplicate post for entry {entry_id}: {submission.url}")
                await reddit.close()
                return True
        
        logger.info(f"Checked {post_count} recent posts, no duplicates found for entry {entry_id}")
        await reddit.close()
        return False
        
    except Exception as e:
        logger.error(f"Error checking for duplicate posts: {str(e)}")
        return False

async def find_and_apply_flair(reddit, submission, subreddit, preferred_flair_name=None):
    """Find and apply an appropriate flair to the post."""
    try:
        # Get available flairs for the subreddit
        available_flairs = []
        async for flair in subreddit.flair.link_templates:
            available_flairs.append(flair)
        
        if not available_flairs:
            logger.warning(f"No flairs found for r/{subreddit.display_name}")
            return (False, None)
            
        logger.info(f"Found {len(available_flairs)} flairs for r/{subreddit.display_name}")
        
        # Select the appropriate flair
        selected_flair = None
        flair_name_to_use = preferred_flair_name or REDDIT_FLAIR_NAME
        
        # First try to find the exact flair
        for flair in available_flairs:
            if "text" in flair and flair["text"].lower() == flair_name_to_use.lower():
                selected_flair = flair
                logger.info(f"Found exact match for flair '{flair_name_to_use}'")
                break
        
        # If we didn't find the exact flair, look for keyword matches
        if not selected_flair:
            flair_keywords = ["change-log", "changelog", "change log", "announcement", "update", "important", "info"]
            
            for keyword in flair_keywords:
                if selected_flair:
                    break
                for flair in available_flairs:
                    if "text" in flair and keyword in flair["text"].lower():
                        selected_flair = flair
                        logger.info(f"Selected flair '{flair['text']}' based on keyword '{keyword}'")
                        break
        
        # Apply the flair if found
        if selected_flair:
            flair_id = selected_flair.get("id") or selected_flair.get("flair_template_id")
            if not flair_id:
                logger.error(f"No flair ID found in selected flair: {selected_flair}")
                return (False, selected_flair.get("text"))
                
            await submission.flair.select(flair_id)
            logger.info(f"Applied flair '{selected_flair.get('text')}' to post {submission.id}")
            return (True, selected_flair.get("text"))
        else:
            logger.warning(f"No suitable flair found for r/{subreddit.display_name}")
            return (False, None)
            
    except Exception as e:
        logger.error(f"Error applying flair: {str(e)}")
        logger.error(traceback.format_exc())
        return (False, None)

async def manage_pinned_posts(reddit, current_post_id):
    """Manage pinned posts in the subreddit."""
    try:
        subreddit = await reddit.subreddit(REDDIT_SUBREDDIT)
        
        # Get currently pinned posts (stickied)
        pinned_posts = []
        try:
            sticky_1 = await subreddit.sticky(number=1)
            if sticky_1:
                pinned_posts.append(sticky_1)
        except Exception as e:
            logger.debug(f"No first sticky post: {e}")
            
        try:
            sticky_2 = await subreddit.sticky(number=2)
            if sticky_2:
                pinned_posts.append(sticky_2)
        except Exception as e:
            logger.debug(f"No second sticky post: {e}")
        
        # If we already have 2 pinned posts, and our current post isn't one of them
        if len(pinned_posts) >= 2 and not any(p.id == current_post_id for p in pinned_posts):
            # Unpin the oldest one (index 1 is the older sticky)
            oldest_post = pinned_posts[1]
            await oldest_post.mod.sticky(state=False)
            logger.info(f"Unpinned older post {oldest_post.id} to make room for new pinned post")
            
            # Update our records
            update_pin_status(oldest_post.id, False)
        
        return True
    except Exception as e:
        logger.error(f"Error managing pinned posts: {str(e)}")
        logger.error(traceback.format_exc())
        return False

async def post_changelog_to_reddit(entry, test_mode=False, force=False):
    """
    Post a single changelog entry to Reddit as a new pinned post with flair.
    
    This is the MAIN function used by your API endpoints.
    
    Parameters:
    - entry: The changelog entry to post (dict with id, content, timestamp, author)
    - test_mode: If True, simulates posting without making actual Reddit API calls
    - force: If True, bypasses duplicate checking and posts anyway
    
    Returns:
    - (success, message): Tuple of success boolean and result message
    """
    logger.info(f"Starting Reddit post for entry {entry['id']} (test_mode={test_mode}, force={force})")
    
    # Check if this entry has already been posted (unless force is True)
    if not force:
        posts_data = get_posted_entries()
        for post in posts_data["posts"]:
            if post["entry_id"] == entry["id"]:
                logger.info(f"Entry {entry['id']} already posted to Reddit as {post['post_id']}")
                return True, f"Already posted: {post['url']} (use force=True to override)"

    # Additional duplicate check by scanning recent Reddit posts
    if not force and not test_mode:
        duplicate_found = await check_recent_reddit_posts(entry["id"])
        if duplicate_found:
            logger.warning(f"Found duplicate post for entry {entry['id']} on Reddit but not in local tracking")
            return False, f"Duplicate post detected on Reddit for entry {entry['id']} (use force=True to override)"

    # Format the entry for Reddit
    formatted_body = format_changelog_for_reddit(
        entry["content"],
        entry["timestamp"],
        entry["author"],
        entry["id"]
    )
    
    # Create title from the first line of content or use a generic title
    content_lines = entry["content"].split('\n')
    title_text = next((line.strip() for line in content_lines if line.strip()), "Heroes' Journey Update")
    
    # Clean the title and add emoji
    title_text = clean_discord_mentions(title_text)
    title = f"🎮 Update: {title_text[:70]}..." if len(title_text) > 70 else f"🎮 Update: {title_text}"
    
    # If in test mode, just return the formatted content without posting
    if test_mode:
        logger.info(f"TEST MODE: Would post entry {entry['id']} with title '{title}'")
        return True, f"Test successful - would post to Reddit with title: '{title}'"
    
    # Initialize Reddit API
    reddit = await initialize_reddit()
    if not reddit:
        logger.error("Failed to initialize Reddit API")
        return False, "Failed to initialize Reddit API"
    
    try:
        # Get the subreddit
        subreddit = await reddit.subreddit(REDDIT_SUBREDDIT)
        
        # Create the post
        submission = await subreddit.submit(
            title=title, 
            selftext=formatted_body,
            send_replies=True
        )
        
        # Load the submission to access its attributes
        await submission.load()
        
        logger.info(f"Created new post for entry {entry['id']}: {submission.id} - {submission.title}")
        
        # Apply flair if possible
        flair_success, flair_name = await find_and_apply_flair(
            reddit, 
            submission, 
            subreddit, 
            REDDIT_FLAIR_NAME
        )
        
        # Manage pinned posts before pinning the new one
        await manage_pinned_posts(reddit, submission.id)
        
        # Pin the post (if possible)
        pin_success = False
        try:
            await submission.mod.sticky()
            logger.info(f"Successfully pinned post {submission.id}")
            pin_success = True
        except Exception as e:
            logger.warning(f"Could not pin post {submission.id}: {str(e)}")
        
        # Save post info
        save_post_info(
            entry["id"],
            submission.id,
            submission.title,
            submission.url,
            flair_name,
            force_used=force
        )
        
        # Generate success message
        status_parts = []
        if flair_success:
            status_parts.append(f"flaired as '{flair_name}'")
        if pin_success:
            status_parts.append("pinned")
        if force:
            status_parts.append("forced override")
            
        status_text = " and ".join(status_parts)
        status_message = f" ({status_text})" if status_parts else ""
        
        # Close the Reddit session
        await reddit.close()
        
        return True, f"Created new post{status_message}: {submission.url}"
        
    except Exception as e:
        logger.error(f"Error creating Reddit post: {str(e)}")
        logger.error(traceback.format_exc())
        return False, f"Error: {str(e)}"
    finally:
        # Ensure Reddit session is closed
        try:
            await reddit.close()
        except:
            pass

# Helper functions for testing and admin use
async def get_reddit_info():
    """Get basic Reddit information for testing and diagnostics."""
    reddit = await initialize_reddit()
    if not reddit:
        return None
    
    try:
        subreddit = await reddit.subreddit(REDDIT_SUBREDDIT)
        
        # Check moderator status
        is_mod = False
        mod_permissions = []

        try:
            moderators = await subreddit.moderator()
            for mod in moderators:
                if mod.name.lower() == REDDIT_USERNAME.lower():
                    is_mod = True
                    try:
                        mod_permissions = list(mod.mod_permissions) if hasattr(mod, 'mod_permissions') else []
                    except:
                        mod_permissions = []
                    break
        except Exception as e:
            logger.warning(f"Could not check moderator status: {e}")
            is_mod = False
            mod_permissions = []
        
        # Get available flairs
        available_flairs = []
        try:
            async for flair in subreddit.flair.link_templates:
                available_flairs.append({
                    "flair_id": flair.get("id") or flair.get("flair_template_id"),
                    "text": flair.get("text", "No text"),
                    "css_class": flair.get("css_class"),
                    "text_editable": flair.get("text_editable", False),
                    "background_color": flair.get("background_color"),
                    "text_color": flair.get("text_color")
                })
        except Exception as e:
            logger.error(f"Error getting flairs: {str(e)}")
        
        preferred_flair = REDDIT_FLAIR_NAME
        matching_flairs = [f for f in available_flairs if f.get("text", "").lower() == preferred_flair.lower()]
        has_preferred_flair = len(matching_flairs) > 0
        
        result = {
            "subreddit": f"r/{subreddit.display_name}",
            "account": REDDIT_USERNAME,
            "is_moderator": is_mod,
            "mod_permissions": mod_permissions,
            "can_manage_flair": "flair" in mod_permissions or "all" in mod_permissions if mod_permissions else False,
            "available_flairs_count": len(available_flairs),
            "available_flairs": available_flairs,
            "preferred_flair": preferred_flair,
            "has_preferred_flair": has_preferred_flair,
            "recommended_action": "The flairs look good!" if has_preferred_flair else f"Add a flair named '{preferred_flair}' to your subreddit or update REDDIT_FLAIR_NAME environment variable"
        }
        
        await reddit.close()
        return result
        
    except Exception as e:
        logger.error(f"Error getting Reddit info: {str(e)}")
        try:
            await reddit.close()
        except:
            pass
        return None