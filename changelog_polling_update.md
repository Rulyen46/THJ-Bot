# Discord Bot Changelog Monitoring Update

## Changes Made

1. Added a polling-based approach to check for new messages in the changelog channel during each heartbeat cycle (every 120 seconds)
2. The bot will now check for new messages during each heartbeat and add them to the changelog.md file
3. This approach ensures changelog updates happen reliably, regardless of whether Discord events are being received

## How It Works

- During each heartbeat cycle (every 120 seconds after initial startup), the bot:
  - Connects to Discord to verify connection status
  - Checks the changelog channel for any new messages
  - Updates the changelog.md file with any new entries found
  - Logs the results of the check

## Testing

1. Start the bot using the normal method
2. Post a message in the changelog channel
3. Within 2 minutes (the heartbeat interval), the message should be detected and added to the changelog.md file
4. Check the logs to confirm that the message was detected and processed

## Troubleshooting

- If the changelog isn't updating, check the bot logs for any error messages
- Verify that the bot has proper permissions to read messages in the changelog channel
- Ensure the CHANGELOG_CHANNEL_ID environment variable is set correctly
- Check file permissions for the changelog.md file to ensure the bot can write to it

To deploy these changes, use the restart_bot.sh script:

```
./restart_bot.sh
```

You'll be prompted for the Azure Web App name and Resource Group.
