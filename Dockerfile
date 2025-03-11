FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Start the bot directly without exposing environment
CMD ["python", "-u", "bot.py"] 