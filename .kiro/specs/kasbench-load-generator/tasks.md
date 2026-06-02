# Implementation Plan: KASBench Load Generator

## Overview

This plan implements the KASBench Load Generator as a FastAPI microservice that manages a Locust subprocess to produce variable HTTP load against the GlobeCo application. Implementation proceeds from core data models and configuration, through subprocess management, to API endpoints and the custom Locust shape class. Property-based tests with Hypothesis validate correctness properties defined in the design.

## Tasks

- [ ] 1. Set up project structure, dependencies, and configuration
  - [ ] 1.1 Configure project dependencies and create module structure
    - Add dependencies to pyproject.toml: fastapi, uvicorn, locust, pydantic, httpx
    - Add dev dependencies: pytest, pytest-asyncio, hypothesis, httpx
    - Create source directory structure: `src/kasbench_load_generator/` with `__init__.py`, `app.py`, `models.py`, `subprocess_manager.py`, `config.py`
    - Create `src/kasbench_load_generator/users/` directory with `__init__.py` and five user class files
    - Create `src/kasbench_load_generator/kasbench_shape.py`
    - Create `tests/` directory with `__init__.py` and test file stubs
    - _Requirements: 1.1, 1.2_

  - [ ] 1.2 Implement configuration constants module (`config.py`)
    - Define `DB_PATH = "/data/kasbench.db"`
    - Define `OUTPUT_PATH = "/data/output.log"`
    - Define `HOST = "0.0.0.0"` and `PORT = 8080`
    - Define `TERMINATION_TIMEOUT_SECONDS = 10`
    - Define `STATUS_UPDATE_TIMEOUT_SECONDS = 5`
    - _Requirements: 1.1, 11.2, 12.2_

- [ ] 2. Implement Pydantic models and validation
  - [ ] 2.1 Implement request/response models (`models.py`)
    - Create `RoleEnum` with values: portfolio-manager, trader, back-office, investor, it-operations
    - Create `StatusEnum` with values: not-started, running, completed
    - Create `StartRequest` with Field validators: Role (RoleEnum), BenchmarkLengthMinutes (ge=1, le=1440), BaseLoadIntensity (ge=1, le=1000), SpawnRate (ge=1, le=100), BaseDelayPercentage (ge=0, le=1000), KasbenchUrl (validated HTTP/HTTPS URL)
    - Create `StartResponse`, `AbortResponse`, `HealthResponse`, `ErrorResponse` models
    - _Requirements: 2.1, 3.4, 3.5_

  - [ ]* 2.2 Write property test for request validation (Property 4)
    - **Property 4: Request validation rejects invalid inputs**
    - Use Hypothesis strategies to generate random StartRequest inputs with invalid fields and verify rejection, and random valid inputs and verify acceptance
    - **Validates: Requirements 3.2, 3.4, 3.5**

- [ ] 3. Implement subprocess manager core
  - [ ] 3.1 Implement SubprocessManager class skeleton and state management
    - Create `SubprocessManager` class with `__init__` accepting `db_path` and `output_path`
    - Implement in-memory state: `_status` (StatusEnum.NOT_STARTED), `_role` (""), `_success_count` (0), `_failure_count` (0), `_internal_error_count` (0), `_last_five_errors` ([])
    - Implement `is_running` property
    - Implement `get_health()` returning a complete `HealthResponse` with current UTC ISO 8601 timestamp
    - Implement `_record_error(msg: str)` maintaining bounded FIFO of 5 errors
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 7.1_

  - [ ]* 3.2 Write property tests for health response (Properties 1, 2, 3)
    - **Property 1: Health response completeness** — For any valid combination of state values, verify all fields present and correctly derived
    - **Property 2: Health field derivation from error count** — Verify healthy/unhealthy based on InternalErrorCount
    - **Property 3: Error list bounded invariant** — For any sequence of N errors, verify list has min(N, 5) entries in chronological order
    - **Validates: Requirements 2.1, 2.3, 2.5, 2.6, 2.7, 2.8**

  - [ ] 3.3 Implement subprocess launch logic (`start` method)
    - Implement `_prepare_artifacts()`: delete old DB, create empty SQLite DB, delete old output file
    - Implement `_build_locust_command(request)`: construct command-line with `--headless`, `--host`, custom arguments (role, benchmark_length_minutes, base_load_intensity, spawn_rate, base_delay_percentage, kasbench_url), and user class selection via `-f` flag
    - Implement `start(request)`: validate state is not running, prepare artifacts, build command, launch subprocess with stdout/stderr redirected to output file, start monitor task, reset counters, return StartTimeStamp
    - Implement error classification: OSError/PermissionError → 500, MemoryError/BlockingIOError → 503
    - _Requirements: 3.1, 3.3, 3.6, 3.7, 3.8, 7.1, 7.3, 10.3, 11.1, 11.2, 11.3, 12.1, 12.2, 12.3, 12.4_

  - [ ]* 3.4 Write property test for command construction (Property 6)
    - **Property 6: Command construction preserves all parameters**
    - Generate random valid StartRequests and verify all six parameters appear in the command list and the correct HttpUser subclass is specified
    - **Validates: Requirements 3.6, 10.3**

  - [ ]* 3.5 Write property test for state reset (Property 7)
    - **Property 7: State reset on new start**
    - Set SubprocessManager to completed with arbitrary non-zero counters and errors, invoke start (mocked subprocess), verify all counters reset to 0 and status is "running"
    - **Validates: Requirements 7.3**

  - [ ] 3.6 Implement subprocess abort logic (`abort` method)
    - Implement `abort()`: verify process is running, send SIGTERM, wait up to 10 seconds, escalate to SIGKILL if not terminated, update status to "completed", return StopTimeStamp
    - Handle ProcessLookupError, OSError → 500; MemoryError/BlockingIOError → 503
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 3.7 Implement subprocess monitor (`_monitor_process` method)
    - Create async task that polls `process.poll()` periodically
    - When process exits, update status to "completed" within 5 seconds
    - _Requirements: 7.2_

  - [ ]* 3.8 Write property test for single subprocess enforcement (Property 5)
    - **Property 5: Single subprocess enforcement**
    - For any operation × state combination, verify 409 is returned when state precondition is violated
    - **Validates: Requirements 3.3, 4.2, 5.2, 6.2, 7.1**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement custom LoadTestShape and user classes
  - [ ] 5.1 Implement KasbenchCustomShape (`kasbench_shape.py`)
    - Define `INTENSITY_LOOKUP` dictionary with all precalculated values for portfolio-manager, trader, back-office, investor
    - Define `MAX_USERS` dictionary: portfolio-manager=175, trader=160, back-office=290, investor=100000
    - Define `EXOGENOUS_EVENT_MINUTE = random.randint(60, 1380)` at class level
    - Implement `tick()` method:
      - Calculate simulated minutes: `int(self.get_run_time() * ratio) // 60`
      - Return None if simulated_minutes >= 1440
      - Return (1, spawn_rate) for it-operations
      - Compute lookup_key: `int(simulated_minutes // 30) * 30`
      - Get base user_count from INTENSITY_LOOKUP
      - Apply exogenous event: if within ±30 of event minute, user_count = max(int(1.5 * lookup_value), MAX_USERS[role])
      - Apply base_load_intensity scaling: `int(user_count * base_load_intensity / 100)`
      - Return (user_count, spawn_rate)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 9.1, 9.2, 9.3_

  - [ ]* 5.2 Write property test for tick normal computation (Property 8)
    - **Property 8: Tick computation for normal operation**
    - Generate random role, elapsed_seconds, base_load_intensity, spawn_rate where simulated minutes < 1440 and not within exogenous window
    - Verify tick returns `(floor(INTENSITY_LOOKUP[role][lookup_key] * base_load_intensity / 100), spawn_rate)`
    - **Validates: Requirements 8.1, 8.2, 8.5, 8.6**

  - [ ]* 5.3 Write property test for tick termination (Property 9)
    - **Property 9: Tick terminates at simulated day boundary**
    - Generate (elapsed_seconds, ratio) pairs where simulated minutes >= 1440
    - Verify tick returns None
    - **Validates: Requirements 8.3**

  - [ ]* 5.4 Write property test for IT-operations constant (Property 10)
    - **Property 10: IT-operations constant user count**
    - Generate random elapsed_seconds, base_load_intensity, spawn_rate for it-operations
    - Verify tick returns (1, spawn_rate)
    - **Validates: Requirements 8.4**

  - [ ]* 5.5 Write property test for exogenous event spike (Property 11)
    - **Property 11: Exogenous event spike computation**
    - Generate random role (not it-operations), simulated minutes within ±30 of event minute
    - Verify user_count before scaling equals max(int(1.5 * INTENSITY_LOOKUP[role][lookup_key]), MAX_USERS[role])
    - **Validates: Requirements 8.7, 9.2**

  - [ ]* 5.6 Write property test for exogenous event minute range (Property 12)
    - **Property 12: Exogenous event minute range invariant**
    - Instantiate KasbenchCustomShape multiple times, verify EXOGENOUS_EVENT_MINUTE is always in [60, 1380]
    - **Validates: Requirements 9.1**

  - [ ] 5.7 Implement Locust HttpUser subclasses
    - Create `users/portfolio_manager_user.py` with `PortfolioManagerUser(HttpUser)` containing a `@task` that uses `between(60, 60)` wait
    - Create `users/trader_user.py` with `TraderUser(HttpUser)`
    - Create `users/back_office_user.py` with `BackOfficeUser(HttpUser)`
    - Create `users/investor_user.py` with `InvestorUser(HttpUser)`
    - Create `users/it_operations_user.py` with `ItOperationsUser(HttpUser)`
    - Export all classes from `users/__init__.py`
    - _Requirements: 10.1, 10.2_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement FastAPI endpoints and wire components together
  - [ ] 7.1 Implement FastAPI application with all endpoints (`app.py`)
    - Create FastAPI instance binding to 0.0.0.0:8080
    - Instantiate `SubprocessManager` with config paths
    - Implement `GET /health` → calls `subprocess_manager.get_health()`, returns 200
    - Implement `POST /start` → validates request (Pydantic handles 400/422), calls `subprocess_manager.start()`, returns 200 with StartTimeStamp, catches HTTPException for 409/500/503
    - Implement `POST /abort` → calls `subprocess_manager.abort()`, returns 200 with StopTimeStamp
    - Implement `GET /download-db` → check status not running (409), check file exists (404), return StreamingResponse with media_type "application/x-sqlite3"
    - Implement `GET /download-output` → check status not running (409), check status not "not-started" (404), return StreamingResponse with media_type "text/plain" (200 even if empty)
    - _Requirements: 1.1, 1.2, 2.1, 3.1, 3.2, 3.3, 4.1, 4.2, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

  - [ ] 7.2 Implement application entry point (`main.py`)
    - Import app and run with uvicorn on HOST:PORT from config
    - _Requirements: 1.1_

  - [ ]* 7.3 Write integration tests for API lifecycle
    - Test initial health returns "not-started"
    - Test start → health shows "running" → process exits → health shows "completed"
    - Test start while running returns 409
    - Test abort while not running returns 409
    - Test download-db/download-output while running returns 409
    - Test download-db when no file returns 404
    - Test download-output when not started returns 404
    - Test download-output with empty output returns 200
    - Test full lifecycle: start → poll → complete → download artifacts
    - _Requirements: 2.2, 2.3, 2.4, 3.1, 3.3, 4.1, 4.2, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4_

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (12 properties total)
- Unit/integration tests validate specific examples and edge cases
- The project uses `uv` as the package manager (Python 3.14)
- All code targets Python 3.14 with type hints throughout
- Subprocess isolation is key: Locust runs as a child process, not in-process
- File paths `/data/kasbench.db` and `/data/output.log` are fixed container paths

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3"] },
    { "id": 4, "tasks": ["3.4", "3.5", "3.6", "3.7"] },
    { "id": 5, "tasks": ["3.8", "5.1", "5.7"] },
    { "id": 6, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6"] },
    { "id": 7, "tasks": ["7.1", "7.2"] },
    { "id": 8, "tasks": ["7.3"] }
  ]
}
```
