"""Trader role Locust user class."""

from locust import HttpUser, task, between


class TraderUser(HttpUser):
    """Simulates trader HTTP traffic."""

    wait_time = between(60, 60)

    @task
    def default_task(self) -> None:
        """Placeholder task - sleeps for the wait duration."""
        pass
