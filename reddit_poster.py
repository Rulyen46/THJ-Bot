import os
import logging
from datetime import datetime, timedelta
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
REDDIT_FLAIR_NAME = os.getenv('REDDIT_FLAIR_NAME', 'Announcement')  # Default to 'Announcement'

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
    
    # Add the new post
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
    
    # Sort posts by posted_at to maintain chronological order
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

def format_batched_changelog_for_reddit(entries, batch_id):
    """Format multiple changelog entries as a single Reddit post."""
    
    # Get the date range
    if len(entries) == 1:
        # Single entry
        entry = entries[0]
        try:
            formatted_date = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
        except:
            formatted_date = entry["timestamp"]
            
        formatted_content = f"# Heroes' Journey Changelog Update\n\n"
        formatted_content += f"**Date:** {formatted_date}\n"
        formatted_content += f"**Author:** {entry['author']}\n"
        formatted_content += f"**Entry ID:** {entry['id']}\n\n"
        formatted_content += f"---\n\n"
        formatted_content += entry['content']
        
    else:
        # Multiple entries - create a batched post
        first_entry = entries[0]
        last_entry = entries[-1]
        
        try:
            start_date = datetime.fromisoformat(first_entry["timestamp"].replace("Z", "+00:00"))
            end_date = datetime.fromisoformat(last_entry["timestamp"].replace("Z", "+00:00"))
            
            # Format the date range
            if start_date.date() == end_date.date():
                # Same day
                date_str = f"{start_date.strftime('%Y-%m-%d')} ({start_date.strftime('%H:%M')} - {end_date.strftime('%H:%M')})"
            else:
                # Different days
                date_str = f"{start_date.strftime('%Y-%m-%d %H:%M')} - {end_date.strftime('%Y-%m-%d %H:%M')}"
                
        except:
            date_str = f"{first_entry['timestamp']} - {last_entry['timestamp']}"
        
        # Collect unique authors
        authors = []
        seen_authors = set()
        for entry in entries:
            if entry['author'] not in seen_authors:
                authors.append(entry['author'])
                seen_authors.add(entry['author'])
        
        formatted_content = f"# Heroes' Journey Changelog Update\n\n"
        formatted_content += f"**Date Range:** {date_str}\n"
        formatted_content += f"**Authors:** {', '.join(authors)}\n"
        formatted_content += f"**Updates:** {len(entries)} changelog entries\n"
        formatted_content += f"**Batch ID:** {batch_id}\n\n"
        formatted_content += f"---\n\n"
        
        # Add each entry's content
        for i, entry in enumerate(entries):
            # Add a subtle separator between entries if there are multiple
            if i > 0:
                formatted_content += "\n\n"
            
            # Add entry metadata as a smaller header
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).strftime("%H:%M")
            except:
                entry_time = entry["timestamp"]
                
            # Only show author if different from previous
            if i == 0 or entry['author'] != entries[i-1]['author']:
                formatted_content += f"**[{entry_time} - {entry['author']}]**\n\n"
            else:
                formatted_content += f"**[{entry_time}]**\n\n"
            
            # Add the content
            formatted_content += entry['content']
    
    formatted_content += "\n\n---\n\n"
    formatted_content += "*This post was automatically generated from the official changelog.*"
    
    return formatted_content

def generate_batch_id(entries):
    """Generate a unique batch ID from the entry IDs."""
    if len(entries) == 1:
        return entries[0]['id']
    
    # For multiple entries, create a hash of all IDs
    entry_ids = [e['id'] for e in entries]
    entry_ids.sort()  # Ensure consistent ordering
    
    # Create a simple batch ID
    batch_id = f"batch_{entry_ids[0]}_{entry_ids[-1]}"
    return batch_id

async def check_recent_reddit_posts(entry_id):
    """
    Check if a changelog entry has already been posted to Reddit by scanning recent posts.
    This is a backup check in case our local tracking gets out of sync.
    
    Returns True if duplicate found, False otherwise.
    """
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

async def find_and_apply_flair(reddit, submission, subreddit, preferred_flair_name=None):
    """Find and apply an appropriate flair to the post.
    
    Args:
        reddit: The Reddit instance
        submission: The submission to flair
        subreddit: The subreddit object
        preferred_flair_name: Preferred flair name (optional)
        
    Returns:
        Tuple of (success, flair_name)
    """
    try:
        # Get available flairs for the subreddit
        available_flairs = []
        async for flair in subreddit.flair.link_templates:
            available_flairs.append(flair)
        
        if not available_flairs:
            logger.warning(f"No flairs found for r/{subreddit.display_name}")
            return (False, None)
            
        logger.info(f"Found {len(available_flairs)} flairs for r/{subreddit.display_name}")
        
        # Log available flairs for debugging
        flair_names = [f["text"] for f in available_flairs if "text" in f]
        logger.info(f"Available flairs: {', '.join(flair_names)}")
        
        # Select the appropriate flair
        selected_flair = None
        
        # First try to find the preferred flair if specified
        if preferred_flair_name:
            for flair in available_flairs:
                if "text" in flair and flair["text"].lower() == preferred_flair_name.lower():
                    selected_flair = flair
                    logger.info(f"Found exact match for preferred flair '{preferred_flair_name}'")
                    break
        
        # If we didn't find the preferred flair, look for announcement/changelog flairs
        if not selected_flair:
            flair_keywords = ["announcement", "changelog", "update", "important", "info"]
            
            for keyword in flair_keywords:
                if selected_flair:
                    break
                    
                for flair in available_flairs:
                    if "text" in flair and keyword in flair["text"].lower():
                        selected_flair = flair
                        logger.info(f"Selected flair '{flair['text']}' based on keyword '{keyword}'")
                        break
        
        # If we found a flair, apply it
        if selected_flair:
            flair_id = selected_flair.get("id") or selected_flair.get("flair_template_id")
            if not flair_id:
                logger.error(f"No flair ID found in selected flair: {selected_flair}")
                return (False, selected_flair.get("text"))
                
            # Apply the flair
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
    """Manage pinned posts in the subreddit.
    
    Reddit only allows 2 pinned posts per subreddit,
    so we need to unpin the oldest one if we're at the limit.
    """
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

async def get_entries_in_window(all_entries, target_entry, window_minutes=30):
    """
    Get all entries within a time window of the target entry.
    
    Parameters:
    - all_entries: List of all changelog entries
    - target_entry: The reference entry (usually the latest)
    - window_minutes: Time window in minutes (default 30)
    
    Returns:
    - List of entries within the window, sorted by timestamp
    """
    try:
        # Parse the target entry's timestamp
        target_time = datetime.fromisoformat(target_entry["timestamp"].replace("Z", "+00:00"))
        window_start = target_time - timedelta(minutes=window_minutes)
        
        # Find all entries within the window
        entries_in_window = []
        
        for entry in all_entries:
            try:
                entry_time = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                
                # Check if entry is within the window and not after the target
                if window_start <= entry_time <= target_time:
                    entries_in_window.append(entry)
                    
            except Exception as e:
                logger.warning(f"Error parsing timestamp for entry {entry['id']}: {str(e)}")
                continue
        
        # Sort by timestamp (oldest first) for chronological reading
        entries_in_window.sort(key=lambda x: datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00")))
        
        return entries_in_window
        
    except Exception as e:
        logger.error(f"Error in get_entries_in_window: {str(e)}")
        return [target_entry]  # Fallback to single entry

async def post_changelog_batch_to_reddit(entries, test_mode=False, force=False):
    """
    Post a batch of changelog entries to Reddit as a single post.
    
    Parameters:
    - entries: List of changelog entries to post (should be in chronological order)
    - test_mode: If True, simulates posting without making actual Reddit API calls
    - force: If True, bypasses duplicate checking and posts anyway
    
    Returns:
    - (success, message): Tuple of success boolean and result message
    """
    
    if not entries:
        return False, "No entries provided"
    
    # Generate batch ID
    batch_id = generate_batch_id(entries)
    
    # Check if this batch has already been posted (unless force is True)
    if not force:
        posts_data = get_posted_entries()
        for post in posts_data["posts"]:
            # Check if this exact batch was posted
            if post.get("batch_id") == batch_id:
                logger.info(f"Batch {batch_id} already posted to Reddit as {post['post_id']}")
                return True, f"Already posted: {post['url']} (use force=True to override)"
            
            # Also check if any individual entries were already posted
            for entry in entries:
                if post["entry_id"] == entry["id"] and not post.get("batch_id"):
                    logger.warning(f"Entry {entry['id']} was already posted individually")
                    if not force:
                        return False, f"Entry {entry['id']} was already posted individually (use force=True to override)"
    
    # Format the batch for Reddit
    formatted_body = format_batched_changelog_for_reddit(entries, batch_id)
    
    # Create title
    if len(entries) == 1:
        # Single entry - use existing logic
        content_lines = entries[0]["content"].split('\n')
        title_text = next((line for line in content_lines if line.strip()), "Heroes' Journey Update")
        title = f"Update: {title_text[:80]}" if len(title_text) > 80 else f"Update: {title_text}"
    else:
        # Multiple entries - create a summary title
        try:
            date = datetime.fromisoformat(entries[-1]["timestamp"].replace("Z", "+00:00")).strftime("%B %d, %Y")
            title = f"Heroes' Journey Updates - {date} ({len(entries)} changes)"
        except:
            title = f"Heroes' Journey Updates - Multiple Changes ({len(entries)} updates)"
    
    # If in test mode, just return the formatted content without posting
    if test_mode:
        logger.info(f"TEST MODE: Would post batch {batch_id} with {len(entries)} entries")
        return True, f"Test successful - would post batch of {len(entries)} entries to Reddit (test mode enabled)"
    
    # Initialize Reddit API
    reddit = await initialize_reddit()
    if not reddit:
        logger.error("Failed to initialize Reddit API")
        return False, "Failed to initialize Reddit API"
    
    try:
        # Get the subreddit
        subreddit = await reddit.subreddit(REDDIT_SUBREDDIT)
        
        # Create the post
        submission = await subreddit.submit(title, selftext=formatted_body)
        
        # Load the submission to access its attributes
        await submission.load()
        
        logger.info(f"Created new batch post for {len(entries)} entries: {submission.id} - {submission.title}")
        
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
        
        # Save post info with batch tracking
        save_batch_post_info(
            batch_id,
            entries,
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
        
        return True, f"Created batch post with {len(entries)} entries{status_message}: {submission.url}"
        
    except Exception as e:
        logger.error(f"Error creating Reddit batch post: {str(e)}")
        logger.error(traceback.format_exc())
        return False, f"Error: {str(e)}"
    finally:
        # Ensure Reddit session is closed
        try:
            await reddit.close()
        except:
            pass

def save_batch_post_info(batch_id, entries, post_id, title, url, flair_applied=None, force_used=False):
    """Save information about a batched changelog post."""
    posts_data = get_posted_entries()
    
    # Create list of entry IDs in the batch
    entry_ids = [e["id"] for e in entries]
    
    # Add the new post
    posts_data["posts"].append({
        "batch_id": batch_id,
        "entry_ids": entry_ids,
        "entry_id": entries[-1]["id"],  # Keep for compatibility
        "post_id": post_id,
        "title": title,
        "url": url,
        "flair": flair_applied,
        "posted_at": datetime.now().isoformat(),
        "pinned": True,
        "force_used": force_used,
        "entry_count": len(entries)
    })
    
    # Sort posts by posted_at to maintain chronological order
    posts_data["posts"].sort(key=lambda x: x["posted_at"], reverse=True)
    
    try:
        with open(REDDIT_POSTS_PATH, 'w') as f:
            json.dump(posts_data, f, indent=2)
        logger.info(f"Saved batch post info for {len(entries)} entries: {post_id}")
    except Exception as e:
        logger.error(f"Error saving batch post info: {str(e)}")

async def post_changelog_to_reddit(entry, test_mode=False, force=False):
    """
    Post a changelog entry to Reddit. This now checks for nearby entries to batch.
    
    Parameters:
    - entry: The changelog entry to post
    - test_mode: If True, simulates posting without making actual Reddit API calls
    - force: If True, bypasses duplicate checking and posts anyway
    
    Returns:
    - (success, message): Tuple of success boolean and result message
    """
    
    # Import the function to get all changelogs
    import importlib.util
    spec = importlib.util.spec_from_file_location("Patcher_API", "/app/Patcher_API.py")
    api_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api_module)
    
    # Get all changelog entries
    try:
        changelogs_response = await api_module.get_changelog(all=True)
        all_entries = changelogs_response.get("changelogs", [])
    except Exception as e:
        logger.error(f"Error getting all changelogs: {str(e)}")
        # Fallback to single entry
        all_entries = [entry]
    
    # Find entries within the time window
    entries_to_post = await get_entries_in_window(all_entries, entry, window_minutes=30)
    
    logger.info(f"Found {len(entries_to_post)} entries within 30-minute window of entry {entry['id']}")
    
    # Use the batch posting function
    return await post_changelog_batch_to_reddit(entries_to_post, test_mode=test_mode, force=force)

# Async helper functions for testing
async def get_reddit_info():
    """Get basic Reddit information for testing."""
    reddit = await initialize_reddit()
    if not reddit:
        return None
    
    try:
        subreddit = await reddit.subreddit(REDDIT_SUBREDDIT)
        
        # Check moderator status
        is_mod = False
        mod_permissions = []

        try:
            # Fix: Await the moderator() call first
            moderators = await subreddit.moderator()
            for mod in moderators:
                if mod.name.lower() == REDDIT_USERNAME.lower():
                    is_mod = True
                    # Get mod permissions if available
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
    
async def test_pin_post(post_id):
    """Test pinning a specific Reddit post."""
    reddit = await initialize_reddit()
    if not reddit:
        return None
    
    try:
        submission = await reddit.submission(id=post_id)
        await submission.load()
        
        # Get the subreddit
        subreddit = await reddit.subreddit(submission.subreddit.display_name)
        
        # Check if user is moderator
        is_mod = False
        mod_permissions = []
        try:
            # Fix: Await the moderator() call first
            moderators = await subreddit.moderator()
            for mod in moderators:
                if mod.name.lower() == REDDIT_USERNAME.lower():
                    is_mod = True
                    if hasattr(mod, 'mod_permissions'):
                        mod_permissions = list(mod.mod_permissions)
                    break
        except Exception as e:
            logger.warning(f"Could not check moderator status: {e}")
            is_mod = False
            mod_permissions = []
                
        # Try to pin
        pin_success = False
        pin_error = None
        if is_mod:
            try:
                await submission.mod.sticky()
                pin_success = True
            except Exception as e:
                pin_error = str(e)
                logger.error(f"Error pinning: {pin_error}")
        
        result = {
            "post_id": post_id,
            "post_title": submission.title,
            "subreddit": f"r/{subreddit.display_name}",
            "account": REDDIT_USERNAME,
            "is_moderator": is_mod,
            "mod_permissions": mod_permissions,
            "pin_attempted": is_mod,
            "pin_successful": pin_success,
            "pin_error": pin_error
        }
        
        await reddit.close()
        return result
        
    except Exception as e:
        logger.error(f"Error accessing post: {str(e)}")
        try:
            await reddit.close()
        except:
            pass
        return None