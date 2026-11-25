"""What the task pages need from the outside world.

The pages receive these functions instead of importing Neo4j or the language
model themselves, so they stay free of infrastructure and are easy to test.
"""

from collections.abc import Callable
from dataclasses import dataclass

from flaskehals.db import DataStoreError
from flaskehals.developer_scoring import (
    AssignmentResult,
    DeveloperProfile,
    recommend_developer,
)
from flaskehals.models import NewTask, Task
from flaskehals.reviewer_recommendations import ReviewerRecommendation


@dataclass(frozen=True)
class TaskServices:
    # (title, description, current specification, feedback) -> specification;
    # None when no OpenRouter key is configured.
    generate: Callable[[str, str, str | None, str | None], str] | None
    load_profiles: Callable[[], list[DeveloperProfile]]
    save_task: Callable[[NewTask], str]
    load_tasks: Callable[[], list[Task]]
    # (task id, new developer, assignee the caller saw)
    reassign_task: Callable[[str, str, str], None]
    load_recommendations: Callable[[], list[ReviewerRecommendation]]
    # (task id, pull request number, new reviewer, reviewer the caller saw);
    # None when GitHub is not configured, so the button is disabled.
    reassign_reviewer: Callable[[str, int, str, str], None] | None = None


def evaluate(
    services: TaskServices,
    title: str,
    specification: str,
    exclude: str | None = None,
) -> AssignmentResult:
    """Recommend a developer; a database failure becomes a notice, not a crash."""
    try:
        profiles = services.load_profiles()
    except DataStoreError as exc:
        return AssignmentResult(scores=(), recommended=None, notice=str(exc))
    return recommend_developer(profiles, title, specification, exclude)
