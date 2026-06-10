"""Unit tests for request/response model validation."""

from kasbench_load_generator.models import StatusEnum


class TestStatusEnum:
    """Tests for StatusEnum values."""

    def test_status_enum_has_exactly_five_values(self) -> None:
        """StatusEnum SHALL define exactly five values."""
        assert len(StatusEnum) == 5

    def test_status_enum_contains_expected_values(self) -> None:
        """StatusEnum SHALL contain not-started, running, success, failed, aborted."""
        expected = {"not-started", "running", "success", "failed", "aborted"}
        actual = {member.value for member in StatusEnum}
        assert actual == expected

    def test_status_enum_not_started(self) -> None:
        assert StatusEnum.NOT_STARTED.value == "not-started"

    def test_status_enum_running(self) -> None:
        assert StatusEnum.RUNNING.value == "running"

    def test_status_enum_success(self) -> None:
        assert StatusEnum.SUCCESS.value == "success"

    def test_status_enum_failed(self) -> None:
        assert StatusEnum.FAILED.value == "failed"

    def test_status_enum_aborted(self) -> None:
        assert StatusEnum.ABORTED.value == "aborted"
