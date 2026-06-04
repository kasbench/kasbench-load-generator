# Implementation Plan: Dockerfile Setup

## Overview

This plan implements Docker containerization for the kasbench-load-generator service. It starts with refactoring config.py to support environment variables (the testable core), then builds the Dockerfile and shell script around it, and finishes with documentation and integration wiring.

## Tasks

- [x] 1. Refactor config.py for environment variable support
  - [x] 1.1 Implement `_parse_positive_int` helper and refactor config.py
    - Add `import sys` to config.py
    - Implement `_parse_positive_int(name: str, default: int) -> int` that reads `os.environ.get(name)`, parses as int, validates > 0, and calls `sys.exit(1)` with stderr message on failure
    - Replace all hardcoded constants with `os.environ.get(KEY, default)` for strings and `_parse_positive_int(KEY, default)` for integers
    - Remove `os.path.expanduser` calls — use direct env var defaults (`/data/kasbench.db`, `/data/output.log`)
    - Ensure module-level interface is unchanged: DB_PATH, OUTPUT_PATH, HOST, PORT, TERMINATION_TIMEOUT_SECONDS, STATUS_UPDATE_TIMEOUT_SECONDS, RABBITMQ_HOST, RABBITMQ_PORT
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

  - [ ]* 1.2 Write property tests for config.py validation logic
    - Create `tests/test_config.py`
    - Use Hypothesis with `@settings(max_examples=100)`
    - **Property 1: String environment variable override** — for any non-empty string and any string config var (DB_PATH, OUTPUT_PATH, HOST, RABBITMQ_HOST), setting the env var returns that value; unsetting returns the default
    - **Property 2: Integer environment variable parsing** — for any positive integer and any numeric config var (PORT, TERMINATION_TIMEOUT_SECONDS, STATUS_UPDATE_TIMEOUT_SECONDS, RABBITMQ_PORT), setting the env var to its string representation returns that integer; unsetting returns the default
    - **Property 3: Invalid numeric environment variable rejection** — for any string that is not a positive integer (non-numeric, negative, zero, float, empty), the config module raises SystemExit with an error message naming the variable
    - _Requirements: 2.1–2.10_

  - [ ]* 1.3 Write example-based unit tests for config defaults
    - Verify each of the 8 config values matches documented defaults when no env vars are set
    - Verify PORT, TERMINATION_TIMEOUT_SECONDS, STATUS_UPDATE_TIMEOUT_SECONDS, RABBITMQ_PORT are `int` type
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

- [x] 2. Checkpoint - Validate config refactor
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Create Dockerfile
  - [x] 3.1 Create Dockerfile in project root
    - Use base image `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`
    - Set `WORKDIR /app`
    - Copy `pyproject.toml` and `uv.lock` first (layer caching)
    - Run `uv sync --no-dev` to install production dependencies
    - Copy `main.py` and `src/` into the image
    - Create `/data` directory with `RUN mkdir -p /data`
    - Declare all 8 `ENV` variables with their default values
    - Add `EXPOSE 8080`
    - Set `CMD ["uv", "run", "python", "main.py"]`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.11_

- [x] 4. Create build_and_push.sh script
  - [x] 4.1 Create build_and_push.sh in project root
    - Add shebang `#!/usr/bin/env bash` and `set -e`
    - Validate exactly 2 arguments; if missing, print usage to stderr and exit 1
    - Assign `REPO=$1` and `TAG=$2`
    - Run `docker build -t "${REPO}:${TAG}" .` with error check; on failure print `"Error: Docker build failed"` to stderr
    - Run `docker push "${REPO}:${TAG}"` with error check; on failure print `"Error: Docker push failed"` to stderr
    - Make file executable (`chmod +x`)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 4.2 Write unit tests for build_and_push.sh argument validation
    - Invoke script with 0 args and verify non-zero exit + usage message on stderr
    - Invoke script with 1 arg and verify non-zero exit + usage message on stderr
    - _Requirements: 3.7_

- [x] 5. Checkpoint - Validate Dockerfile and script
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Update README with Docker documentation
  - [x] 6.1 Add Docker section to README.md
    - Add a "## Docker" section after the existing "## Configuration" section
    - Include a "### Building the Image" subsection with: `docker build -t kasbench-load-generator .`
    - Include a "### Running the Container" subsection with: `docker run -p 8080:8080 kasbench-load-generator`
    - Include a "### Environment Variable Overrides" subsection with example using at least 2 `-e` flags (e.g., `-e PORT=9090 -e RABBITMQ_HOST=rabbitmq.local`)
    - Include a "### Environment Variables" subsection with a table listing all 8 variables: name, default, one-line description
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The config.py refactor preserves the existing module interface so no downstream code changes are needed

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["3.1", "4.1"] },
    { "id": 3, "tasks": ["4.2", "6.1"] }
  ]
}
```
