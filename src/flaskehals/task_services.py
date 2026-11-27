"""What the task pages need from the outside world.

The pages receive these functions instead of importing Neo4j or the language
model themselves, so they stay free of infrastructure and are easy to test.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from flaskehals.db import DataStoreError
from flaskehals.developer_scoring import (
    AssignmentResult,
    DeveloperProfile,
    recommend_developer,
)
from flaskehals.llm_recommendation import Complete, decide_with_llm
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
    # Chat messages -> model reply; None when no OpenRouter key is configured,
    # in which case recommendations fall back to the rule-based ranking.
    complete: Complete | None = None
    # True when re-assigning a task also updates the dev: label of its open pull
    # requests on GitHub; False when GitHub is not configured.
    github_labels: bool = False


def evaluate(
    services: TaskServices,
    title: str,
    specification: str,
    exclude: str | None = None,
    role: str = "developer",
    reviewers: Sequence[str] = (),
) -> AssignmentResult:
    """Recommend a developer (or, with ``role="reviewer"``, a reviewer).

    The rule-based ranking is computed first as evidence and as the fallback;
    the language model then makes the decision. A database failure becomes a
    notice, not a crash. ``reviewers`` are the current reviewers of the task's
    open pull requests; the model is nudged to prefer someone else as developer.
    """
    try:
        profiles = services.load_profiles()
    except DataStoreError as exc:
        return AssignmentResult(scores=(), recommended=None, notice=str(exc))
    baseline = recommend_developer(profiles, title, specification, exclude)
    return decide_with_llm(
        services.complete,
        role,
        profiles,
        title,
        specification,
        baseline,
        exclude,
        reviewers,
    )
