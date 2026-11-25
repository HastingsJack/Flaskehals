"""Reviewer recommendation on the task page (pull-request-task-assignment.feature)."""

import pytest
from neo4j.exceptions import ServiceUnavailable
from test_task_creation import Fakes, fakes, go_to, open_task_page  # noqa: F401

from flaskehals.developer_scoring import DeveloperScore
from flaskehals.models import Task
from flaskehals.reviewer_recommendations import ReviewerRecommendation

pytestmark = pytest.mark.usefixtures("auth_env", "neo4j_env")

TASK = Task(
    "u1", "CSV export", "d", "s", "approved", None, "Hans", "2026-11-16", number=1
)
SCORES = (
    DeveloperScore("Peter", 71.2, explanation=("Workload: 0 item(s)",)),
    DeveloperScore("Maria", 40.0, explanation=("Workload: 4 item(s)",)),
)


def rec(**overrides: object) -> ReviewerRecommendation:
    values: dict[str, object] = {
        "task_id": "u1", "pr_number": 7, "pr_url": "https://x/pull/7",
        "developer": "Hans", "reviewer": "Peter", "notice": None,
        "candidates": SCORES, "created_at": "2026-11-25T10:00:00Z", "labelled": True,
    }  # fmt: skip
    return ReviewerRecommendation(**{**values, **overrides})  # type: ignore[arg-type]


def texts(at) -> str:  # type: ignore[no-untyped-def]
    return "\n".join(
        [m.value for m in at.markdown]
        + [i.value for i in at.info]
        + [w.value for w in at.warning]
        + [c.value for c in at.caption]
    )


def test_shows_reviewer_pull_request_and_reasoning(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = [TASK]
    fakes.recommendations = [rec()]
    at = go_to(open_task_page(), "Tasks")
    shown = texts(at)
    assert "Recommended reviewer: **Peter**" in shown
    assert "[#7](https://x/pull/7)" in shown
    assert "recommended 2026-11-25" in shown
    # only the AI response is shown: no score breakdown or dropdown
    assert "**Maria** - 40.0/100" not in shown
    assert "Workload: 4 item(s)" not in shown
    assert not any("was scored" in e.label for e in at.expander)


def test_shows_the_stored_ai_reasoning(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = [TASK]
    fakes.recommendations = [rec(reasoning="Peter reviewed similar Postgres work.")]
    shown = texts(go_to(open_task_page(), "Tasks"))
    assert "**Why (AI):** Peter reviewed similar Postgres work." in shown


def test_unlabelled_recommendation_is_flagged(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = [TASK]
    fakes.recommendations = [rec(labelled=False)]
    assert "labels have not been added" in texts(go_to(open_task_page(), "Tasks"))


def test_no_suitable_reviewer_shows_the_notice(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = [TASK]
    fakes.recommendations = [
        rec(reviewer=None, candidates=(), notice="No reviewer found")
    ]
    shown = texts(go_to(open_task_page(), "Tasks"))
    assert "No reviewer found" in shown and "Recommended reviewer" not in shown


def test_each_pull_request_shows_its_own_recommendation(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = [TASK]
    fakes.recommendations = [
        rec(),
        rec(pr_number=8, pr_url="https://x/pull/8", reviewer="Maria"),
    ]
    shown = texts(go_to(open_task_page(), "Tasks"))
    assert "#7" in shown and "#8" in shown
    assert "Recommended reviewer: **Maria**" in shown


def test_other_tasks_recommendations_are_not_shown(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = [TASK]
    fakes.recommendations = [rec(task_id="other")]
    assert "Reviewer recommendation" not in texts(go_to(open_task_page(), "Tasks"))


def test_tasks_still_shown_when_recommendations_cannot_be_loaded(
    fakes: Fakes,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fakes.tasks = [TASK]

    def boom(*args: object) -> list[ReviewerRecommendation]:
        raise ServiceUnavailable("down")

    monkeypatch.setattr(
        "flaskehals.reviewer_recommendations.fetch_recommendations", boom
    )
    at = go_to(open_task_page(), "Tasks")
    assert [e.label for e in at.expander] == ["Task-1 - CSV export - Hans"]
    assert not at.error
