FROM python:3.9-slim

WORKDIR /app

# Install system dependencies including MySQL client libraries
RUN apt-get update && apt-get install -y \
    build-essential \
    pkg-config \
    curl \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port Streamlit runs on
EXPOSE 8501

# Set up environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create directories that might be needed
RUN mkdir -p /app/assets /app/config

# Add a healthcheck
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Create entrypoint script directly in the container (to avoid line ending issues)
RUN echo '#!/bin/bash' > /docker-entrypoint.sh && \
    echo 'set -e' >> /docker-entrypoint.sh && \
    echo 'echo "Starting maintenance control application..."' >> /docker-entrypoint.sh && \
    echo 'if [ ! -f /app/config/database_config.json ]; then' >> /docker-entrypoint.sh && \
    echo '    echo "Creating minimal configuration..."' >> /docker-entrypoint.sh && \
    echo '    mkdir -p /app/config' >> /docker-entrypoint.sh && \
    echo '    cat > /app/config/database_config.json << EOF' >> /docker-entrypoint.sh && \
    echo '{' >> /docker-entrypoint.sh && \
    echo '    "connection": {' >> /docker-entrypoint.sh && \
    echo '        "type": "mysql",' >> /docker-entrypoint.sh && \
    echo '        "host": "host.docker.internal",' >> /docker-entrypoint.sh && \
    echo '        "port": 3306,' >> /docker-entrypoint.sh && \
    echo '        "user": "root",' >> /docker-entrypoint.sh && \
    echo '        "password": "BootMe!",' >> /docker-entrypoint.sh && \
    echo '        "database": "annadb",' >> /docker-entrypoint.sh && \
    echo '        "fallback_hosts": ["host.docker.internal", "172.17.0.1"]' >> /docker-entrypoint.sh && \
    echo '    }' >> /docker-entrypoint.sh && \
    echo '}' >> /docker-entrypoint.sh && \
    echo 'EOF' >> /docker-entrypoint.sh && \
    echo '    echo "Configuration created successfully"' >> /docker-entrypoint.sh && \
    echo 'fi' >> /docker-entrypoint.sh && \
    echo 'exec "$@"' >> /docker-entrypoint.sh && \
    chmod +x /docker-entrypoint.sh

# Set entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]

# Command to run the application
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
