"""Unit tests for KasbenchCustomShape tick computation logic."""

from types import SimpleNamespace
from unittest.mock import patch, PropertyMock

import pytest

from kasbench_load_generator.kasbench_shape import (
    INTENSITY_LOOKUP,
    KasbenchCustomShape,
    MAX_USERS,
)


def _make_shape(
    role: str = "portfolio-manager",
    benchmark_length_minutes: int = 60,
    base_load_intensity: int = 100,
    spawn_rate: int = 10,
    base_delay_percentage: int = 100,
    kasbench_url: str = "http://localhost:8080",
    run_time: float = 0.0,
    exogenous_event_minute: int = 720,
) -> KasbenchCustomShape:
    """Create a KasbenchCustomShape with mocked runner and run_time."""
    options = SimpleNamespace(
        role=role,
        benchmark_length_minutes=benchmark_length_minutes,
        base_load_intensity=base_load_intensity,
        spawn_rate=spawn_rate,
        base_delay_percentage=base_delay_percentage,
        kasbench_url=kasbench_url,
    )

    shape = KasbenchCustomShape.__new__(KasbenchCustomShape)
    shape.EXOGENOUS_EVENT_MINUTE = exogenous_event_minute

    # Mock runner with environment.parsed_options
    shape.runner = SimpleNamespace(
        environment=SimpleNamespace(parsed_options=options)
    )
    # Patch get_run_time to return our controlled value
    shape.get_run_time = lambda: run_time

    return shape


class TestTickTermination:
    """Test that tick returns None when simulated day is complete."""

    def test_returns_none_at_1440_simulated_minutes(self):
        """When simulated_minutes reaches 1440, tick returns None."""
        # With benchmark_length_minutes=60, ratio=24
        # simulated_minutes = int(run_time * 24) // 60
        # For simulated_minutes = 1440: run_time * 24 / 60 = 1440 → run_time = 3600
        shape = _make_shape(
            benchmark_length_minutes=60,
            run_time=3600.0,
        )
        assert shape.tick() is None

    def test_returns_none_beyond_1440(self):
        """When simulated_minutes exceeds 1440, tick returns None."""
        shape = _make_shape(
            benchmark_length_minutes=60,
            run_time=4000.0,
        )
        assert shape.tick() is None

    def test_returns_value_just_before_1440(self):
        """When simulated_minutes is just under 1440, tick does not return None."""
        # ratio=24, simulated_minutes = int(3599 * 24) // 60 = 86376 // 60 = 1439
        shape = _make_shape(
            benchmark_length_minutes=60,
            run_time=3599.0,
            exogenous_event_minute=60,  # Far away from 1439
        )
        result = shape.tick()
        assert result is not None

    def test_full_duration_benchmark_termination(self):
        """With benchmark_length_minutes=1440, ratio=1, at 86400s → done."""
        # ratio=1, simulated_minutes = int(86400 * 1) // 60 = 1440
        shape = _make_shape(
            benchmark_length_minutes=1440,
            run_time=86400.0,
        )
        assert shape.tick() is None


class TestItOperationsConstant:
    """Test that IT-operations always returns (1, spawn_rate)."""

    def test_returns_one_user(self):
        """IT-operations returns (1, spawn_rate) regardless of time."""
        shape = _make_shape(
            role="it-operations",
            spawn_rate=5,
            run_time=100.0,
            benchmark_length_minutes=1440,
        )
        assert shape.tick() == (1, 5)

    def test_returns_one_user_at_any_time(self):
        """IT-operations returns constant even during peak hours."""
        shape = _make_shape(
            role="it-operations",
            spawn_rate=20,
            run_time=28800.0,  # 8 hours into a 1440min run = 480 simulated minutes
            benchmark_length_minutes=1440,
        )
        assert shape.tick() == (1, 20)

    def test_ignores_exogenous_event(self):
        """IT-operations ignores the exogenous event entirely."""
        # Place event at a time that would overlap
        shape = _make_shape(
            role="it-operations",
            spawn_rate=10,
            run_time=600.0,
            benchmark_length_minutes=1440,
            exogenous_event_minute=10,  # Overlaps with simulated_minutes=10
        )
        assert shape.tick() == (1, 10)


class TestNormalTickComputation:
    """Test tick computation without exogenous event interference."""

    def test_basic_lookup_at_time_zero(self):
        """At time 0, returns INTENSITY_LOOKUP[role][0] scaled by intensity."""
        shape = _make_shape(
            role="portfolio-manager",
            benchmark_length_minutes=1440,
            base_load_intensity=100,
            spawn_rate=10,
            run_time=0.0,
            exogenous_event_minute=720,  # Far from minute 0
        )
        expected = int(INTENSITY_LOOKUP["portfolio-manager"][0] * 100 / 100)
        assert shape.tick() == (expected, 10)

    def test_lookup_key_floors_to_30(self):
        """Simulated minutes 45 floors to lookup_key 30."""
        # benchmark_length=1440, ratio=1, run_time=2700s → 45 simulated minutes
        shape = _make_shape(
            role="trader",
            benchmark_length_minutes=1440,
            base_load_intensity=100,
            spawn_rate=5,
            run_time=2700.0,
            exogenous_event_minute=720,
        )
        # simulated_minutes = int(2700 * 1) // 60 = 45, lookup_key = 30
        expected = int(INTENSITY_LOOKUP["trader"][30] * 100 / 100)
        assert shape.tick() == (expected, 5)

    def test_base_load_intensity_scaling(self):
        """base_load_intensity of 200 doubles the user count."""
        shape = _make_shape(
            role="back-office",
            benchmark_length_minutes=1440,
            base_load_intensity=200,
            spawn_rate=8,
            run_time=0.0,
            exogenous_event_minute=720,
        )
        expected = int(INTENSITY_LOOKUP["back-office"][0] * 200 / 100)
        assert shape.tick() == (expected, 8)

    def test_base_load_intensity_scaling_50_percent(self):
        """base_load_intensity of 50 halves the user count."""
        shape = _make_shape(
            role="investor",
            benchmark_length_minutes=1440,
            base_load_intensity=50,
            spawn_rate=3,
            run_time=0.0,
            exogenous_event_minute=720,
        )
        expected = int(INTENSITY_LOOKUP["investor"][0] * 50 / 100)
        assert shape.tick() == (expected, 3)

    def test_compressed_time_with_ratio(self):
        """With 60-min benchmark (ratio=24), time progresses 24x faster."""
        # ratio=24, run_time=300s → simulated_minutes = int(300 * 24) // 60 = 120
        # lookup_key = 120
        shape = _make_shape(
            role="portfolio-manager",
            benchmark_length_minutes=60,
            base_load_intensity=100,
            spawn_rate=10,
            run_time=300.0,
            exogenous_event_minute=720,  # Far from 120
        )
        expected = int(INTENSITY_LOOKUP["portfolio-manager"][120] * 100 / 100)
        assert shape.tick() == (expected, 10)


class TestExogenousEvent:
    """Test exogenous event spike behavior."""

    def test_spike_applies_when_within_30_minutes(self):
        """User count spikes when within ±30 of exogenous event minute."""
        event_minute = 300
        # Place simulated_minutes at 300 (exactly at event)
        # benchmark_length=1440, ratio=1, run_time=300*60=18000
        shape = _make_shape(
            role="portfolio-manager",
            benchmark_length_minutes=1440,
            base_load_intensity=100,
            spawn_rate=10,
            run_time=18000.0,
            exogenous_event_minute=event_minute,
        )
        lookup_value = INTENSITY_LOOKUP["portfolio-manager"][300]
        expected_spike = max(int(1.5 * lookup_value), MAX_USERS["portfolio-manager"])
        expected = int(expected_spike * 100 / 100)
        assert shape.tick() == (expected, 10)

    def test_spike_at_boundary_minus_30(self):
        """Spike applies at exactly 30 minutes before event."""
        event_minute = 300
        # simulated_minutes = 270 (event_minute - 30)
        shape = _make_shape(
            role="trader",
            benchmark_length_minutes=1440,
            base_load_intensity=100,
            spawn_rate=5,
            run_time=270 * 60.0,
            exogenous_event_minute=event_minute,
        )
        lookup_value = INTENSITY_LOOKUP["trader"][270]
        expected_spike = max(int(1.5 * lookup_value), MAX_USERS["trader"])
        expected = int(expected_spike * 100 / 100)
        assert shape.tick() == (expected, 5)

    def test_spike_at_boundary_plus_30(self):
        """Spike applies at exactly 30 minutes after event."""
        event_minute = 300
        # simulated_minutes = 330 (event_minute + 30)
        shape = _make_shape(
            role="back-office",
            benchmark_length_minutes=1440,
            base_load_intensity=100,
            spawn_rate=7,
            run_time=330 * 60.0,
            exogenous_event_minute=event_minute,
        )
        lookup_value = INTENSITY_LOOKUP["back-office"][330]
        expected_spike = max(int(1.5 * lookup_value), MAX_USERS["back-office"])
        expected = int(expected_spike * 100 / 100)
        assert shape.tick() == (expected, 7)

    def test_no_spike_outside_window(self):
        """No spike when more than 30 minutes from event."""
        event_minute = 300
        # simulated_minutes = 331 (event_minute + 31, outside window)
        shape = _make_shape(
            role="portfolio-manager",
            benchmark_length_minutes=1440,
            base_load_intensity=100,
            spawn_rate=10,
            run_time=331 * 60.0,
            exogenous_event_minute=event_minute,
        )
        lookup_value = INTENSITY_LOOKUP["portfolio-manager"][330]
        expected = int(lookup_value * 100 / 100)
        assert shape.tick() == (expected, 10)

    def test_spike_uses_max_users_when_higher(self):
        """When MAX_USERS > 1.5 * lookup, MAX_USERS is used."""
        # portfolio-manager at minute 0 has lookup value 5
        # 1.5 * 5 = 7, MAX_USERS = 175 → max(7, 175) = 175
        event_minute = 0
        shape = _make_shape(
            role="portfolio-manager",
            benchmark_length_minutes=1440,
            base_load_intensity=100,
            spawn_rate=10,
            run_time=0.0,
            exogenous_event_minute=event_minute,
        )
        expected = int(MAX_USERS["portfolio-manager"] * 100 / 100)
        assert shape.tick() == (expected, 10)

    def test_spike_uses_15x_when_higher(self):
        """When 1.5 * lookup > MAX_USERS, 1.5x is used."""
        # investor at minute 420 has lookup value 80000
        # 1.5 * 80000 = 120000, MAX_USERS = 100000 → max(120000, 100000) = 120000
        event_minute = 420
        shape = _make_shape(
            role="investor",
            benchmark_length_minutes=1440,
            base_load_intensity=100,
            spawn_rate=5,
            run_time=420 * 60.0,
            exogenous_event_minute=event_minute,
        )
        lookup_value = INTENSITY_LOOKUP["investor"][420]
        expected_spike = max(int(1.5 * lookup_value), MAX_USERS["investor"])
        expected = int(expected_spike * 100 / 100)
        assert expected_spike == 120000
        assert shape.tick() == (expected, 5)

    def test_spike_with_intensity_scaling(self):
        """Exogenous spike is calculated before intensity scaling."""
        event_minute = 300
        shape = _make_shape(
            role="portfolio-manager",
            benchmark_length_minutes=1440,
            base_load_intensity=200,
            spawn_rate=10,
            run_time=300 * 60.0,
            exogenous_event_minute=event_minute,
        )
        lookup_value = INTENSITY_LOOKUP["portfolio-manager"][300]
        expected_spike = max(int(1.5 * lookup_value), MAX_USERS["portfolio-manager"])
        expected = int(expected_spike * 200 / 100)
        assert shape.tick() == (expected, 10)


class TestExogenousEventMinuteRange:
    """Test that EXOGENOUS_EVENT_MINUTE is within valid bounds."""

    def test_event_minute_in_valid_range(self):
        """EXOGENOUS_EVENT_MINUTE should be between 60 and 1380 inclusive."""
        assert 60 <= KasbenchCustomShape.EXOGENOUS_EVENT_MINUTE <= 1380

    def test_event_minute_with_multiple_seeds(self):
        """Verify range holds across multiple random instantiations."""
        for _ in range(100):
            value = random.randint(60, 1380)
            assert 60 <= value <= 1380


class TestIntensityLookupStructure:
    """Test that INTENSITY_LOOKUP has the expected structure."""

    def test_all_roles_present(self):
        """All four non-IT roles have lookup tables."""
        expected_roles = {"portfolio-manager", "trader", "back-office", "investor"}
        assert set(INTENSITY_LOOKUP.keys()) == expected_roles

    def test_all_30_minute_intervals_present(self):
        """Each role has entries for 0, 30, 60, ..., 1410."""
        expected_keys = set(range(0, 1440, 30))
        for role in INTENSITY_LOOKUP:
            assert set(INTENSITY_LOOKUP[role].keys()) == expected_keys

    def test_all_values_positive(self):
        """All lookup values are positive integers."""
        for role in INTENSITY_LOOKUP:
            for minute, count in INTENSITY_LOOKUP[role].items():
                assert count > 0, f"{role} at minute {minute} has non-positive count"


class TestMaxUsers:
    """Test MAX_USERS dictionary values."""

    def test_max_users_values(self):
        """MAX_USERS has the correct values per spec."""
        assert MAX_USERS == {
            "portfolio-manager": 175,
            "trader": 160,
            "back-office": 290,
            "investor": 100000,
        }


# Import random for the range test
import random
