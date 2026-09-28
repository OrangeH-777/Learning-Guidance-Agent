"""One absolute task budget for queues, model calls, retry delays and persistence."""

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TypeVar

from agents.schemas.models import ModelErrorCode, ModelFailure

T = TypeVar("T")


class TaskDeadlineExceeded(Exception):
    def __init__(self):
        super().__init__("TASK_TIMEOUT")


class Deadline:
    def __init__(self, seconds_remaining: float, *, clock: Callable[[], float] = time.monotonic):
        if not math.isfinite(seconds_remaining):
            raise ValueError("Remaining time must be finite")
        self._clock = clock
        self._end = clock() + max(0.0, seconds_remaining)

    @classmethod
    def from_accepted_at(
        cls, accepted_at: datetime, *, total_seconds: float = 180, now: datetime | None = None
    ) -> "Deadline":
        now = now or datetime.now(UTC)
        if accepted_at.utcoffset() is None or now.utcoffset() is None:
            raise ValueError("Task timestamps must be timezone-aware")
        if not math.isfinite(total_seconds) or not 0 < total_seconds <= 180:
            raise ValueError("Total task budget must be within 180 seconds")
        if accepted_at > now:
            raise ValueError("Task acceptance cannot be in the future")
        return cls(total_seconds - (now - accepted_at).total_seconds())

    def remaining(self) -> float:
        remaining = self._end - self._clock()
        if remaining <= 0:
            raise TaskDeadlineExceeded()
        return remaining

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Guard any async step; even an operation suppressing cancellation returns no result."""
        remaining = self.remaining()
        try:
            async with asyncio.timeout(remaining):
                result = await operation()
        except TimeoutError:
            raise TaskDeadlineExceeded() from None
        self.remaining()
        return result


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """HTTP delta-seconds or date; malformed values must not enter task telemetry."""
    if value is None:
        return None
    value = value.strip()
    if value.isascii() and value.isdecimal():
        try:
            delay = float(value)
        except ValueError:
            return None
        return delay if math.isfinite(delay) else None
    try:
        date = parsedate_to_datetime(value)
        if date.utcoffset() is None:
            return None
        return max(0.0, (date - (now or datetime.now(UTC))).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


class ModelCallRunner:
    def __init__(
        self,
        deadline: Deadline,
        *,
        call_timeout_seconds: float = 60,
        transport_retry_limit: int = 1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        if not math.isfinite(call_timeout_seconds) or not 0 < call_timeout_seconds <= 60:
            raise ValueError("Model call timeout must be within 60 seconds")
        if transport_retry_limit not in (0, 1):
            raise ValueError("Transport retries must be zero or one")
        self.deadline = deadline
        self.call_timeout_seconds = call_timeout_seconds
        self.transport_retry_limit = transport_retry_limit
        self.sleep = sleep
        self.attempts = 0
        self.transport_retries = 0

    async def call(self, operation: Callable[[float], Awaitable[T]]) -> T:
        for attempt in range(self.transport_retry_limit + 1):
            timeout = min(self.call_timeout_seconds, self.deadline.remaining())
            self.attempts += 1
            if attempt:
                self.transport_retries += 1
            started = time.monotonic()
            failure: ModelFailure
            try:
                async with asyncio.timeout(timeout):
                    result = await operation(timeout)
                self.deadline.remaining()
                # A transport may accidentally suppress cancellation; never accept late output.
                if time.monotonic() - started >= timeout:
                    raise ModelFailure(ModelErrorCode.TIMEOUT)
                return result
            except TimeoutError:
                self.deadline.remaining()
                failure = ModelFailure(ModelErrorCode.TIMEOUT)
            except ModelFailure as error:
                self.deadline.remaining()
                failure = error
            if not failure.retryable or attempt == self.transport_retry_limit:
                raise failure from None
            delay = failure.retry_after_seconds or 0.0
            if delay >= self.deadline.remaining():
                # The provider's earliest retry is beyond the task deadline; never call early.
                raise TaskDeadlineExceeded() from None
            if delay:
                await self.deadline.run(lambda: self.sleep(delay))
        raise AssertionError("Unreachable retry state")
