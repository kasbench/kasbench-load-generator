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
