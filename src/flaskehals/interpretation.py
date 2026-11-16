"""Interpretation of custom PR labels and simulated review comments.

Pure functions with no I/O, so the rules are easy to test and explain.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

DEVELOPER_PREFIX = "dev:"
REVIEWER_PREFIX = "reviewer:"
PRIORITY_PREFIX = "priority:"
PRIORITIES = frozenset({"low", "medium", "high", "critical"})


class ReviewOutcome(StrEnum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"


@dataclass(frozen=True)
class LabelInfo:
    developer: str | None = None
    reviewer: str | None = None
    priority: str | None = None


def _label_value(label: str, prefix: str) -> str | None:
    """Return the trimmed value after a case-insensitive prefix, or None."""
    if not label.lower().startswith(prefix):
        return None
    return label[len(prefix) :].strip() or None


def interpret_labels(labels: Iterable[str]) -> LabelInfo:
    """Extract developer, reviewer and priority from custom labels.

    Missing or unrecognised labels leave the field as None rather than
    failing. If a prefix appears more than once, the first label wins.
    """
    developer = reviewer = priority = None
    for label in labels:
        if developer is None:
            developer = _label_value(label, DEVELOPER_PREFIX)
        if reviewer is None:
            reviewer = _label_value(label, REVIEWER_PREFIX)
        if priority is None:
            value = _label_value(label, PRIORITY_PREFIX)
            if value is not None and value.lower() in PRIORITIES:
                priority = value.lower()
    return LabelInfo(developer=developer, reviewer=reviewer, priority=priority)


def interpret_comment(body: str, reviewer: str | None) -> ReviewOutcome | None:
    """Return the simulated review outcome of a comment, or None.

    All comments on a PR are attributed to its assigned reviewer, so a
    review outcome is only recorded when the PR has one. Prefixes are
    case-sensitive and must start the comment (leading whitespace allowed).
    """
    if reviewer is None:
        return None
    text = body.lstrip()
    for outcome in ReviewOutcome:
        if text.startswith(f"[{outcome.value}]"):
            return outcome
    return None
