"""Task data shared by the database, the business logic and the UI.

Plain dataclasses with no behaviour, so the pure logic modules (search, task
numbers, reviewer planning) do not have to import the Neo4j module.
"""

from dataclasses import dataclass

from flaskehals.pr_status import PullRequestStatus


@dataclass(frozen=True)
class PreviousAssignment:
    developer: str
    assigned_at: str
    unassigned_at: str


@dataclass(frozen=True)
class NewTask:
    title: str
    description: str  # the project manager's original description
    specification: str  # the approved (possibly edited) specification
    assigned_developer: str  # final assignee
    recommended_developer: str | None  # original recommendation, if any


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    description: str
    specification: str
    status: str
    recommended_developer: str | None
    assigned_developer: str | None
    created_at: str
    previous_assignments: tuple[PreviousAssignment, ...] = ()
    number: int | None = None  # global, shown as "Task-N"
    pull_request_statuses: tuple[PullRequestStatus, ...] = ()
