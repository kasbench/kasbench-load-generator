# Requirement 3: Enhancements to GET /health output

- This is the current code for GET /health
```python
    def get_health(self) -> HealthResponse:
        """Return a complete HealthResponse reflecting current state."""
        health = "healthy" if self._internal_error_count == 0 else "unhealthy"
        now = datetime.now(timezone.utc)
        current_timestamp = (
            now.strftime("%Y-%m-%dT%H:%M:%S.")
            + f"{now.microsecond // 1000:03d}Z"
        )

        return HealthResponse(
            Status=self._status,
            Role=self._role,
            Health=health,
            SuccessCount=self._success_count,
            FailureCount=self._failure_count,
            InternalErrorCount=self._internal_error_count,
            LastFiveErrorMessages=list(self._last_five_errors),
            CurrentTimeStamp=current_timestamp,
        )
```
- This enhancement will add two new fields:
    - StartTime: the time /start API was processed
    - EndTime: the time the Locust execution completed (or null/empty if Locust is currently running)

- Replace the 

```python
class StatusEnum(str, Enum):
    """Subprocess lifecycle states."""

    NOT_STARTED = "not-started"
    RUNNING = "running"
    COMPLETED = "completed"
```