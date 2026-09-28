"""Pure transition rules shared by future database conditional updates and runners."""

from dataclasses import dataclass, replace
from enum import StrEnum


class TaskStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    GENERATING = "generating"
    VALIDATING = "validating"
    FORMATTING = "formatting"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATUSES = frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED})
_NEXT = {
    TaskStatus.QUEUED: TaskStatus.PLANNING,
    TaskStatus.PLANNING: TaskStatus.GENERATING,
    TaskStatus.GENERATING: TaskStatus.VALIDATING,
    TaskStatus.VALIDATING: TaskStatus.FORMATTING,
    TaskStatus.FORMATTING: TaskStatus.COMPLETED,
}


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True)
class TaskProgress:
    status: TaskStatus = TaskStatus.QUEUED
    content_regenerations: int = 0

    def advance(self, target: TaskStatus, *, regeneration_limit: int = 2) -> "TaskProgress":
        if not 0 <= regeneration_limit <= 2:
            raise ValueError("Content regeneration limit must be between zero and two")
        if self.status in TERMINAL_STATUSES:
            raise InvalidTransition("Terminal tasks cannot change state")
        if target == TaskStatus.FAILED:
            return replace(self, status=target)
        if self.status == TaskStatus.VALIDATING and target == TaskStatus.GENERATING:
            if self.content_regenerations >= regeneration_limit:
                raise InvalidTransition("Content regeneration limit exhausted")
            return TaskProgress(target, self.content_regenerations + 1)
        if _NEXT.get(self.status) != target:
            raise InvalidTransition("Task stage cannot be skipped or repeated")
        return replace(self, status=target)
