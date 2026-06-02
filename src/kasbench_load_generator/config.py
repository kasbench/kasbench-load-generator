"""Configuration constants for the KASBench Load Generator."""

import os

# File paths for artifacts (fixed container paths)
# Use expanduser to handle ~ in local development; in containers these will be absolute paths.
DB_PATH = os.path.expanduser("~/data/kasbench.db")
OUTPUT_PATH = os.path.expanduser("~/data/output.log")

# Server binding
HOST = "0.0.0.0"
PORT = 8080

# Subprocess management timeouts (seconds)
TERMINATION_TIMEOUT_SECONDS = 10
STATUS_UPDATE_TIMEOUT_SECONDS = 5
