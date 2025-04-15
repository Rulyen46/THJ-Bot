FROM python:3.11-slim

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose the port the app runs on
EXPOSE 80

# Set up environment for Azure - ensure PORT is properly used
ENV PORT=80

# Create a startup script to ensure proper execution
RUN echo "#!/bin/bash\necho 'Starting application...'\nls -la /app\necho 'Running main.py...'\npython /app/main.py" > /app/startup.sh && \
    chmod +x /app/startup.sh

# Use ENTRYPOINT for more reliable execution in Azure
ENTRYPOINT ["/app/startup.sh"]