import os
import praw
import logging
from datetime import datetime
import json
import traceback

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

# Path to store Reddit posts information
REDDIT_POSTS_PATH = "/app/reddit_posts.json"

def initialize_reddit():
    """Initialize and return a Reddit API instance."""
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD, REDDIT_SUBREDDIT]):
        logger.error("Reddit credentials not fully configured!")
        return None
    
    try:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            username=REDDIT_USERNAME,
            password=REDDIT_PASSWORD,
            user_agent=REDDIT_USER_AGENT
        )
        logger.info(f"Successfully authenticated with Reddit as {REDDIT_USERNAME}")
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

def save_post_info(entry_id, post_id, title, url):
    """Save information about a posted changelog entry."""
    posts_data = get_posted_entries()
    
    # Add the new post
    posts_data["posts"].append({
        "entry_id": entry_id,
        "post_id": post_id,
        "title": title,
        "url": url,
        "posted_at": datetime.now().isoformat(),
        "pinned": True
    })
    
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

def format_changelog_for_reddit(message_content, timestamp, author, entry_id):
    """Format a changelog entry for Reddit."""
    try:
        # Convert timestamp to datetime if it's a string
        if isinstance(timestamp, str):
            try:
                formatted_date = datetime.fromisoformat(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                formatted_date = timestamp  # Keep it as is if parsing fails
        else:
            formatted_date = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    except:
        formatted_date = str(timestamp)
    
    formatted_content = f"# Heroes' Journey Changelog Update\n\n"
    formatted_content += f"**Author:** {author}\n"
    formatted_content += f"**Date:** {formatted_date}\n"
    formatted_content += f"**Entry ID:** {entry_id}\n\n"
    formatted_content += f"---\n\n"
    formatted_content += message_content
    formatted_content += "\n\n---\n\n"
    formatted_content += "*This post was automatically generated from the official changelog.*"
    
    return formatted_content

def manage_pinned_posts(reddit, current_post_id):
    """Manage pinned posts in the subreddit.
    
    Reddit only allows 2 pinned posts per subreddit,
    so we need to unpin the oldest one if we're at the limit.
    """
    try:
        subreddit = reddit.subreddit(REDDIT_SUBREDDIT)
        
        # Get currently pinned posts (stickied)
        pinned_posts = list(subreddit.sticky(limit=2))
        
        # If we already have 2 pinned posts, and our current post isn't one of them
        if len(pinned_posts) >= 2 and not any(p.id == current_post_id for p in pinned_posts):
            # Unpin the oldest one (index 1 is the older sticky)
            oldest_post = pinned_posts[1]
            oldest_post.mod.sticky(state=False)
            logger.info(f"Unpinned older post {oldest_post.id} to make room for new pinned post")
            
            # Update our records
            update_pin_status(oldest_post.id, False)
        
        return True
    except Exception as e:
        logger.error(f"Error managing pinned posts: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def post_changelog_to_reddit(entry, test_mode=False):
    """
    Post a single changelog entry to Reddit as a new pinned post.
    
    Parameters:
    - entry: The changelog entry to post
    - test_mode: If True, simulates posting without making actual Reddit API calls
    
    Returns:
    - (success, message): Tuple of success boolean and result message
    """
    # Check if this entry has already been posted
    posts_data = get_posted_entries()
    for post in posts_data["posts"]:
        if post["entry_id"] == entry["id"]:
            logger.info(f"Entry {entry['id']} already posted to Reddit as {post['post_id']}")
            return True, f"Already posted: {post['url']}"
    
    # Format the entry for logging/testing
    formatted_body = format_changelog_for_reddit(
        entry["content"],
        entry["timestamp"],
        entry["author"],
        entry["id"]
    )
    
    # Create title from the first line of content or use a generic title
    content_lines = entry["content"].split('\n')
    title_text = next((line for line in content_lines if line.strip()), "Heroes' Journey Update")
    
    # Truncate title if too long
    title = f"Update: {title_text[:80]}" if len(title_text) > 80 else f"Update: {title_text}"
    
    # If in test mode, just return the formatted content without posting
    if test_mode:
        logger.info(f"TEST MODE: Would post entry {entry['id']} with title '{title}'")
        return True, "Test successful - would post to Reddit (test mode enabled)"
    
    # Initialize Reddit API
    reddit = initialize_reddit()
    if not reddit:
        logger.error("Failed to initialize Reddit API")
        return False, "Failed to initialize Reddit API"
    
    try:
        # Get the subreddit
        subreddit = reddit.subreddit(REDDIT_SUBREDDIT)
        
        # Create the post
        submission = subreddit.submit(title, selftext=formatted_body)
        logger.info(f"Created new post for entry {entry['id']}: {submission.id} - {submission.title}")
        
        # Manage pinned posts before pinning the new one
        manage_pinned_posts(reddit, submission.id)
        
        # Pin the post (if possible)
        try:
            submission.mod.sticky()
            logger.info(f"Successfully pinned post {submission.id}")
        except Exception as e:
            logger.warning(f"Could not pin post {submission.id}: {str(e)}")
        
        # Save post info
        save_post_info(
            entry["id"],
            submission.id,
            submission.title,
            submission.url
        )
        
        return True, f"Created new post: {submission.url}"
    except Exception as e:
        logger.error(f"Error creating Reddit post: {str(e)}")
        logger.error(traceback.format_exc())
        return False, f"Error: {str(e)}"