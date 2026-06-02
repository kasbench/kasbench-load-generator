"""Unit tests for SubprocessManager start method and helpers (Task 3.3)."""

import asyncio
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from kasbench_load_generator.models import RoleEnum, StartRequest, StatusEnum
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
def valid_request() -> StartRequest:
    """Create a valid StartRequest."""
    return StartRequest(
        Role=RoleEnum.TRADER,
        BenchmarkLengthMinutes=60,
        BaseLoadIntensity=100,
        SpawnRate=10,
        BaseDelayPercentage=50,
        KasbenchUrl="http://localhost:8080",
    )


class TestPrepareArtifacts:
    """Tests for _prepare_artifacts method."""

    def test_creates_empty_sqlite_db(self, manager: SubprocessManager, tmp_paths: tuple[str, str]) -> None:
        db_path, _ = tmp_paths
        manager._prepare_artifacts()
        assert os.path.exists(db_path)
        # Verify it's a valid SQLite database
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        conn.close()
        assert tables == []  # Empty DB, no application tables

    def test_deletes_existing_db_file(self, manager: SubprocessManager, tmp_paths: tuple[str, str]) -> None:
        db_path, _ = tmp_paths
        # Create a pre-existing file with content
        with open(db_path, "w") as f:
            f.write("old data")
        manager._prepare_artifacts()
        # Should be a fresh SQLite DB now
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        conn.close()
        assert tables == []

    def test_deletes_existing_output_file(self, manager: SubprocessManager, tmp_paths: tuple[str, str]) -> None:
        db_path, output_path = tmp_paths
        # Create pre-existing output file
        with open(output_path, "w") as f:
            f.write("old output")
        manager._prepare_artifacts()
        assert not os.path.exists(output_path)

    def test_handles_missing_db_file_gracefully(self, manager: SubprocessManager, tmp_paths: tuple[str, str]) -> None:
        db_path, _ = tmp_paths
        # Should not raise even if files don't exist
        manager._prepare_artifacts()
        assert os.path.exists(db_path)

    def test_handles_missing_output_file_gracefully(self, manager: SubprocessManager, tmp_paths: tuple[str, str]) -> None:
        _, output_path = tmp_paths
        # Should not raise even if output file doesn't exist
        manager._prepare_artifacts()
        assert not os.path.exists(output_path)


class TestBuildLocustCommand:
    """Tests for _build_locust_command method."""

    def test_command_starts_with_locust(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        assert cmd[0] == "locust"

    def test_command_includes_headless_flag(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        assert "--headless" in cmd

    def test_command_includes_host(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        host_idx = cmd.index("--host")
        assert cmd[host_idx + 1] == "http://localhost:8080"

    def test_command_includes_role(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        role_idx = cmd.index("--role")
        assert cmd[role_idx + 1] == "trader"

    def test_command_includes_benchmark_length_minutes(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        idx = cmd.index("--benchmark-length-minutes")
        assert cmd[idx + 1] == "60"

    def test_command_includes_base_load_intensity(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        idx = cmd.index("--base-load-intensity")
        assert cmd[idx + 1] == "100"

    def test_command_includes_spawn_rate(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        idx = cmd.index("--spawn-rate")
        assert cmd[idx + 1] == "10"

    def test_command_includes_base_delay_percentage(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        idx = cmd.index("--base-delay-percentage")
        assert cmd[idx + 1] == "50"

    def test_command_includes_kasbench_url(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        idx = cmd.index("--kasbench-url")
        assert cmd[idx + 1] == "http://localhost:8080"

    def test_command_f_flag_includes_user_file_and_shape_file(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        cmd = manager._build_locust_command(valid_request)
        f_idx = cmd.index("-f")
        locustfiles = cmd[f_idx + 1]
        assert "trader_user.py" in locustfiles
        assert "kasbench_shape.py" in locustfiles

    @pytest.mark.parametrize(
        "role,expected_file",
        [
            (RoleEnum.PORTFOLIO_MANAGER, "portfolio_manager_user.py"),
            (RoleEnum.TRADER, "trader_user.py"),
            (RoleEnum.BACK_OFFICE, "back_office_user.py"),
            (RoleEnum.INVESTOR, "investor_user.py"),
            (RoleEnum.IT_OPERATIONS, "it_operations_user.py"),
        ],
    )
    def test_command_selects_correct_user_file_for_each_role(
        self, manager: SubprocessManager, role: RoleEnum, expected_file: str
    ) -> None:
        request = StartRequest(
            Role=role,
            BenchmarkLengthMinutes=30,
            BaseLoadIntensity=50,
            SpawnRate=5,
            BaseDelayPercentage=10,
            KasbenchUrl="http://example.com",
        )
        cmd = manager._build_locust_command(request)
        f_idx = cmd.index("-f")
        locustfiles = cmd[f_idx + 1]
        assert expected_file in locustfiles


class TestStart:
    """Tests for the start method."""

    @pytest.mark.asyncio
    async def test_start_raises_409_when_already_running(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        manager._status = StatusEnum.RUNNING
        with pytest.raises(HTTPException) as exc_info:
            await manager.start(valid_request)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_start_resets_counters(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        # Set non-zero values
        manager._status = StatusEnum.COMPLETED
        manager._success_count = 42
        manager._failure_count = 7
        manager._internal_error_count = 3
        manager._last_five_errors = ["err1", "err2", "err3"]

        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            await manager.start(valid_request)

        assert manager._success_count == 0
        assert manager._failure_count == 0
        assert manager._internal_error_count == 0
        assert manager._last_five_errors == []

    @pytest.mark.asyncio
    async def test_start_sets_status_to_running(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            await manager.start(valid_request)

        assert manager._status == StatusEnum.RUNNING

    @pytest.mark.asyncio
    async def test_start_sets_role(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            await manager.start(valid_request)

        assert manager._role == "trader"

    @pytest.mark.asyncio
    async def test_start_returns_start_timestamp(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            response = await manager.start(valid_request)

        # Verify timestamp format
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
        assert re.match(pattern, response.StartTimeStamp)

    @pytest.mark.asyncio
    async def test_start_launches_subprocess(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("kasbench_load_generator.subprocess_manager.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            await manager.start(valid_request)

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        # Verify it was called with the command list
        cmd = call_args[0][0]
        assert cmd[0] == "locust"

    @pytest.mark.asyncio
    async def test_start_creates_monitor_task(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.poll.return_value = 0  # Process already exited
            mock_popen.return_value = mock_process
            await manager.start(valid_request)

        assert manager._monitor_task is not None

    @pytest.mark.asyncio
    async def test_start_raises_500_on_oserror(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("kasbench_load_generator.subprocess_manager.subprocess.Popen", side_effect=OSError("exec failed")):
            with pytest.raises(HTTPException) as exc_info:
                await manager.start(valid_request)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_start_raises_500_on_permission_error(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("kasbench_load_generator.subprocess_manager.subprocess.Popen", side_effect=PermissionError("denied")):
            with pytest.raises(HTTPException) as exc_info:
                await manager.start(valid_request)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_start_raises_503_on_memory_error(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("kasbench_load_generator.subprocess_manager.subprocess.Popen", side_effect=MemoryError("out of memory")):
            with pytest.raises(HTTPException) as exc_info:
                await manager.start(valid_request)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_start_raises_503_on_blocking_io_error(self, manager: SubprocessManager, valid_request: StartRequest) -> None:
        with patch("kasbench_load_generator.subprocess_manager.subprocess.Popen", side_effect=BlockingIOError("resource busy")):
            with pytest.raises(HTTPException) as exc_info:
                await manager.start(valid_request)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_start_prepares_artifacts(self, manager: SubprocessManager, valid_request: StartRequest, tmp_paths: tuple[str, str]) -> None:
        db_path, _ = tmp_paths
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            await manager.start(valid_request)

        # DB should have been created
        assert os.path.exists(db_path)
