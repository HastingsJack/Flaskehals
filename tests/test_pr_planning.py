"""Scenarios from features/githubsync/pull-request-task-assignment.feature (logic)."""

import pytest

from flaskehals.developer_scoring import DeveloperProfile
from flaskehals.github import PullRequest
from flaskehals.models import Task
from flaskehals.pr_planning import (
    PullRequestPlan,
    Skipped,
    label_changes,
    plan_pull_request,
)

SPEC = "## Objective\nExport CSV from Postgres"
TASK = Task(
    "u1", "CSV export", "d", SPEC, "approved", "Hans", "Hans", "2026-11-16", number=1
)
HANS = DeveloperProfile("Hans", history_texts=("Postgres CSV export",))
PETER = DeveloperProfile("Peter", history_texts=("Postgres reviews",))
MARIA = DeveloperProfile("Maria", history_texts=("React dashboard",))


def pr(
    branch: str = "feat/task-1",
    labels: tuple[str, ...] = (),
    state: str = "open",
    draft: bool = False,
) -> PullRequest:
    return PullRequest(
        1, 7, "Add export", "u", state, draft, "c", "u", None, None, 1, 1, 1,
        labels, head_ref=branch,
    )  # fmt: skip


def plan(
    request: PullRequest,
    tasks: list[Task] | None = None,
    profiles: list[DeveloperProfile] | None = None,
) -> PullRequestPlan | Skipped:
    return plan_pull_request(
        request,
        [TASK] if tasks is None else tasks,
        [HANS, PETER, MARIA] if profiles is None else profiles,
    )


def planned(
    request: PullRequest,
    tasks: list[Task] | None = None,
    profiles: list[DeveloperProfile] | None = None,
) -> PullRequestPlan:
    result = plan(request, tasks, profiles)
    assert isinstance(result, PullRequestPlan)
    return result


@pytest.mark.parametrize(
    "branch", ["feat/task-1", "fix/Task-1", "feature/TASK-1", "feat/task-1-login"]
)
def test_branch_styles_resolve_to_the_task(branch: str) -> None:
    assert planned(pr(branch)).task == TASK


@pytest.mark.parametrize("branch", ["main", "feat/login", "feat/mytask-1", ""])
def test_branch_without_task_is_skipped(branch: str) -> None:
    assert isinstance(plan(pr(branch)), Skipped)


def test_unknown_task_is_skipped() -> None:
    assert isinstance(plan(pr("feat/task-99")), Skipped)


@pytest.mark.parametrize("kwargs", [{"state": "closed"}, {"draft": True}])
def test_closed_and_draft_pull_requests_are_skipped(kwargs: dict[str, object]) -> None:
    assert isinstance(plan(pr(**kwargs)), Skipped)  # type: ignore[arg-type]


def test_task_without_assignee_is_skipped() -> None:
    unassigned = Task("u2", "T", "d", SPEC, "approved", None, None, "x", number=1)
    assert isinstance(plan(pr(), tasks=[unassigned]), Skipped)


def test_plan_names_the_developer_and_recommended_reviewer() -> None:
    result = planned(pr())
    assert result.developer == "Hans"
    assert result.reviewer == "Peter"  # relevant history, Hans excluded


def test_task_developer_is_never_the_reviewer() -> None:
    result = planned(pr(), profiles=[HANS, MARIA])
    assert result.reviewer != "Hans"


def test_uses_developer_assigned_now_not_originally() -> None:
    reassigned = Task(
        "u1", "CSV export", "d", SPEC, "approved", "Hans", "Peter", "x", number=1
    )
    result = planned(pr(), tasks=[reassigned])
    assert result.developer == "Peter"
    assert result.reviewer != "Peter"


def test_new_pull_request_gets_developer_and_reviewer_labels() -> None:
    assert label_changes((), "Hans", "Peter") == (("dev:Hans", "reviewer:Peter"), ())


def test_wrong_developer_label_is_replaced() -> None:
    add, remove = label_changes(("dev:Hans",), "Peter", None)
    assert add == ("dev:Peter",)
    assert remove == ("dev:Hans",)


def test_existing_correct_labels_are_not_added_again() -> None:
    labels = ("dev:Hans", "reviewer:Peter", "bug")
    assert label_changes(labels, "Hans", "Peter") == ((), ())


def test_reviewer_recommendation_replaces_existing_reviewer_label() -> None:
    labels = ("dev:Hans", "reviewer:Bob")
    assert label_changes(labels, "Hans", "Peter") == (
        ("reviewer:Peter",),
        ("reviewer:Bob",),
    )


def test_prefix_match_is_case_insensitive_so_one_label_remains() -> None:
    add, remove = label_changes(("DEV:hans",), "Hans", None)
    assert add == ("dev:Hans",)
    assert remove == ("DEV:hans",)


def test_without_a_reviewer_an_existing_reviewer_label_is_kept() -> None:
    assert label_changes(("reviewer:Bob",), "Hans", None) == (("dev:Hans",), ())


def test_no_suitable_reviewer_is_explained() -> None:
    result = planned(pr(), profiles=[HANS])
    assert result.reviewer is None
    assert result.assignment.notice


def test_plan_carries_scores_and_reasons_for_the_task() -> None:
    result = planned(pr())
    assert {s.name for s in result.assignment.scores} == {"Hans", "Peter", "Maria"}
    assert all(s.explanation for s in result.assignment.scores)


def test_ranking_is_deterministic() -> None:
    assert plan(pr()) == plan(pr())
