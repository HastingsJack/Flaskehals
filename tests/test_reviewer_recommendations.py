"""Neo4j storage for reviewer recommendations (pull-request-task-assignment.feature)."""

from unittest.mock import MagicMock

import pytest

from flaskehals.assignment import AssignmentResult, DeveloperScore
from flaskehals.github import PullRequest
from flaskehals.pr_assignment import PullRequestPlan
from flaskehals.reviewer_recommendations import (
    RecommendationSaveError,
    ReviewerRecommendation,
    fetch_recommendations,
    mark_labelled,
    recommendation_key,
    save_recommendation,
)
from flaskehals.tasks import Task

TASK = Task("u1", "CSV export", "d", "s", "approved", "Hans", "Hans", "x", number=1)
PR = PullRequest(55, 7, "Add export", "https://x/7", "open", False, "c", "u", None, None, 1, 1, 1, ())  # fmt: skip
PLAN = PullRequestPlan(
    task=TASK,
    developer="Hans",
    reviewer="Peter",
    assignment=AssignmentResult(
        scores=(
            DeveloperScore("Peter", 71.234, (), ("Workload: 0",)),
            DeveloperScore("Hans", 50.0, (), ("Workload: 3",)),
        ),
        recommended="Peter",
    ),
    add_labels=("dev:Hans", "reviewer:Peter"),
    remove_labels=(),
)


def driver_returning(records: list[object]) -> MagicMock:
    driver = MagicMock()
    driver.execute_query.return_value = (records, None, None)
    return driver


def test_save_stores_recommendation_pr_link_and_reasoning() -> None:
    driver = driver_returning([{"key": "k"}])
    save_recommendation(driver, PR, PLAN, "db")
    query = driver.execute_query.call_args.args[0]
    kwargs = driver.execute_query.call_args.kwargs
    assert "HAS_PULL_REQUEST" in query and "HAS_REVIEWER_RECOMMENDATION" in query
    assert "labelled = false" in query
    assert kwargs["key"] == "u1:55" == recommendation_key("u1", 55)
    assert kwargs["reviewer"] == "Peter" and kwargs["developer"] == "Hans"
    assert kwargs["github_id"] == 55 and kwargs["number"] == 7
    assert kwargs["database_"] == "db"
    assert '"Peter"' in kwargs["candidates"] and "Workload: 3" in kwargs["candidates"]


def test_save_never_overwrites_an_existing_recommendation() -> None:
    driver = driver_returning([{"key": "k"}])
    save_recommendation(driver, PR, PLAN)
    query = driver.execute_query.call_args.args[0]
    assert "MERGE (r:ReviewerRecommendation {key: $key})" in query
    assert "ON CREATE SET r.task_id" in query


def test_save_creates_the_uniqueness_constraint_first() -> None:
    driver = driver_returning([{"key": "k"}])
    save_recommendation(driver, PR, PLAN)
    assert (
        "reviewer_recommendation_key" in driver.execute_query.call_args_list[0].args[0]
    )


def test_save_without_reviewer_stores_the_notice() -> None:
    plan = PullRequestPlan(
        TASK, "Hans", None, AssignmentResult((), None, "none found"), (), ()
    )
    driver = driver_returning([{"key": "k"}])
    save_recommendation(driver, PR, plan)
    kwargs = driver.execute_query.call_args.kwargs
    assert kwargs["reviewer"] is None and kwargs["notice"] == "none found"


def test_save_raises_when_task_is_gone() -> None:
    with pytest.raises(RecommendationSaveError):
        save_recommendation(driver_returning([]), PR, PLAN)


def test_save_propagates_database_errors() -> None:
    driver = MagicMock()
    driver.execute_query.side_effect = RuntimeError("down")
    with pytest.raises(RuntimeError):
        save_recommendation(driver, PR, PLAN)


def test_mark_labelled_targets_the_recommendation() -> None:
    driver = driver_returning([])
    mark_labelled(driver, "u1", 55, "db")
    assert driver.execute_query.call_args.kwargs == {"key": "u1:55", "database_": "db"}
    assert "labelled = true" in driver.execute_query.call_args.args[0]


def test_fetch_maps_records_and_decodes_candidates() -> None:
    save_driver = driver_returning([{"key": "k"}])
    save_recommendation(save_driver, PR, PLAN)
    stored = save_driver.execute_query.call_args.kwargs["candidates"]
    driver = driver_returning(
        [
            {
                "task_id": "u1", "pr_number": 7, "pr_url": None, "developer": "Hans",
                "reviewer": "Peter", "notice": None, "candidates": stored,
                "created_at": "2026-11-25T10:00:00Z", "labelled": None,
            }
        ]
    )  # fmt: skip
    assert fetch_recommendations(driver) == [
        ReviewerRecommendation(
            "u1", 7, "", "Hans", "Peter", None,
            (DeveloperScore("Peter", 71.2, explanation=("Workload: 0",)), DeveloperScore("Hans", 50.0, explanation=("Workload: 3",))),
            "2026-11-25T10:00:00Z", False,
        )
    ]  # fmt: skip


@pytest.mark.parametrize("bad", [None, "", "not json", '[{"name": "x"}]', '"str"'])
def test_unreadable_candidates_yield_none_not_an_error(bad: str | None) -> None:
    row = {
        "task_id": "u1", "pr_number": 7, "pr_url": "u", "developer": "Hans",
        "reviewer": None, "notice": "n", "candidates": bad, "created_at": "x",
        "labelled": True,
    }  # fmt: skip
    (rec,) = fetch_recommendations(driver_returning([row]))
    assert rec.candidates == () and rec.labelled is True
