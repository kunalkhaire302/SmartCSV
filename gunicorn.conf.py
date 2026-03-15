import os

# Gunicorn configuration
# Binds gracefully to the PORT environment variable provided by Railway/Render
port = os.environ.get("PORT", "5000")
bind = f"0.0.0.0:{port}"

workers = 2
timeout = 120
