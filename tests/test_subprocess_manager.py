"""Unit tests for SubprocessManager class skeleton and state management (Task 3.1)."""

import re
from datetime import datetime, timezone

from kasbench_load_generator.models import StatusEnum
from kasbench_load_generator.subprocess_manager import SubprocessManager


class TestSubprocessManagerInit:
    """Tests for initial state of SubprocessManager."""

    def test_initial_status_is_not_started(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        assert mgr._status == StatusEnum.NOT_STARTED

    def test_initial_role_is_empty_string(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        assert mgr._role == ""

    def test_initial_counters_are_zero(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        assert mgr._success_count == 0
        assert mgr._failure_count == 0
        assert mgr._internal_error_count == 0

    def test_initial_error_list_is_empty(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        assert mgr._last_five_errors == []

    def test_initial_process_is_none(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        assert mgr._process is None

    def test_initial_monitor_task_is_none(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        assert mgr._monitor_task is None


class TestIsRunning:
    """Tests for the is_running property."""

    def test_is_running_false_when_not_started(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        assert mgr.is_running is False

    def test_is_running_true_when_running(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._status = StatusEnum.RUNNING
        assert mgr.is_running is True

    def test_is_running_false_when_completed(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._status = StatusEnum.COMPLETED
        assert mgr.is_running is False


class TestGetHealth:
    """Tests for get_health() method."""

    def test_health_returns_all_fields(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        response = mgr.get_health()
        assert response.Status == StatusEnum.NOT_STARTED
        assert response.Role == ""
        assert response.Health == "healthy"
        assert response.SuccessCount == 0
        assert response.FailureCount == 0
        assert response.InternalErrorCount == 0
        assert response.LastFiveErrorMessages == []
        assert response.CurrentTimeStamp is not None

    def test_health_reports_healthy_when_no_errors(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        assert mgr.get_health().Health == "healthy"

    def test_health_reports_unhealthy_when_errors_exist(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._internal_error_count = 1
        assert mgr.get_health().Health == "unhealthy"

    def test_health_reflects_current_status(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._status = StatusEnum.RUNNING
        mgr._role = "trader"
        response = mgr.get_health()
        assert response.Status == StatusEnum.RUNNING
        assert response.Role == "trader"

    def test_health_timestamp_is_utc_iso8601(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        response = mgr.get_health()
        # Validate ISO 8601 format: YYYY-MM-DDTHH:MM:SS.mmmZ
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
        assert re.match(pattern, response.CurrentTimeStamp), (
            f"Timestamp {response.CurrentTimeStamp!r} doesn't match ISO 8601 format"
        )

    def test_health_timestamp_is_recent(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        before = datetime.now(timezone.utc)
        response = mgr.get_health()
        after = datetime.now(timezone.utc)
        # Parse the timestamp back
        ts = datetime.strptime(response.CurrentTimeStamp, "%Y-%m-%dT%H:%M:%S.%fZ")
        ts = ts.replace(tzinfo=timezone.utc)
        # Truncate before to milliseconds to match format precision
        before_ms = before.replace(microsecond=(before.microsecond // 1000) * 1000)
        assert before_ms <= ts <= after

    def test_health_reflects_counters(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._success_count = 42
        mgr._failure_count = 7
        mgr._internal_error_count = 3
        response = mgr.get_health()
        assert response.SuccessCount == 42
        assert response.FailureCount == 7
        assert response.InternalErrorCount == 3

    def test_health_reflects_error_messages(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._last_five_errors = ["err1", "err2", "err3"]
        response = mgr.get_health()
        assert response.LastFiveErrorMessages == ["err1", "err2", "err3"]


class TestRecordError:
    """Tests for _record_error() method."""

    def test_record_error_adds_to_list(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._record_error("first error")
        assert mgr._last_five_errors == ["first error"]

    def test_record_error_increments_counter(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._record_error("error")
        assert mgr._internal_error_count == 1
        mgr._record_error("another error")
        assert mgr._internal_error_count == 2

    def test_record_error_maintains_chronological_order(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        mgr._record_error("first")
        mgr._record_error("second")
        mgr._record_error("third")
        assert mgr._last_five_errors == ["first", "second", "third"]

    def test_record_error_bounds_at_five(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        for i in range(7):
            mgr._record_error(f"error {i}")
        assert len(mgr._last_five_errors) == 5
        # Should keep the 5 most recent (oldest first)
        assert mgr._last_five_errors == [
            "error 2",
            "error 3",
            "error 4",
            "error 5",
            "error 6",
        ]

    def test_record_error_counter_tracks_all_errors(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        for i in range(10):
            mgr._record_error(f"error {i}")
        # Counter should be total number of errors, not bounded to 5
        assert mgr._internal_error_count == 10
        assert len(mgr._last_five_errors) == 5

    def test_record_error_evicts_oldest_at_boundary(self) -> None:
        mgr = SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")
        for i in range(5):
            mgr._record_error(f"error {i}")
        assert mgr._last_five_errors == [
            "error 0", "error 1", "error 2", "error 3", "error 4"
        ]
        # Adding 6th should evict "error 0"
        mgr._record_error("error 5")
        assert mgr._last_five_errors == [
            "error 1", "error 2", "error 3", "error 4", "error 5"
        ]
