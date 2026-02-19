FROM python:3.10-slim

WORKDIR /app

# System deps (needed by some Python packages and for TLS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better caching)
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Run as non-root (optional but nice)
RUN useradd -m -u 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["python", "cli.py", "serve", "--host", "0.0.0.0", "--port", "8000"]
