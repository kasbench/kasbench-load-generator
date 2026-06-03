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


# Precalculated intensity lookup tables mapping simulated minute (at 30-min
# intervals) to user count for each role. Values represent realistic daily
# trading patterns.
INTENSITY_LOOKUP: dict[str, dict[int, int]] = {
    "portfolio-manager": {
        0: 5,
        30: 5,
        60: 8,
        90: 10,
        120: 12,
        150: 15,
        180: 20,
        210: 30,
        240: 50,
        270: 80,
        300: 100,
        330: 120,
        360: 135,
        390: 145,
        420: 150,
        450: 150,
        480: 145,
        510: 140,
        540: 130,
        570: 120,
        600: 110,
        630: 100,
        660: 90,
        690: 80,
        720: 70,
        750: 60,
        780: 50,
        810: 40,
        840: 35,
        870: 30,
        900: 25,
        930: 20,
        960: 18,
        990: 15,
        1020: 12,
        1050: 10,
        1080: 10,
        1110: 8,
        1140: 8,
        1170: 6,
        1200: 5,
        1230: 5,
        1260: 5,
        1290: 5,
        1320: 5,
        1350: 5,
        1380: 5,
        1410: 5,
    },
    "trader": {
        0: 10,
        30: 10,
        60: 15,
        90: 20,
        120: 25,
        150: 30,
        180: 40,
        210: 60,
        240: 80,
        270: 100,
        300: 120,
        330: 135,
        360: 140,
        390: 140,
        420: 135,
        450: 130,
        480: 130,
        510: 125,
        540: 120,
        570: 115,
        600: 110,
        630: 100,
        660: 90,
        690: 80,
        720: 70,
        750: 60,
        780: 50,
        810: 40,
        840: 35,
        870: 30,
        900: 25,
        930: 20,
        960: 18,
        990: 15,
        1020: 12,
        1050: 10,
        1080: 10,
        1110: 10,
        1140: 10,
        1170: 10,
        1200: 10,
        1230: 10,
        1260: 10,
        1290: 10,
        1320: 10,
        1350: 10,
        1380: 10,
        1410: 10,
    },
    "back-office": {
        0: 20,
        30: 20,
        60: 25,
        90: 30,
        120: 35,
        150: 40,
        180: 50,
        210: 60,
        240: 70,
        270: 80,
        300: 90,
        330: 100,
        360: 110,
        390: 120,
        420: 130,
        450: 140,
        480: 150,
        510: 160,
        540: 180,
        570: 200,
        600: 220,
        630: 240,
        660: 250,
        690: 240,
        720: 220,
        750: 200,
        780: 180,
        810: 150,
        840: 120,
        870: 100,
        900: 80,
        930: 70,
        960: 60,
        990: 50,
        1020: 45,
        1050: 40,
        1080: 35,
        1110: 30,
        1140: 25,
        1170: 25,
        1200: 20,
        1230: 20,
        1260: 20,
        1290: 20,
        1320: 20,
        1350: 20,
        1380: 20,
        1410: 20,
    },
    "investor": {
        0: 100,
        30: 100,
        60: 150,
        90: 200,
        120: 300,
        150: 500,
        180: 1000,
        210: 2000,
        240: 5000,
        270: 10000,
        300: 20000,
        330: 40000,
        360: 60000,
        390: 75000,
        420: 80000,
        450: 75000,
        480: 70000,
        510: 65000,
        540: 60000,
        570: 50000,
        600: 40000,
        630: 30000,
        660: 20000,
        690: 15000,
        720: 10000,
        750: 8000,
        780: 5000,
        810: 3000,
        840: 2000,
        870: 1500,
        900: 1000,
        930: 800,
        960: 600,
        990: 500,
        1020: 400,
        1050: 300,
        1080: 250,
        1110: 200,
        1140: 150,
        1170: 150,
        1200: 100,
        1230: 100,
        1260: 100,
        1290: 100,
        1320: 100,
        1350: 100,
        1380: 100,
        1410: 100,
    },
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

        # Compression factor: maps real time to simulated 1440-minute day
        ratio = 1440 / benchmark_length_minutes

        # Calculate simulated elapsed minutes
        simulated_minutes: int = int(self.get_run_time() * ratio) // 60

        # Terminate if we've completed the simulated day
        if simulated_minutes >= 1440:
            return None

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
            user_count = min(int(1.5 * lookup_value), MAX_USERS[role])

        # Apply base_load_intensity scaling
        user_count = int(user_count * base_load_intensity / 100)

        return (user_count, spawn_rate)
