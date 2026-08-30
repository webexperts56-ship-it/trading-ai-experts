FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Ensure data and models directories exist
RUN mkdir -p data models

EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000
ENV ALERTS_ENABLED=true
ENV DESKTOP_ALERTS=false
ENV USE_ML=true

CMD ["python", "run.py"]
