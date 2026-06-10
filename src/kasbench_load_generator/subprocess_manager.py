"""Subprocess manager for Locust process lifecycle."""

import asyncio
import os
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

from kasbench_load_generator import config
from kasbench_load_generator.models import (
    AbortResponse,
    HealthResponse,
    StartRequest,
    StartResponse,
    StatusEnum,
)

# Mapping from role to user class file name
_ROLE_TO_USER_FILE: dict[str, str] = {
    "portfolio-manager": "portfolio_manager_user.py",
    "trader": "trader_user.py",
    "back-office": "back_office_user.py",
    "investor": "investor_user.py",
    "it-operations": "it_operations_user.py",
}


class SubprocessManager:
    """Manages exactly one Locust subprocess at a time."""

    def __init__(self, db_path: str, output_path: str) -> None:
        self._db_path = db_path
        self._output_path = output_path

        # In-memory state
        self._status: StatusEnum = StatusEnum.NOT_STARTED
        self._role: str = ""
        self._success_count: int = 0
        self._failure_count: int = 0
        self._internal_error_count: int = 0
        self._last_five_errors: list[str] = []

        # Timing and abort state
        self._start_time: str | None = None
        self._end_time: str | None = None
        self._aborted: bool = False

        # Subprocess placeholders
        self._process: subprocess.Popen | None = None
        self._monitor_task: asyncio.Task | None = None
        self._output_file = None  # Keep file handle open for subprocess lifetime

    @property
    def is_running(self) -> bool:
        """Return True if the subprocess is currently running."""
        return self._status == StatusEnum.RUNNING

    def get_health(self) -> HealthResponse:
        """Return a complete HealthResponse reflecting current state."""
        health = "healthy" if self._internal_error_count == 0 else "unhealthy"
        now = datetime.now(timezone.utc)
        current_timestamp = (
            now.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{now.microsecond // 1000:03d}Z"
        )

        return HealthResponse(
            Status=self._status,
            Role=self._role,
            Health=health,
            SuccessCount=self._success_count,
            FailureCount=self._failure_count,
            InternalErrorCount=self._internal_error_count,
            LastFiveErrorMessages=list(self._last_five_errors),
            CurrentTimeStamp=current_timestamp,
            StartTime=self._start_time,
            EndTime=self._end_time,
        )

    def _record_error(self, msg: str) -> None:
        """Record an internal error, maintaining a bounded FIFO of 5 errors.

        Errors are stored in chronological order (oldest first).
        When the list exceeds 5 entries, the oldest is evicted.
        """
        self._last_five_errors.append(msg)
        if len(self._last_five_errors) > 5:
            self._last_five_errors = self._last_five_errors[-5:]
        self._internal_error_count += 1

    def _prepare_artifacts(self) -> None:
        """Delete old DB and output file, then create a fresh empty SQLite DB.

        Raises:
            OSError: If file operations fail.
        """
        # Delete old DB file (ignore if missing)
        try:
            os.remove(self._db_path)
        except FileNotFoundError:
            pass

        # Create fresh empty SQLite database
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.close()

        # Delete old output file (ignore if missing)
        try:
            os.remove(self._output_path)
        except FileNotFoundError:
            pass

    def _build_locust_command(self, request: StartRequest) -> list[str]:
        """Construct the Locust command-line argument list.

        The command includes --headless mode, the correct user class file
        and shape file via -f, the target host, and all custom arguments.
        """
        # Determine the path to the users directory and shape file
        package_dir = Path(__file__).parent
        user_file = package_dir / "users" / _ROLE_TO_USER_FILE[request.Role.value]
        shape_file = package_dir / "kasbench_shape.py"

        # Locust -f accepts comma-separated file paths
        locustfiles = f"{user_file},{shape_file}"

        return [
            "locust",
            "--headless",
            "-f",
            locustfiles,
            "--host",
            request.KasbenchUrl,
            "--role",
            request.Role.value,
            "--benchmark-length-minutes",
            str(request.BenchmarkLengthMinutes),
            "--base-load-intensity",
            str(request.BaseLoadIntensity),
            "--spawn-rate",
            str(request.SpawnRate),
            "--base-delay-percentage",
            str(request.BaseDelayPercentage),
            "--kasbench-url",
            request.KasbenchUrl,
        ]

    async def start(self, request: StartRequest) -> StartResponse:
        """Launch the Locust subprocess.

        Validates that no subprocess is currently running, prepares artifacts,
        builds the command, launches the process, starts the monitor task,
        resets counters, and returns the start timestamp.

        Raises:
            HTTPException: 409 if already running, 500 for system errors,
                          503 for resource exhaustion.
        """
        if self.is_running:
            raise HTTPException(
                status_code=409,
                detail="A subprocess is already running",
            )

        # Reset state before launch so state is clean even if launch fails
        self._end_time = None
        self._aborted = False
        self._success_count = 0
        self._failure_count = 0
        self._internal_error_count = 0
        self._last_five_errors = []

        try:
            self._prepare_artifacts()
        except (OSError, PermissionError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to prepare artifacts: {exc}",
            ) from exc

        command = self._build_locust_command(request)

        try:
            # Ensure output directory exists
            output_dir = os.path.dirname(self._output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)

            output_file = open(self._output_path, "w")
            self._output_file = output_file  # Keep reference to prevent GC
            self._process = subprocess.Popen(
                command,
                stdout=output_file,
                stderr=output_file,
            )
        except (MemoryError, BlockingIOError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Resource unavailable: {exc}",
            ) from exc
        except (OSError, PermissionError) as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to start subprocess: {exc}",
            ) from exc

        # Update state
        self._status = StatusEnum.RUNNING
        self._role = request.Role.value

        # Start monitor task
        self._monitor_task = asyncio.create_task(self._monitor_process())

        # Generate start timestamp and record it
        now = datetime.now(timezone.utc)
        start_timestamp = (
            now.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{now.microsecond // 1000:03d}Z"
        )
        self._start_time = start_timestamp

        return StartResponse(StartTimeStamp=start_timestamp)

    async def abort(self) -> AbortResponse:
        """Terminate the running subprocess.

        Sends SIGTERM first, waits up to TERMINATION_TIMEOUT_SECONDS for the
        process to exit gracefully. If it doesn't, escalates to SIGKILL.

        Returns:
            AbortResponse with StopTimeStamp in UTC ISO 8601 format.

        Raises:
            HTTPException: 409 if not running, 500 for system errors,
                          503 for resource exhaustion.
        """
        if not self.is_running:
            raise HTTPException(
                status_code=409,
                detail="No subprocess is currently running",
            )

        # Mark as aborted before attempting termination
        self._aborted = True

        try:
            # Send SIGTERM
            self._process.terminate()

            # Wait for graceful exit
            try:
                self._process.wait(timeout=config.TERMINATION_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                # Escalate to SIGKILL
                self._process.kill()
                self._process.wait()

        except (MemoryError, BlockingIOError) as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Resource unavailable: {exc}",
            ) from exc
        except (ProcessLookupError, OSError) as exc:
            self._status = StatusEnum.FAILED
            self._record_error(f"Failed to terminate subprocess: {exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to terminate subprocess: {exc}",
            ) from exc

        # Update status
        self._status = StatusEnum.ABORTED

        # Cancel the monitor task if running
        if self._monitor_task is not None and not self._monitor_task.done():
            self._monitor_task.cancel()

        # Generate stop timestamp
        now = datetime.now(timezone.utc)
        stop_timestamp = (
            now.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{now.microsecond // 1000:03d}Z"
        )

        # Record end time
        self._end_time = stop_timestamp

        return AbortResponse(StopTimeStamp=stop_timestamp)

    def _read_stats_db(self) -> None:
        """Read success/failure counts from the Locust stats SQLite DB.

        The Locust users log every request to a 'logs' table. Successful
        requests have exception='None', failed requests have a non-null
        exception value.

        If the 'logs' table doesn't exist yet (Locust hasn't spawned users),
        this is a no-op — counters stay at their current values.
        """
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT "
                "COALESCE(SUM(CASE WHEN exception = 'None' THEN 1 ELSE 0 END), 0), "
                "COALESCE(SUM(CASE WHEN exception != 'None' THEN 1 ELSE 0 END), 0) "
                "FROM logs"
            )
            row = cursor.fetchone()
            conn.close()
            if row:
                self._success_count = row[0]
                self._failure_count = row[1]
        except sqlite3.OperationalError as exc:
            # "no such table: logs" is expected during Locust startup
            # before users have been spawned — silently skip.
            if "no such table" not in str(exc):
                self._record_error(f"Failed to read stats DB: {exc}")
        except (sqlite3.Error, OSError) as exc:
            self._record_error(f"Failed to read stats DB: {exc}")

    async def _monitor_process(self) -> None:
        """Monitor the subprocess and update status when it exits.

        Polls process.poll() every 1 second while reading stats from the
        Locust SQLite database. When the process exits (poll() returns not
        None), performs a final stats read, determines status based on exit
        code and abort flag, records end time, and closes the output file.
        """
        if self._process is None:
            return

        while self._process.poll() is None:
            self._read_stats_db()
            await asyncio.sleep(1)

        # Process has exited - perform final stats read
        self._read_stats_db()

        # Close output file handle
        if self._output_file is not None:
            self._output_file.close()
            self._output_file = None

        # Skip status determination if aborted (abort() already set status)
        if self._aborted:
            return

        # Determine status based on exit code
        exit_code = self._process.poll()
        if exit_code == 0:
            self._status = StatusEnum.SUCCESS
        else:
            self._status = StatusEnum.FAILED

        # Record end time
        now = datetime.now(timezone.utc)
        self._end_time = (
            now.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{now.microsecond // 1000:03d}Z"
        )
