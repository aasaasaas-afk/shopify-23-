# Use Python 3.9 slim as the base image for a smaller footprint
FROM python:3.9-slim

# Set working directory inside the container
WORKDIR /app

# Copy requirements.txt and application code
COPY requirements.txt .
COPY app.py .
COPY gunicorn_config.py .

# Install system dependencies and clean up
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get remove -y gcc && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Expose port 5000 for the Flask app
EXPOSE 5000

# Run the application with Gunicorn
CMD ["gunicorn", "--config", "gunicorn_config.py", "app:app"]
