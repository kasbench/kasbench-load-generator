"""Pydantic request/response models for the KASBench Load Generator API."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RoleEnum(str, Enum):
    """Valid roles for load generation profiles."""

    PORTFOLIO_MANAGER = "portfolio-manager"
    TRADER = "trader"
    BACK_OFFICE = "back-office"
    INVESTOR = "investor"
    IT_OPERATIONS = "it-operations"


class StatusEnum(str, Enum):
    """Subprocess lifecycle states."""

    NOT_STARTED = "not-started"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ABORTED = "aborted"


class StartRequest(BaseModel):
    """Request body for POST /start endpoint."""

    Role: RoleEnum
    BenchmarkLengthMinutes: int = Field(ge=1, le=1440)
    BaseLoadIntensity: int = Field(ge=1, le=1000)
    SpawnRate: int = Field(ge=1, le=100)
    BaseDelayPercentage: int = Field(ge=0, le=1000)
    KasbenchUrl: str

    @field_validator("KasbenchUrl")
    @classmethod
    def validate_kasbench_url(cls, v: str) -> str:
        """Validate that KasbenchUrl is a valid HTTP or HTTPS URL."""
        if not isinstance(v, str):
            raise ValueError("KasbenchUrl must be a string")
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("KasbenchUrl must be a valid HTTP or HTTPS URL")
        # Check there's something after the scheme
        scheme_end = v.index("://") + 3
        remainder = v[scheme_end:]
        if not remainder:
            raise ValueError("KasbenchUrl must contain a host after the scheme")
        return v


class StartResponse(BaseModel):
    """Response body for POST /start endpoint."""

    StartTimeStamp: str


class AbortResponse(BaseModel):
    """Response body for POST /abort endpoint."""

    StopTimeStamp: str


class HealthResponse(BaseModel):
    """Response body for GET /health endpoint."""

    Status: StatusEnum
    Role: str
    Health: Literal["healthy", "unhealthy"]
    SuccessCount: int
    FailureCount: int
    InternalErrorCount: int
    LastFiveErrorMessages: list[str]
    CurrentTimeStamp: str
    StartTime: str | None
    EndTime: str | None


class ErrorResponse(BaseModel):
    """Error response body for 4xx/5xx responses."""

    error: str
