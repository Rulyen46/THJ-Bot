# THJ Changelog Bot

A Discord bot that provides a secure API endpoint for retrieving the latest changelog entry from a designated Discord channel.

## Features

- Monitors a specific Discord channel for changelog entries
- Provides secure API endpoint for patcher to retrieve latest changelog
- Formats changelog entries with proper Markdown formatting
- *(Coming Soon) Automatic Wiki.js page updates*

## Setup

1. Create a `.env` file with the following variables:
```env
DISCORD_TOKEN=your_discord_token
CHANGELOG_CHANNEL_ID=your_channel_id
PATCHER_TOKEN=your_patcher_token
# Wiki.js integration (coming soon)
# WIKI_API_URL=your_wiki_api_url
# WIKI_API_KEY=your_wiki_api_key
# WIKI_PAGE_ID=your_wiki_page_id
```

2. Build and run with Docker:
```bash
docker-compose up --build -d
```

## API Endpoints

### GET /patcher/latest
Secure endpoint to get the latest changelog entry.

Required header:
```
X-Patcher-Token: your_patcher_token
```

Response format:
```json
{
    "status": "success",
    "found": true,
    "changelog": {
        "raw_content": "Original Discord message",
        "formatted_content": "Formatted markdown content",
        "author": "Author name",
        "timestamp": "ISO timestamp",
        "message_id": "Discord message ID"
    }
}
```

## Development

Requirements:
- Python 3.11+
- Discord.py
- FastAPI
- Docker (optional) 