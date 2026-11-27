"""Scenarios from features/tasks/task-reassignment-github-labels.feature."""

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fake_github import FakeGitHub, pr_json
from neo4j.exceptions import ServiceUnavailable
from test_task_creation import Fakes, button, fakes, go_to, open_task_page  # noqa: F401
from test_task_reviews import TASK, rec

from flaskehals import task_reassignment as module
from flaskehals.db import DataStoreError
from flaskehals.tasks import (
    fetch_open_pull_request_numbers,
    reassign_task,
)

pytestmark = pytest.mark.usefixtures("auth_env", "neo4j_env")


def driver_with(rows: list[dict[str, Any]]) -> MagicMock:
    driver = MagicMock()
    driver.execute_query.return_value = (rows, None, None)
    return driver


def test_open_pull_requests_are_read_from_the_task() -> None:
    driver = driver_with([{"number": 7}, {"number": 9}])
    assert fetch_open_pull_request_numbers(driver, "u1") == [7, 9]
    query = driver.execute_query.call_args.args[0]
    assert "HAS_PULL_REQUEST" in query and "p.state = 'open'" in query


def reassign_tx(prs: list[int]) -> MagicMock:
    tx = MagicMock()
    tx.run.return_value.single.return_value = {"current": "Hans", "target": "Maria"}
    session = MagicMock()
    session.execute_write.side_effect = lambda work: work(tx)
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    reassign_task(driver, "u1", "Maria", "Hans", prs)
    return tx


def test_pull_request_author_moves_in_the_same_transaction() -> None:
    tx = reassign_tx([7])
    assert tx.run.call_count == 3
    query = tx.run.call_args_list[2].args[0]
    kwargs = tx.run.call_args_list[2].kwargs
    assert "AUTHORED" in query and "r.developer = $new_developer" in query
    assert kwargs["numbers"] == [7] and kwargs["new_developer"] == "Maria"


def test_without_pull_requests_only_the_task_moves() -> None:
    assert reassign_tx([]).run.call_count == 2


class Neo4j:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, numbers: list[int]) -> None:
        self.validate_error: Exception | None = None
        self.save_error: Exception | None = None
        self.numbers = numbers
        self.saved: list[tuple[object, ...]] = []
        monkeypatch.setattr(module, "validate_reassignment", self.validate)
        monkeypatch.setattr(module, "fetch_open_pull_request_numbers", self.fetch)
        monkeypatch.setattr(module, "reassign_task", self.save)

    def validate(self, driver: object, *args: object) -> None:
        if self.validate_error:
            raise self.validate_error

    def fetch(self, driver: object, task_id: str) -> list[int]:
        return self.numbers

    def save(self, driver: object, *args: object) -> None:
        if self.save_error:
            raise self.save_error
        self.saved.append(args)


@pytest.fixture
def neo4j(monkeypatch: pytest.MonkeyPatch) -> Neo4j:
    return Neo4j(monkeypatch, [7])


def run(gh: FakeGitHub) -> None:
    with gh.client() as client:
        module.reassign_task_and_labels(None, client, "u1", "Maria", "Hans")  # type: ignore[arg-type]


def labelled(number: int = 7, **overrides: object) -> dict[str, Any]:
    return pr_json(number, ("dev:Hans", "reviewer:Peter", "bug"), **overrides)


def test_changes_only_the_dev_label_then_saves(neo4j: Neo4j) -> None:
    gh = FakeGitHub([labelled()])
    run(gh)
    assert gh.label_edits == [
        ("add", 7, ["dev:Maria"]),
        ("remove", 7, "dev:Hans"),
    ]
    assert neo4j.saved == [("u1", "Maria", "Hans", [7])]


def test_every_open_pull_request_is_updated(monkeypatch: pytest.MonkeyPatch) -> None:
    neo4j = Neo4j(monkeypatch, [7, 8])
    gh = FakeGitHub([labelled(7), labelled(8)])
    run(gh)
    assert [edit[1] for edit in gh.label_edits] == [7, 7, 8, 8]
    assert neo4j.saved == [("u1", "Maria", "Hans", [7, 8])]


def test_a_pull_request_closed_since_the_sync_is_left_alone(neo4j: Neo4j) -> None:
    gh = FakeGitHub([labelled(state="closed")])
    run(gh)
    assert gh.label_edits == []
    assert neo4j.saved == [("u1", "Maria", "Hans", [])]


def test_no_pull_requests_means_github_is_not_contacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    neo4j = Neo4j(monkeypatch, [])
    gh = FakeGitHub([])
    run(gh)
    assert gh.requests == []
    assert neo4j.saved == [("u1", "Maria", "Hans", [])]


def test_rejected_change_never_touches_github(neo4j: Neo4j) -> None:
    neo4j.validate_error = DataStoreError("The task is now assigned to Peter.")
    gh = FakeGitHub([labelled()])
    with pytest.raises(DataStoreError, match="now assigned"):
        run(gh)
    assert gh.requests == [] and neo4j.saved == []


def test_database_down_before_the_change_never_touches_github(neo4j: Neo4j) -> None:
    neo4j.validate_error = ServiceUnavailable("down")
    gh = FakeGitHub([labelled()])
    with pytest.raises(DataStoreError, match="Neo4j"):
        run(gh)
    assert gh.requests == []


def test_github_failure_leaves_the_task_unchanged(neo4j: Neo4j) -> None:
    gh = FakeGitHub([labelled()])
    gh.override = lambda request: httpx.Response(500, json={"message": "boom"})
    with pytest.raises(DataStoreError, match="GitHub failed"):
        run(gh)
    assert neo4j.saved == []


def test_a_failure_on_the_second_pull_request_restores_the_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    neo4j = Neo4j(monkeypatch, [7, 8])
    gh = FakeGitHub([labelled(7)])  # #8 does not exist: GitHub answers 404
    with pytest.raises(DataStoreError, match="GitHub failed"):
        run(gh)
    assert gh.label_edits == [
        ("add", 7, ["dev:Maria"]),
        ("remove", 7, "dev:Hans"),
        ("remove", 7, "dev:Maria"),  # restored
        ("add", 7, ["dev:Hans"]),
    ]
    assert neo4j.saved == []


@pytest.mark.parametrize(
    "error", [ServiceUnavailable("down"), DataStoreError("now Peter")]
)
def test_failed_save_restores_the_labels(neo4j: Neo4j, error: Exception) -> None:
    neo4j.save_error = error
    gh = FakeGitHub([labelled()])
    with pytest.raises(DataStoreError):
        run(gh)
    assert gh.label_edits == [
        ("add", 7, ["dev:Maria"]),
        ("remove", 7, "dev:Hans"),
        ("remove", 7, "dev:Maria"),
        ("add", 7, ["dev:Hans"]),
    ]


def test_the_new_developer_may_already_be_the_reviewer(neo4j: Neo4j) -> None:
    gh = FakeGitHub([labelled()])
    with gh.client() as client:
        module.reassign_task_and_labels(None, client, "u1", "Peter", "Hans")  # type: ignore[arg-type]
    assert gh.label_edits == [("add", 7, ["dev:Peter"]), ("remove", 7, "dev:Hans")]
    assert neo4j.saved == [("u1", "Peter", "Hans", [7])]


def open_reassignment(fakes: Fakes, reviews: bool) -> Any:  # noqa: F811
    fakes.tasks = [TASK]
    fakes.recommendations = [rec()] if reviews else []
    at = go_to(open_task_page(), "Tasks")
    at = button(at, "Re-assign developer").click().run()
    return button(at, "Confirm re-assignment").click().run()


def test_page_says_labels_were_not_updated_without_github(
    fakes: Fakes,  # noqa: F811
) -> None:
    at = open_reassignment(fakes, reviews=True)
    assert any("labels were not updated" in s.value for s in at.success)


def test_page_has_no_extra_notice_without_pull_requests(
    fakes: Fakes,  # noqa: F811
) -> None:
    at = open_reassignment(fakes, reviews=False)
    assert at.success and not any("labels were not" in s.value for s in at.success)


def test_page_has_no_notice_when_github_updates_the_labels(
    fakes: Fakes,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/repo")
    monkeypatch.setattr(
        "flaskehals.task_reassignment.reassign_task_and_labels",
        lambda *args: None,
    )
    at = open_reassignment(fakes, reviews=True)
    assert at.success and not any("labels were not" in s.value for s in at.success)
