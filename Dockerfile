FROM python:3.11-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 80

# Create startup script with better error handling and diagnostics
RUN echo '#!/bin/bash\n\
echo "==== CONTAINER STARTUP DIAGNOSTICS ===="\n\
echo "Current directory: $(pwd)"\n\
echo "Directory contents:"\n\
ls -la\n\
echo "Python version: $(python --version)"\n\
echo "Environment variables:"\n\
env | grep -v TOKEN | grep -v KEY | grep -v PASSWORD\n\
echo "Starting application..."\n\
if [ -f /app/main.py ]; then\n\
  echo "Found main.py, executing..."\n\
  python /app/main.py\n\
else\n\
  echo "ERROR: main.py not found! Directory contents:"\n\
  ls -la /app\n\
  exit 1\n\
fi\n\
' > /app/startup.sh && chmod +x /app/startup.sh

# Set environment variables
ENV PORT=80
ENV PYTHONUNBUFFERED=1

# Use ENTRYPOINT for more reliable execution
ENTRYPOINT ["/app/startup.sh"]