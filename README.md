# KASBench Load Generator

A FastAPI microservice that manages a Locust subprocess to produce variable HTTP load against the GlobeCo application running in Kubernetes. Part of the KASBench benchmarking framework.

## Overview

Five instances of this service run concurrently in separate Docker containers, each executing a distinct load profile:

| Role | Description |
|------|-------------|
| `portfolio-manager` | Simulates portfolio management activity with business-hours peaks |
| `trader` | Simulates trading activity with market-open peaks |
| `back-office` | Simulates back-office processing with settlement-period peaks |
| `investor` | Simulates retail investor traffic with high-volume market-hours spikes |
| `it-operations` | Constant single-user monitoring load |

Each instance compresses a simulated 24-hour day into a configurable benchmark duration using precalculated intensity lookup tables and includes a random exogenous event spike.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) package manager

## Installation

```bash
uv sync
```

## Running

```bash
uv run python main.py
```

The service binds to `0.0.0.0:8080`.

## API Endpoints

### GET /health

Returns the current status of the load generator.

**Response 200:**

```json
{
  "Status": "not-started | running | completed",
  "Role": "trader",
  "Health": "healthy | unhealthy",
  "SuccessCount": 0,
  "FailureCount": 0,
  "InternalErrorCount": 0,
  "LastFiveErrorMessages": [],
  "CurrentTimeStamp": "2026-06-01T10:18:00.000Z"
}
```

### POST /start

Launches a Locust subprocess with the specified parameters.

**Request body:**

```json
{
  "Role": "portfolio-manager",
  "BenchmarkLengthMinutes": 10,
  "BaseLoadIntensity": 100,
  "SpawnRate": 10,
  "BaseDelayPercentage": 50,
  "KasbenchUrl": "http://globeco.local:32080"
}
```

| Field | Type | Constraints |
|-------|------|-------------|
| Role | string | One of: portfolio-manager, trader, back-office, investor, it-operations |
| BenchmarkLengthMinutes | integer | 1–1440 |
| BaseLoadIntensity | integer | 1–1000 (percentage scaling) |
| SpawnRate | integer | 1–100 (users/second ramp rate) |
| BaseDelayPercentage | integer | 0–1000 |
| KasbenchUrl | string | Valid HTTP or HTTPS URL |

**Response 200:**

```json
{
  "StartTimeStamp": "2026-06-01T10:18:00.000Z"
}
```

**Errors:** 409 (already running), 422 (validation), 500 (system error), 503 (resource exhaustion)

### POST /abort

Terminates the running Locust subprocess. Sends SIGTERM, escalates to SIGKILL after 10 seconds.

**Response 200:**

```json
{
  "StopTimeStamp": "2026-06-01T10:18:00.000Z"
}
```

**Errors:** 409 (not running), 500, 503

### GET /download-db

Streams the SQLite database file after the run completes.

**Response 200:** Binary stream (`application/x-sqlite3`)

**Errors:** 409 (still running), 404 (file not found)

### GET /download-output

Streams the captured stdout/stderr from the Locust subprocess.

**Response 200:** Text stream (`text/plain`, may be empty)

**Errors:** 409 (still running), 404 (no run started)

## Architecture

```
src/kasbench_load_generator/
├── app.py                  # FastAPI application and route handlers
├── config.py               # Configuration constants (paths, ports, timeouts)
├── models.py               # Pydantic request/response models
├── subprocess_manager.py   # Locust subprocess lifecycle management
├── kasbench_shape.py       # Custom LoadTestShape with intensity lookup tables
└── users/                  # Locust HttpUser subclasses (one per role)
    ├── portfolio_manager_user.py
    ├── trader_user.py
    ├── back_office_user.py
    ├── investor_user.py
    └── it_operations_user.py
```

The service enforces a single-subprocess constraint — only one Locust process runs at a time. The `SubprocessManager` handles launching, monitoring, and terminating the child process while tracking health counters and error state in memory.

## Load Shape

The `KasbenchCustomShape` class controls user counts per tick:

1. Compresses a 1440-minute simulated day into the configured `BenchmarkLengthMinutes` using a ratio
2. Looks up base user counts from `INTENSITY_LOOKUP` tables at 30-minute intervals
3. Applies a random exogenous event spike (1.5× or MAX_USERS cap) within a 60-minute window
4. Scales the result by `BaseLoadIntensity / 100`

IT-operations bypasses all lookup logic and maintains a constant single user.

## Testing

```bash
uv run pytest
```

Tests use pytest with pytest-asyncio for async endpoint testing and Hypothesis for property-based validation of the shape computation and model constraints.

## Configuration

Fixed container paths (defined in `config.py`):

| Constant | Value | Purpose |
|----------|-------|---------|
| `DB_PATH` | `/data/kasbench.db` | SQLite database written by Locust |
| `OUTPUT_PATH` | `/data/output.log` | Captured subprocess stdout/stderr |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8080` | Server port |
| `TERMINATION_TIMEOUT_SECONDS` | `10` | SIGTERM grace period before SIGKILL |
| `STATUS_UPDATE_TIMEOUT_SECONDS` | `5` | Max delay detecting subprocess exit |

## License

Part of the KASBench dissertation project.
