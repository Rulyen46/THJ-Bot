FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set default port to 80
ENV PORT=80

# Expose port 80 for Azure Web App
EXPOSE 80

# Start the bot directly without exposing environment
CMD ["python", "-u", "bot.py"] 