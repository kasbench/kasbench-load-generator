"""Portfolio Manager role Locust user class."""
import time

from locust import HttpUser, task, between


class PortfolioManagerUserOld(HttpUser):
    """Simulates portfolio manager HTTP traffic."""

    wait_time = between(60, 60)

    def  on_start(self) -> None:
        """Called once at the beginning of the test."""
        print("Starting Portfolio Manager tests")


    @task
    def default_task(self) -> None:
        """Placeholder task - sleeps for the wait duration."""
        print("Portfolio Manager Running")
        time.sleep(60)
