import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from agents.schemas.models import ModelErrorCode, ModelFailure
from agents.workflows.runtime import (
    Deadline,
    ModelCallRunner,
    TaskDeadlineExceeded,
    parse_retry_after,
)
from backend.app.tasks.state import InvalidTransition, TaskProgress, TaskStatus


def test_state_machine_terminal_and_retry_bounds():
    progress = TaskProgress()
    for stage in (TaskStatus.PLANNING, TaskStatus.GENERATING, TaskStatus.VALIDATING):
        progress = progress.advance(stage)
    for _ in range(2):
        progress = progress.advance(TaskStatus.GENERATING).advance(TaskStatus.VALIDATING)
    with pytest.raises(InvalidTransition):
        progress.advance(TaskStatus.GENERATING)
    progress = progress.advance(TaskStatus.FORMATTING).advance(TaskStatus.COMPLETED)
    for target in TaskStatus:
        with pytest.raises(InvalidTransition):
            progress.advance(target)
    with pytest.raises(InvalidTransition):
        TaskProgress().advance(TaskStatus.COMPLETED)


@pytest.mark.parametrize("status", list(TaskStatus)[:-2])
def test_each_nonterminal_can_fail(status):
    assert TaskProgress(status).advance(TaskStatus.FAILED).status == TaskStatus.FAILED


def test_queue_time_counts_and_timestamps_must_be_aware():
    now = datetime.now(UTC)
    deadline = Deadline.from_accepted_at(now - timedelta(seconds=170), now=now)
    assert 9 < deadline.remaining() <= 10
    with pytest.raises(TaskDeadlineExceeded):
        Deadline.from_accepted_at(now - timedelta(seconds=181), now=now).remaining()
    with pytest.raises(ValueError):
        Deadline.from_accepted_at(datetime.now())


@pytest.mark.parametrize(
    "code",
    [
        ModelErrorCode.AUTH,
        ModelErrorCode.NOT_FOUND,
        ModelErrorCode.FORMAT,
        ModelErrorCode.UNSUPPORTED,
    ],
)
async def test_nontransient_errors_never_retry(code):
    runner = ModelCallRunner(Deadline(1))

    async def fail(timeout):
        raise ModelFailure(code)

    with pytest.raises(ModelFailure):
        await runner.call(fail)
    assert runner.attempts == 1


async def test_transient_retry_limit_and_separate_counters():
    runner = ModelCallRunner(Deadline(10))

    async def fail(timeout):
        assert timeout <= 10
        raise ModelFailure(ModelErrorCode.UNAVAILABLE)

    with pytest.raises(ModelFailure):
        await runner.call(fail)
    assert (runner.attempts, runner.transport_retries) == (2, 1)


async def test_no_request_after_exhausted_deadline_or_oversize_retry_after():
    runner = ModelCallRunner(Deadline(0))

    async def never(timeout):
        pytest.fail("A request must not start after the deadline")

    with pytest.raises(TaskDeadlineExceeded):
        await runner.call(never)
    runner = ModelCallRunner(Deadline(1))

    async def limited(timeout):
        raise ModelFailure(ModelErrorCode.RATE_LIMIT, retry_after_seconds=5)

    with pytest.raises(TaskDeadlineExceeded):
        await runner.call(limited)
    assert runner.attempts == 1


async def test_late_result_cannot_escape_cancellation_or_deadline():
    async def late():
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            return "late output"

    with pytest.raises(TaskDeadlineExceeded):
        await Deadline(0.01).run(late)


def test_retry_after_dates_and_invalid_values():
    now = datetime(2026, 9, 27, tzinfo=UTC)
    assert parse_retry_after("120") == 120
    assert parse_retry_after("Sun, 27 Sep 2026 00:00:05 GMT", now=now) == 5
    for value in (None, "-1", "nan", "1.5", "secret-invalid-value"):
        assert parse_retry_after(value, now=now) is None
