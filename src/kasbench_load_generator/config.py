"""Configuration constants for the KASBench Load Generator."""

import os
import sys


def _parse_positive_int(name: str, default: int) -> int:
    """Parse env var as positive integer, exit with error if invalid.

    Reads os.environ.get(name), parses as int, validates > 0.
    Returns the default if the env var is not set.
    Calls sys.exit(1) with a stderr message on failure.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (ValueError, TypeError):
        print(
            f"Error: {name} must be a positive integer, got '{value}'",
            file=sys.stderr,
        )
        sys.exit(1)
    if parsed <= 0:
        print(
            f"Error: {name} must be a positive integer, got '{value}'",
            file=sys.stderr,
        )
        sys.exit(1)
    return parsed


# File paths for artifacts
DB_PATH: str = os.environ.get("DB_PATH", "/data/kasbench.db")
OUTPUT_PATH: str = os.environ.get("OUTPUT_PATH", "/data/output.log")

# Server binding
HOST: str = os.environ.get("HOST", "0.0.0.0")
PORT: int = _parse_positive_int("PORT", 8080)

# Subprocess management timeouts (seconds)
TERMINATION_TIMEOUT_SECONDS: int = _parse_positive_int("TERMINATION_TIMEOUT_SECONDS", 10)
STATUS_UPDATE_TIMEOUT_SECONDS: int = _parse_positive_int("STATUS_UPDATE_TIMEOUT_SECONDS", 5)

# RabbitMQ settings
RABBITMQ_HOST: str = os.environ.get("RABBITMQ_HOST", "localhost")
RABBITMQ_PORT: int = _parse_positive_int("RABBITMQ_PORT", 5672)

# Number of background publisher greenlets draining the in-process publish
# buffer. Sustained publish throughput scales roughly linearly with this, so
# raise it if you see "publish buffer full" warnings under peak load.
RABBITMQ_PUBLISHERS: int = _parse_positive_int("RABBITMQ_PUBLISHERS", 8)

# Whether published messages are persisted to disk by the broker. Persistence
# forces a per-message fsync that serializes and dominates publish latency under
# load. For a load generator these queues carry transient IDs, so durability is
# off by default for much higher throughput. Set RABBITMQ_PERSISTENT=1 to enable.
RABBITMQ_PERSISTENT: bool = os.environ.get("RABBITMQ_PERSISTENT", "0").lower() in (
    "1", "true", "yes",
)
