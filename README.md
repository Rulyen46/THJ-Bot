# THJ Changelog Bot

A Discord bot that provides a secure API endpoint for retrieving the latest changelog entry from a designated Discord channel.

## Features

- Monitors a specific Discord channel for changelog entries
- Provides secure API endpoint for patcher to retrieve latest changelog
- Formats changelog entries with proper Markdown formatting

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

## Heartbeat System

The application includes a robust heartbeat system designed specifically for Azure App Service to prevent timeouts and ensure the bot stays connected. Key features:

### Features

- **Dedicated Heartbeat Process**: Runs separately from main application to ensure reliability
- **Multiple Logging Methods**: Uses stdout, stderr, and file-based logging for maximum visibility
- **Graduated Timing**: Starts with frequent heartbeats and reduces frequency over time
- **Health Check API**: Provides REST endpoints to verify system health
- **System Stats**: Monitors memory usage, CPU utilization, and application uptime

### Configuration

Add these to your `.env` file:

```env
# Optional - defaults to 300 seconds (5 minutes)
HEARTBEAT_INTERVAL=300
```

### Heartbeat Endpoints

- `/heartbeat` - Public endpoint that returns basic status information
- `/heartbeat/detail` - Authenticated endpoint that returns detailed system stats (requires PATCHER_TOKEN)

### Testing the Heartbeat System

Run the included test script:

```bash
./run_heartbeat_test.sh
```

Or run the module directly:

```bash
python azure_heartbeat.py
```

### Log Files

Heartbeat logs are stored in:

- `/app/logs/azure_heartbeat.log` (in container)
- `./logs/azure_heartbeat.log` (when mounted via Docker volumes)
