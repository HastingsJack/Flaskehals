"""GitHub status of a task, derived from its synced pull requests.

Pure logic: no Streamlit, no database, no GitHub calls.
"""

import re
from collections.abc import Iterable, Mapping
from enum import Enum


class PullRequestStatus(Enum):
    NO_PR = "No PR"
    DRAFT = "Draft"
    OPEN = "Open"
    MERGED = "Merged"
    CLOSED = "Closed"


# Which status wins when a task has several pull requests: unfinished work
# first, then finished work.
_PRIORITY = (
    PullRequestStatus.OPEN,
    PullRequestStatus.DRAFT,
    PullRequestStatus.MERGED,
    PullRequestStatus.CLOSED,
)

# GitHub's colours, as Streamlit colour names (GitHub's purple is "violet").
# Shown as filled badges so they stay readable in light and dark themes.
STATUS_COLOURS = {
    PullRequestStatus.OPEN: "green",
    PullRequestStatus.DRAFT: "gray",
    PullRequestStatus.MERGED: "violet",
    PullRequestStatus.CLOSED: "red",
    PullRequestStatus.NO_PR: "gray",
}

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_\[\]()#~<>$:|])")


def classify(
    state: str | None, draft: bool | None, merged: bool | None
) -> PullRequestStatus:
    """Status of one pull request. A missing state counts as open."""
    if merged:
        return PullRequestStatus.MERGED
    if state == "closed":
        return PullRequestStatus.CLOSED
    if draft:
        return PullRequestStatus.DRAFT
    return PullRequestStatus.OPEN


def classify_rows(
    rows: Iterable[Mapping[str, object]],
) -> tuple[PullRequestStatus, ...]:
    """Classify rows with ``state``, ``draft`` and ``merged`` keys."""
    statuses = []
    for row in rows:
        state = row.get("state")
        statuses.append(
            classify(
                state if isinstance(state, str) else None,
                bool(row.get("draft")),
                bool(row.get("merged")),
            )
        )
    return tuple(statuses)


def summarise(
    statuses: Iterable[PullRequestStatus],
) -> tuple[PullRequestStatus, int]:
    """The status to show for a task, and how many pull requests it has."""
    found = tuple(statuses)
    for status in _PRIORITY:
        if status in found:
            return status, len(found)
    return PullRequestStatus.NO_PR, 0


def escape_markdown(text: str) -> str:
    """Stop user-supplied text being read as markup in a Streamlit label."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def _badge(text: str, colour: str) -> str:
    return f":{colour}-badge[{escape_markdown(f'[{text}]')}]"


def format_status(status: PullRequestStatus, count: int) -> str:
    """The coloured ``[Status]`` text shown at the end of a task title."""
    text = status.value if count < 2 else f"{status.value} ({count})"
    return _badge(text, STATUS_COLOURS[status])


def format_task_status(task_status: str) -> str:
    """Badge for a task with no pull request: the task's own stored status."""
    return _badge(task_status.strip().capitalize() or "Unknown", "gray")
