"""Unit tests for SubprocessManager abort method (Task 3.6)."""

import asyncio
import re
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from kasbench_load_generator.models import StatusEnum
from kasbench_load_generator.subprocess_manager import SubprocessManager


@pytest.fixture
def tmp_paths(tmp_path: Path) -> tuple[str, str]:
    """Provide temporary db_path and output_path."""
    db_path = str(tmp_path / "test.db")
    output_path = str(tmp_path / "output.log")
    return db_path, output_path


@pytest.fixture
def manager(tmp_paths: tuple[str, str]) -> SubprocessManager:
    """Create a SubprocessManager with temp paths."""
    db_path, output_path = tmp_paths
    return SubprocessManager(db_path=db_path, output_path=output_path)


@pytest.fixture
def running_manager(manager: SubprocessManager) -> SubprocessManager:
    """Create a SubprocessManager in running state with a mock process."""
    manager._status = StatusEnum.RUNNING
    mock_process = MagicMock()
    mock_process.terminate = MagicMock()
    mock_process.kill = MagicMock()
    mock_process.wait = MagicMock(return_value=0)
    manager._process = mock_process
    manager._monitor_task = None
    return manager


class TestAbortNotRunning:
    """Tests for abort when no process is running."""

    @pytest.mark.asyncio
    async def test_abort_raises_409_when_not_started(self, manager: SubprocessManager) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await manager.abort()
        assert exc_info.value.status_code == 409
        assert "No subprocess is currently running" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_abort_raises_409_when_completed(self, manager: SubprocessManager) -> None:
        manager._status = StatusEnum.SUCCESS
        with pytest.raises(HTTPException) as exc_info:
            await manager.abort()
        assert exc_info.value.status_code == 409
        assert "No subprocess is currently running" in exc_info.value.detail


class TestAbortGracefulTermination:
    """Tests for abort with graceful SIGTERM termination."""

    @pytest.mark.asyncio
    async def test_abort_sends_sigterm(self, running_manager: SubprocessManager) -> None:
        await running_manager.abort()
        running_manager._process.terminate.assert_called_once()

    @pytest.mark.asyncio
    async def test_abort_waits_for_process_exit(self, running_manager: SubprocessManager) -> None:
        await running_manager.abort()
        running_manager._process.wait.assert_called_once_with(timeout=10)

    @pytest.mark.asyncio
    async def test_abort_does_not_send_sigkill_on_graceful_exit(self, running_manager: SubprocessManager) -> None:
        await running_manager.abort()
        running_manager._process.kill.assert_not_called()

    @pytest.mark.asyncio
    async def test_abort_updates_status_to_aborted(self, running_manager: SubprocessManager) -> None:
        await running_manager.abort()
        assert running_manager._status == StatusEnum.ABORTED

    @pytest.mark.asyncio
    async def test_abort_returns_abort_response_with_timestamp(self, running_manager: SubprocessManager) -> None:
        response = await running_manager.abort()
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
        assert re.match(pattern, response.StopTimeStamp)


class TestAbortSigkillEscalation:
    """Tests for abort with SIGKILL escalation after timeout."""

    @pytest.mark.asyncio
    async def test_abort_sends_sigkill_on_timeout(self, running_manager: SubprocessManager) -> None:
        # Simulate timeout on first wait, then success on second wait
        running_manager._process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="locust", timeout=10),
            0,
        ]
        await running_manager.abort()
        running_manager._process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_abort_waits_again_after_sigkill(self, running_manager: SubprocessManager) -> None:
        running_manager._process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="locust", timeout=10),
            0,
        ]
        await running_manager.abort()
        # wait() called twice: once with timeout, once without
        assert running_manager._process.wait.call_count == 2

    @pytest.mark.asyncio
    async def test_abort_updates_status_after_sigkill(self, running_manager: SubprocessManager) -> None:
        running_manager._process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="locust", timeout=10),
            0,
        ]
        await running_manager.abort()
        assert running_manager._status == StatusEnum.ABORTED

    @pytest.mark.asyncio
    async def test_abort_returns_timestamp_after_sigkill(self, running_manager: SubprocessManager) -> None:
        running_manager._process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="locust", timeout=10),
            0,
        ]
        response = await running_manager.abort()
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
        assert re.match(pattern, response.StopTimeStamp)


class TestAbortMonitorTaskCancellation:
    """Tests for abort cancelling the monitor task."""

    @pytest.mark.asyncio
    async def test_abort_cancels_running_monitor_task(self, running_manager: SubprocessManager) -> None:
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()
        running_manager._monitor_task = mock_task

        await running_manager.abort()
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_abort_does_not_cancel_already_done_monitor_task(self, running_manager: SubprocessManager) -> None:
        mock_task = MagicMock()
        mock_task.done.return_value = True
        mock_task.cancel = MagicMock()
        running_manager._monitor_task = mock_task

        await running_manager.abort()
        mock_task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_abort_handles_no_monitor_task(self, running_manager: SubprocessManager) -> None:
        running_manager._monitor_task = None
        # Should not raise
        response = await running_manager.abort()
        assert response.StopTimeStamp is not None


class TestAbortErrorHandling:
    """Tests for abort error handling."""

    @pytest.mark.asyncio
    async def test_abort_raises_500_on_process_lookup_error(self, running_manager: SubprocessManager) -> None:
        running_manager._process.terminate.side_effect = ProcessLookupError("No such process")
        with pytest.raises(HTTPException) as exc_info:
            await running_manager.abort()
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_abort_raises_500_on_os_error(self, running_manager: SubprocessManager) -> None:
        running_manager._process.terminate.side_effect = OSError("Unexpected OS error")
        with pytest.raises(HTTPException) as exc_info:
            await running_manager.abort()
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_abort_raises_503_on_memory_error(self, running_manager: SubprocessManager) -> None:
        running_manager._process.terminate.side_effect = MemoryError("Out of memory")
        with pytest.raises(HTTPException) as exc_info:
            await running_manager.abort()
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_abort_raises_503_on_blocking_io_error(self, running_manager: SubprocessManager) -> None:
        running_manager._process.terminate.side_effect = BlockingIOError("Resource busy")
        with pytest.raises(HTTPException) as exc_info:
            await running_manager.abort()
        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_abort_raises_500_on_os_error_during_kill(self, running_manager: SubprocessManager) -> None:
        running_manager._process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="locust", timeout=10),
        ]
        running_manager._process.kill.side_effect = OSError("Kill failed")
        with pytest.raises(HTTPException) as exc_info:
            await running_manager.abort()
        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_abort_raises_503_on_memory_error_during_wait(self, running_manager: SubprocessManager) -> None:
        running_manager._process.wait.side_effect = MemoryError("Out of memory")
        with pytest.raises(HTTPException) as exc_info:
            await running_manager.abort()
        assert exc_info.value.status_code == 503
