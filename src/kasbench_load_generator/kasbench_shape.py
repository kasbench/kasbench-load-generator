"""Custom Locust LoadTestShape for KASBench variable load profiles."""

import random

from locust import LoadTestShape, events

# Register custom command-line arguments for the Locust subprocess
@events.init_command_line_parser.add_listener
def _(parser, **kwargs):
    parser.add_argument("--role", type=str, default="")
    parser.add_argument("--benchmark-length-minutes", type=int, default=60)
    parser.add_argument("--base-load-intensity", type=int, default=100)
    parser.add_argument("--base-delay-percentage", type=int, default=100)
    parser.add_argument("--kasbench-url", type=str, default="")
    parser.add_argument("--fixed", type=int, default=-1)


# Precalculated intensity lookup tables mapping simulated minute (at 30-min
# intervals) to user count for each role. Values represent realistic daily
# trading patterns.
INTENSITY_LOOKUP: dict[str, dict[int, int]] = {
        "portfolio-manager": {
            0: 11, 30: 16, 60: 46, 90: 46, 120: 46, 150: 46, 
            180: 36, 210: 31, 240: 26, 270: 16, 300: 16, 330: 16, 
            360: 23, 390: 35, 420: 110, 450: 110, 480: 110, 510: 110, 
            540: 110, 570: 85, 600: 73, 630: 60, 660: 68, 690: 55, 
            720: 55, 750: 45, 780: 35, 810: 28, 840: 28, 870: 28, 
            900: 28, 930: 28, 960: 78, 990: 78, 1020: 78, 1050: 53, 
            1080: 28, 1110: 9, 1140: 9, 1170: 9, 1200: 9, 1230: 9, 
            1260: 9, 1290: 9, 1320: 9, 1350: 9, 1380: 9, 1410: 9
        },
        "trader": {
            0: 32, 30: 32, 60: 32, 90: 32, 120: 32, 150: 32, 
            180: 36, 210: 36, 240: 36, 270: 36, 300: 36, 330: 36, 
            360: 36, 390: 36, 420: 36, 450: 36, 480: 36, 510: 36, 
            540: 36, 570: 108, 600: 108, 630: 108, 660: 108, 690: 108, 
            720: 80, 750: 80, 780: 72, 810: 72, 840: 72, 870: 72, 
            900: 72, 930: 72, 960: 16, 990: 16, 1020: 8, 1050: 8, 
            1080: 12, 1110: 12, 1140: 12, 1170: 12, 1200: 12, 1230: 44, 
            1260: 44, 1290: 44, 1320: 44, 1350: 44, 1380: 44, 1410: 44
        },
        "back-office": {
            0: 36, 30: 36, 60: 36, 90: 36, 120: 36, 150: 36, 
            180: 36, 210: 36, 240: 36, 270: 36, 300: 36, 330: 36, 
            360: 36, 390: 36, 420: 166, 450: 166, 480: 166, 510: 166, 
            540: 166, 570: 166, 600: 166, 630: 166, 660: 166, 690: 166, 
            720: 166, 750: 166, 780: 166, 810: 166, 840: 166, 870: 130, 
            900: 130, 930: 130, 960: 130, 990: 130, 1020: 130, 1050: 130, 
            1080: 130, 1110: 130, 1140: 36, 1170: 36, 1200: 36, 1230: 36, 
            1260: 36, 1290: 36, 1320: 36, 1350: 36, 1380: 36, 1410: 36
        },
        "investor": {
            0: 26, 30: 26, 60: 26, 90: 26, 120: 26, 150: 26, 
            180: 26, 210: 26, 240: 26, 270: 26, 300: 26, 330: 26, 
            360: 26, 390: 26, 420: 26, 450: 26, 480: 44, 510: 44, 
            540: 44, 570: 44, 600: 44, 630: 44, 660: 44, 690: 44, 
            720: 44, 750: 44, 780: 44, 810: 44, 840: 44, 870: 44, 
            900: 44, 930: 44, 960: 44, 990: 44, 1020: 44, 1050: 44, 
            1080: 64, 1110: 64, 1140: 64, 1170: 64, 1200: 64, 1230: 64, 
            1260: 64, 1290: 64, 1320: 64, 1350: 64, 1380: 26, 1410: 26
        }
    }

# Maximum user caps per role (used during exogenous events)
MAX_USERS: dict[str, int] = {
    "portfolio-manager": 175,
    "trader": 160,
    "back-office": 290,
    "investor": 100000,
}


class KasbenchCustomShape(LoadTestShape):
    """Custom shape that maps simulated time to user count via INTENSITY_LOOKUP.

    The shape compresses a 24-hour (1440-minute) simulated day into the
    configured benchmark duration using a ratio. It looks up user counts
    from precalculated tables at 30-minute intervals, applies an exogenous
    event spike, and scales by base_load_intensity.
    """

    # Random exogenous event minute, chosen once at class definition time
    EXOGENOUS_EVENT_MINUTE: int = random.randint(60, 1380)

    def tick(self) -> tuple[int, int] | None:
        """Return (user_count, spawn_rate) for the current tick, or None to stop.

        Reads configuration from Locust's parsed command-line options via
        self.runner.environment.parsed_options.
        """
        options = self.runner.environment.parsed_options

        role: str = options.role
        benchmark_length_minutes: int = options.benchmark_length_minutes
        base_load_intensity: int = options.base_load_intensity
        spawn_rate: int = options.spawn_rate
        fixed = options.fixed

        # Compression factor: maps real time to simulated 1440-minute day
        ratio = 1440 / benchmark_length_minutes

        # Calculate simulated elapsed minutes
        simulated_minutes: int = int(self.get_run_time() * ratio) // 60

        # Terminate if we've completed the simulated day
        if simulated_minutes >= 1440:
            return None

        # Fixed always takes priority
        if fixed > 0:
            return (fixed, spawn_rate)

        # IT-operations always returns constant 1 user
        if role == "it-operations":
            return (1, spawn_rate)

        # Compute lookup key (floor to nearest 30-minute boundary)
        lookup_key: int = int(simulated_minutes // 30) * 30

        # Get base user count from intensity lookup
        lookup_value: int = INTENSITY_LOOKUP[role][lookup_key]
        user_count: int = lookup_value

        # Apply exogenous event spike if within ±30 minutes of event
        if abs(simulated_minutes - self.EXOGENOUS_EVENT_MINUTE) <= 30:
            user_count = min(int(1.5 * lookup_value), MAX_USERS[role] * base_load_intensity / 100.0)

        # Apply base_load_intensity scaling
        user_count = int(user_count * base_load_intensity / 100.0)

        return (user_count, spawn_rate)
