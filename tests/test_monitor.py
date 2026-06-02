"""Unit tests for _monitor_process method (Task 3.7).

Tests verify:
- Polling detects process exit and updates status to COMPLETED
- Status update occurs within STATUS_UPDATE_TIMEOUT_SECONDS (5 seconds)
- Graceful handling when self._process is None
- Status remains unchanged until the process actually exits
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from kasbench_load_generator.models import StatusEnum
from kasbench_load_generator.subprocess_manager import SubprocessManager


@pytest.fixture
def manager() -> SubprocessManager:
    """Create a SubprocessManager with test paths."""
    return SubprocessManager(db_path="/tmp/test.db", output_path="/tmp/test.log")


class TestMonitorProcessNoneProcess:
    """Tests for _monitor_process when process is None."""

    @pytest.mark.asyncio
    async def test_returns_immediately_when_process_is_none(
        self, manager: SubprocessManager
    ) -> None:
        """If _process is None, the monitor should return without changing status."""
        assert manager._process is None
        original_status = manager._status

        await manager._monitor_process()

        assert manager._status == original_status

    @pytest.mark.asyncio
    async def test_does_not_set_completed_when_process_is_none(
        self, manager: SubprocessManager
    ) -> None:
        """Status should NOT be set to COMPLETED if process was never assigned."""
        manager._status = StatusEnum.NOT_STARTED

        await manager._monitor_process()

        assert manager._status == StatusEnum.NOT_STARTED


class TestMonitorProcessDetectsExit:
    """Tests for _monitor_process detecting process exit."""

    @pytest.mark.asyncio
    async def test_sets_status_completed_when_process_exits(
        self, manager: SubprocessManager
    ) -> None:
        """When process.poll() returns not None, status should become COMPLETED."""
        mock_process = MagicMock()
        # First call returns None (still running), second returns 0 (exited)
        mock_process.poll.side_effect = [None, 0]
        manager._process = mock_process
        manager._status = StatusEnum.RUNNING

        await manager._monitor_process()

        assert manager._status == StatusEnum.COMPLETED

    @pytest.mark.asyncio
    async def test_sets_completed_on_immediate_exit(
        self, manager: SubprocessManager
    ) -> None:
        """If process already exited before first poll, status becomes COMPLETED."""
        mock_process = MagicMock()
        # poll() returns exit code immediately (process already done)
        mock_process.poll.return_value = 0
        manager._process = mock_process
        manager._status = StatusEnum.RUNNING

        await manager._monitor_process()

        assert manager._status == StatusEnum.COMPLETED

    @pytest.mark.asyncio
    async def test_sets_completed_on_nonzero_exit_code(
        self, manager: SubprocessManager
    ) -> None:
        """Status should be COMPLETED regardless of exit code (even non-zero)."""
        mock_process = MagicMock()
        mock_process.poll.return_value = 1  # Non-zero exit code
        manager._process = mock_process
        manager._status = StatusEnum.RUNNING

        await manager._monitor_process()

        assert manager._status == StatusEnum.COMPLETED

    @pytest.mark.asyncio
    async def test_polls_multiple_times_before_detecting_exit(
        self, manager: SubprocessManager
    ) -> None:
        """Should poll repeatedly until process exits."""
        mock_process = MagicMock()
        # Process runs for several polls before exiting
        mock_process.poll.side_effect = [None, None, None, 0]
        manager._process = mock_process
        manager._status = StatusEnum.RUNNING

        await manager._monitor_process()

        assert manager._status == StatusEnum.COMPLETED
        assert mock_process.poll.call_count == 4


class TestMonitorProcessTiming:
    """Tests verifying detection happens within 5 seconds."""

    @pytest.mark.asyncio
    async def test_detects_exit_within_timeout(
        self, manager: SubprocessManager
    ) -> None:
        """Monitor should detect exit within STATUS_UPDATE_TIMEOUT_SECONDS (5s).

        We simulate a process that exits after 1 poll cycle. With 1s sleep,
        detection should happen well within 5 seconds.
        """
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, 0]
        manager._process = mock_process
        manager._status = StatusEnum.RUNNING

        async def fake_sleep(seconds):
            pass

        # Use a patched sleep to speed up the test
        with patch(
            "kasbench_load_generator.subprocess_manager.asyncio.sleep",
            side_effect=fake_sleep,
        ) as mock_sleep:
            await manager._monitor_process()

        assert manager._status == StatusEnum.COMPLETED
        # Verify sleep was called with 1 second interval
        mock_sleep.assert_called_with(1)

    @pytest.mark.asyncio
    async def test_sleep_interval_is_one_second(
        self, manager: SubprocessManager
    ) -> None:
        """Verify the poll interval is 1 second (satisfies the 5s timeout requirement)."""
        mock_process = MagicMock()
        mock_process.poll.side_effect = [None, None, 0]
        manager._process = mock_process
        manager._status = StatusEnum.RUNNING

        async def fake_sleep(seconds):
            pass

        with patch(
            "kasbench_load_generator.subprocess_manager.asyncio.sleep",
            side_effect=fake_sleep,
        ) as mock_sleep:
            await manager._monitor_process()

        # All sleep calls should use 1-second interval
        for call in mock_sleep.call_args_list:
            assert call[0][0] == 1


class TestMonitorProcessAsAsyncTask:
    """Tests for _monitor_process running as an asyncio task."""

    @pytest.mark.asyncio
    async def test_can_be_cancelled(self, manager: SubprocessManager) -> None:
        """The monitor task should be cancellable (e.g., during abort)."""
        mock_process = MagicMock()
        # Process never exits on its own
        mock_process.poll.return_value = None
        manager._process = mock_process
        manager._status = StatusEnum.RUNNING

        task = asyncio.create_task(manager._monitor_process())
        await asyncio.sleep(0.01)  # Let the task start
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        # Status should remain RUNNING since process didn't exit
        assert manager._status == StatusEnum.RUNNING

    @pytest.mark.asyncio
    async def test_runs_concurrently_without_blocking(
        self, manager: SubprocessManager
    ) -> None:
        """The monitor should yield control via asyncio.sleep, not block."""
        mock_process = MagicMock()
        # Exit after a couple of polls
        poll_count = 0

        def poll_side_effect():
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 3:
                return 0
            return None

        mock_process.poll.side_effect = poll_side_effect
        manager._process = mock_process
        manager._status = StatusEnum.RUNNING

        # Run the monitor as a task
        task = asyncio.create_task(manager._monitor_process())

        # Other coroutines should be able to run concurrently
        other_ran = False

        async def other_coro():
            nonlocal other_ran
            other_ran = True

        await other_coro()
        await task

        assert other_ran
        assert manager._status == StatusEnum.COMPLETED
