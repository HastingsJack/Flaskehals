"""Decide the reviewer for a pull request opened for a task, and the label changes.

features/githubsync/pull-request-task-assignment.feature

Pure functions with no I/O and no LLM. Given a pull request, the stored tasks
and the developer profiles, decide what to do; callers do the Neo4j and GitHub
writes. The reviewer is ranked with the same deterministic scoring used for
task assignment (workload, relevant history including previously reviewed PRs,
experience level), and the task's own developer is never recommended.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from flaskehals.developer_scoring import (
    AssignmentResult,
    DeveloperProfile,
    recommend_developer,
)
from flaskehals.github import PullRequest
from flaskehals.interpretation import DEVELOPER_PREFIX, REVIEWER_PREFIX
from flaskehals.models import Task
from flaskehals.task_numbers import task_for_branch


@dataclass(frozen=True)
class Skipped:
    """The pull request needs no action. ``reason`` is safe to show."""

    reason: str


@dataclass(frozen=True)
class PullRequestPlan:
    task: Task
    developer: str
    reviewer: str | None  # None when no suitable reviewer was found
    assignment: AssignmentResult  # scores and reasoning for every candidate


def _label_changes(
    current: Iterable[str], prefix: str, wanted: str
) -> tuple[list[str], list[str]]:
    """Labels to add and remove so ``wanted`` is the only label with ``prefix``."""
    existing = [label for label in current if label.lower().startswith(prefix)]
    add = [] if wanted in existing else [wanted]
    remove = [label for label in existing if label != wanted]
    return add, remove


def label_changes(
    current: Iterable[str], developer: str, reviewer: str | None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(labels to add, labels to remove) so the PR carries exactly the wanted
    ``dev:`` label and, if there is a reviewer, the ``reviewer:`` label.

    Without a reviewer an existing ``reviewer:`` label is left alone.
    """
    current = tuple(current)
    add, remove = _label_changes(
        current, DEVELOPER_PREFIX, DEVELOPER_PREFIX + developer
    )
    if reviewer is not None:
        add_reviewer, remove_reviewer = _label_changes(
            current, REVIEWER_PREFIX, REVIEWER_PREFIX + reviewer
        )
        add += add_reviewer
        remove += remove_reviewer
    return tuple(add), tuple(remove)


def reviewer_label_changes(
    current: Iterable[str], reviewer: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(labels to add, labels to remove) so ``reviewer`` is the only ``reviewer:``
    label. Every other label, including ``dev:``, is left alone."""
    add, remove = _label_changes(current, REVIEWER_PREFIX, REVIEWER_PREFIX + reviewer)
    return tuple(add), tuple(remove)


def plan_pull_request(
    pr: PullRequest,
    tasks: Sequence[Task],
    profiles: list[DeveloperProfile],
) -> PullRequestPlan | Skipped:
    """Decide the labels and recommended reviewer for one pull request."""
    if pr.state != "open":
        return Skipped("The pull request is not open.")
    if pr.draft:
        return Skipped("The pull request is a draft.")
    task = task_for_branch(tasks, pr.head_ref)
    if task is None:
        return Skipped("The branch does not refer to an existing task.")
    developer = task.assigned_developer
    if not developer:
        return Skipped("The task has no assigned developer.")

    assignment = recommend_developer(
        profiles, task.title, task.specification, exclude=developer
    )
    return PullRequestPlan(
        task=task,
        developer=developer,
        reviewer=assignment.recommended,
        assignment=assignment,
    )
