# Gunicorn configuration for production
bind = "0.0.0.0:5000"
workers = 3  # Number of worker processes (adjust based on CPU cores)
threads = 3  # Number of threads per worker
timeout = 60  # Timeout for worker processes
loglevel = "info"  # Logging level
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
