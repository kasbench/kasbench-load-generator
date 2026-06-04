FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN uv sync --no-dev

# Copy application source
COPY main.py ./
COPY src/ ./src/

# Create data directory for database and output file storage
RUN mkdir -p /data

# Environment variables with defaults
ENV DB_PATH=/home/ubuntu/data/kasbench.db
ENV OUTPUT_PATH=/home/ubuntu/data/output.log
ENV HOST=0.0.0.0
ENV PORT=8080
ENV TERMINATION_TIMEOUT_SECONDS=10
ENV STATUS_UPDATE_TIMEOUT_SECONDS=5
ENV RABBITMQ_HOST=localhost
ENV RABBITMQ_PORT=5672

EXPOSE 8080

CMD ["uv", "run", "python", "main.py"]
