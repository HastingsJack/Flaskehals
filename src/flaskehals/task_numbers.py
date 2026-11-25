"""Task numbers (features/tasks/task-numbers.feature).

A task number is a global positive integer shown as ``Task-N``. Branch names
use the lowercase form, e.g. ``feat/task-1``. Pure functions, no I/O.
"""

import re
from collections.abc import Iterable

from flaskehals.models import Task

# "task-<n>" as a whole word: not part of a longer word (mytask-1) and not
# followed by more digits. Zero and leading zeros are not valid numbers.
_BRANCH_NUMBER = re.compile(r"(?<![a-z0-9])task-([1-9][0-9]*)(?![0-9])", re.IGNORECASE)
_SEARCH_NUMBER = re.compile(r"(?:task-)?([1-9][0-9]*)", re.IGNORECASE)


def format_task_number(number: int) -> str:
    return f"Task-{number}"


def parse_branch_task_number(branch: str) -> int | None:
    """The task number named in a branch name, or None."""
    match = _BRANCH_NUMBER.search(branch)
    return int(match.group(1)) if match else None


def parse_number_query(query: str) -> int | None:
    """The number if the whole query is ``Task-N`` or ``N`` (any case)."""
    match = _SEARCH_NUMBER.fullmatch(query.strip())
    return int(match.group(1)) if match else None


def task_for_branch(tasks: Iterable[Task], branch: str) -> Task | None:
    """The task a branch name refers to, or None if none does."""
    number = parse_branch_task_number(branch)
    if number is None:
        return None
    return next((task for task in tasks if task.number == number), None)
