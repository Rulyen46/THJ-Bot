#!/bin/bash
# Script to restart the Discord bot in Azure

echo "=== Restarting Discord Bot ==="

# Get Azure details interactively if not provided
if [ -z "$APP_NAME" ]; then
    read -p "Enter Azure Web App name: " APP_NAME
fi

if [ -z "$RESOURCE_GROUP" ]; then
    read -p "Enter Resource Group name: " RESOURCE_GROUP
fi

# Deploy latest code changes to Azure
echo "Deploying code changes to $APP_NAME in $RESOURCE_GROUP..."
az webapp deployment source sync --name "$APP_NAME" --resource-group "$RESOURCE_GROUP"

# Restart the web app
echo "Restarting web app..."
az webapp restart --name "$APP_NAME" --resource-group "$RESOURCE_GROUP"

echo "Deployment and restart complete. Wait 1-2 minutes for the bot to initialize."
echo "Then check the logs in Azure Portal or using:"
echo "az webapp log tail --name \"$APP_NAME\" --resource-group \"$RESOURCE_GROUP\""
