"""Configuration constants for the KASBench Load Generator."""

# File paths for artifacts (fixed container paths)
DB_PATH = "/data/kasbench.db"
OUTPUT_PATH = "/data/output.log"

# Server binding
HOST = "0.0.0.0"
PORT = 8080

# Subprocess management timeouts (seconds)
TERMINATION_TIMEOUT_SECONDS = 10
STATUS_UPDATE_TIMEOUT_SECONDS = 5
