# Implementation Plan: Health Endpoint Enhancements

## Overview

This plan enhances the load generator's health endpoint to provide richer lifecycle observability. Changes span `models.py`, `subprocess_manager.py`, and `app.py`, adding timing fields, expanded status values, live counter polling from Locust's stats DB, and abort endpoint refinements. Existing tests are updated alongside new property-based tests.

## Tasks

- [ ] 1. Update data models and StatusEnum
  - [ ] 1.1 Update StatusEnum and HealthResponse in models.py
    - Replace `COMPLETED = "completed"` with `SUCCESS = "success"`, `FAILED = "failed"`, `ABORTED = "aborted"` in `StatusEnum`
    - Add `StartTime: str | None` and `EndTime: str | None` fields to `HealthResponse`
    - _Requirements: 3.1, 1.1, 2.1_

  - [ ] 1.2 Update existing tests for new StatusEnum values
    - Update `tests/test_models.py` to assert exactly 5 enum values
    - Update `tests/test_subprocess_manager.py` to replace `StatusEnum.COMPLETED` references with the appropriate new status values
    - Update any other test files referencing `COMPLETED` (e.g., `test_health.py`, `test_abort.py`)
    - _Requirements: 3.1, 3.6_

- [ ] 2. Add timing and abort fields to SubprocessManager
  - [ ] 2.1 Add _start_time, _end_time, _aborted fields and update get_health()
    - Add `_start_time: str | None = None`, `_end_time: str | None = None`, `_aborted: bool = False` to `__init__`
    - Update `get_health()` to include `StartTime=self._start_time` and `EndTime=self._end_time` in the returned `HealthResponse`
    - _Requirements: 1.1, 1.2, 2.1, 2.4_

  - [ ] 2.2 Update start() to record StartTime and reset state
    - After successful subprocess launch, record `_start_time` as current UTC timestamp (ISO 8601 with ms precision)
    - Reset `_end_time = None` and `_aborted = False` at the beginning of a successful start
    - Ensure counter resets (already exist) execute correctly with new fields
    - _Requirements: 1.3, 2.5, 3.5, 4.6_

  - [ ] 2.3 Update abort() to set _aborted flag, status ABORTED, and EndTime
    - Set `self._aborted = True` before sending SIGTERM
    - After successful termination, set `self._status = StatusEnum.ABORTED`
    - Record `self._end_time` as current UTC timestamp
    - On OS error during termination, set `self._status = StatusEnum.FAILED` and record error via `_record_error()`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.6, 5.7_

  - [ ]* 2.4 Write unit tests for start/abort state transitions
    - Test that start() records StartTime and resets EndTime/aborted flag
    - Test that abort() sets status to ABORTED and records EndTime
    - Test that abort when not running returns HTTP 409
    - Test that OS error during abort sets status to FAILED
    - _Requirements: 1.3, 2.5, 3.4, 5.4, 5.5, 5.6, 5.7_

- [ ] 3. Enhance _monitor_process() with stats DB polling and status determination
  - [ ] 3.1 Implement stats DB reading in _monitor_process()
    - Add a `_read_stats_db()` helper method that queries `SELECT COALESCE(SUM(num_requests), 0), COALESCE(SUM(num_failures), 0) FROM requests` from the Locust stats SQLite database
    - Wrap DB read in try/except for `sqlite3.Error` and `OSError`, calling `_record_error()` on failure
    - Call `_read_stats_db()` every 1 second in the monitor loop alongside the existing `process.poll()` check
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 3.2 Implement final read and status determination on process exit
    - When `process.poll()` returns not None, perform one final `_read_stats_db()` call
    - If `_aborted` is True, skip status determination (abort already set it)
    - If `_aborted` is False and exit code == 0, set `_status = StatusEnum.SUCCESS`
    - If `_aborted` is False and exit code != 0, set `_status = StatusEnum.FAILED`
    - Record `_end_time` as current UTC timestamp
    - Close the output file handle
    - _Requirements: 3.2, 3.3, 2.2, 4.7_

  - [ ]* 3.3 Write unit tests for monitor loop and stats DB reading
    - Test that `_read_stats_db()` correctly parses success/failure counts from an in-memory SQLite DB
    - Test that DB read errors increment InternalErrorCount and append to LastFiveErrorMessages
    - Test status determination: exit code 0 → SUCCESS, non-zero → FAILED, aborted → ABORTED
    - Test final read is performed on exit
    - _Requirements: 3.2, 3.3, 4.1, 4.2, 4.3, 4.7_

- [ ] 4. Checkpoint - Verify core logic
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Wire abort endpoint and integration
  - [ ] 5.1 Verify POST /abort endpoint wiring in app.py
    - Confirm the existing `/abort` endpoint in `app.py` correctly delegates to `subprocess_manager.abort()`
    - No new route needed — the endpoint already exists; validate it returns the correct response format with new status behavior
    - _Requirements: 5.1, 5.3, 5.5_

  - [ ]* 5.2 Write integration tests for full lifecycle
    - Test full lifecycle: start → health shows running with StartTime, EndTime null → process exits → health shows SUCCESS/FAILED with EndTime set
    - Test abort lifecycle: start → abort → health shows ABORTED with EndTime set
    - Test sequential runs: start → complete → start → verify StartTime updated, EndTime reset, counters reset
    - _Requirements: 1.1, 1.3, 2.1, 2.2, 2.3, 2.5, 3.2, 3.3, 3.4, 4.6_

- [ ] 6. Property-based tests
  - [ ]* 6.1 Write property test for StartTime persistence
    - **Property 1: StartTime is recorded on successful start and persists**
    - **Validates: Requirements 1.1, 1.3, 1.4**
    - Use Hypothesis to generate valid StartRequest objects, verify StartTime is set and persists through terminal states

  - [ ]* 6.2 Write property test for EndTime lifecycle
    - **Property 2: EndTime lifecycle — null while running, set on termination**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.5**
    - Verify EndTime is None while running and non-null in any terminal state

  - [ ]* 6.3 Write property test for status determination
    - **Property 3: Status determination by exit code and abort flag**
    - **Validates: Requirements 3.2, 3.3, 3.4**
    - Generate random exit codes and abort flags, verify correct status assignment

  - [ ]* 6.4 Write property test for counter accuracy
    - **Property 4: Counters reflect Locust statistics database**
    - **Validates: Requirements 4.1, 4.2**
    - Generate in-memory SQLite DBs with random request counts, verify counters match after read

  - [ ]* 6.5 Write property test for error FIFO bound
    - **Property 5: Error recording bounded FIFO**
    - **Validates: Requirements 4.3, 4.4, 4.5**
    - Generate sequences of K errors, verify LastFiveErrorMessages has min(K, 5) entries and InternalErrorCount == K

  - [ ]* 6.6 Write property test for counter reset on start
    - **Property 6: Counter reset on start**
    - **Validates: Requirements 4.6**
    - Set arbitrary counter/error state, call start, verify all counters and errors reset to zero/empty

  - [ ]* 6.7 Write property test for abort rejection when not running
    - **Property 7: Abort rejection when not running**
    - **Validates: Requirements 5.5**
    - Generate any non-running status, verify abort returns HTTP 409

  - [ ]* 6.8 Write property test for abort response format
    - **Property 8: Successful abort returns valid StopTimeStamp**
    - **Validates: Requirements 5.3**
    - Abort a running subprocess, verify response has valid ISO 8601 timestamp with ms precision

- [ ] 7. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The project uses pytest with pytest-asyncio (auto mode) and Hypothesis for property-based tests
- All code changes are in Python, matching the existing project stack

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3"] },
    { "id": 3, "tasks": ["2.4", "3.1"] },
    { "id": 4, "tasks": ["3.2"] },
    { "id": 5, "tasks": ["3.3", "5.1"] },
    { "id": 6, "tasks": ["5.2", "6.1", "6.2", "6.3", "6.4", "6.5", "6.6", "6.7", "6.8"] }
  ]
}
```
