"""Scenarios from features/tasks/task-numbers.feature and the number-search ones."""

from unittest.mock import MagicMock

import pytest
from neo4j.exceptions import ConstraintError

from flaskehals.task_numbers import (
    format_task_number,
    parse_branch_task_number,
    parse_number_query,
    task_for_branch,
)
from flaskehals.task_search import search_tasks
from flaskehals.tasks import NewTask, Task, fetch_tasks, save_approved_task

NEW_TASK = NewTask("T", "D", "S", "Peter", "Hans")


def make(number: int | None, title: str = "t") -> Task:
    return Task(
        str(number), title, "d", "s", "approved", None, "Peter", "2026", number=number
    )


def driver_with_writes(*outcomes: object) -> tuple[MagicMock, MagicMock]:
    """A driver whose successive write transactions return or raise outcomes."""
    tx = MagicMock()
    tx.run.return_value.single.return_value = {"id": "x"}
    session = MagicMock()
    pending = list(outcomes)

    def execute_write(work: object) -> object:
        outcome = pending.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return work(tx)  # type: ignore[operator]

    session.execute_write.side_effect = execute_write
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    return driver, session


def test_format() -> None:
    assert format_task_number(12) == "Task-12"


@pytest.mark.parametrize(
    "branch",
    ["feat/task-12", "fix/Task-12", "feature/TASK-12", "feat/task-12-login", "task-12"],
)
def test_branch_names_resolve_to_number(branch: str) -> None:
    assert parse_branch_task_number(branch) == 12


@pytest.mark.parametrize(
    "branch",
    [
        "main",
        "feat/login",
        "feat/task-",
        "feat/task-0",
        "feat/mytask-1",
        "feat/task-012",
        "",
    ],
)
def test_branch_names_without_valid_number(branch: str) -> None:
    assert parse_branch_task_number(branch) is None


def test_task_for_branch_resolves_or_returns_none() -> None:
    tasks = [make(1), make(12)]
    assert task_for_branch(tasks, "feat/task-12") == tasks[1]
    assert task_for_branch(tasks, "feat/task-99") is None
    assert task_for_branch(tasks, "main") is None


@pytest.mark.parametrize("query", ["Task-7", "task-7", "7", "  TASK-7 "])
def test_number_queries(query: str) -> None:
    assert parse_number_query(query) == 7


@pytest.mark.parametrize("query", ["", "task-", "0", "task-0", "7 days", "csv"])
def test_not_number_queries(query: str) -> None:
    assert parse_number_query(query) is None


@pytest.mark.parametrize("query", ["Task-1", "task-1", "1"])
def test_number_search_is_exact(query: str) -> None:
    tasks = [make(1), make(12), make(2, "Task-1 cleanup")]
    assert search_tasks(tasks, query) == [tasks[0]]


def test_number_search_without_match_is_empty() -> None:
    assert search_tasks([make(1)], "Task-99") == []


def test_save_numbers_task_in_the_same_write_as_the_create() -> None:
    driver, session = driver_with_writes(None)
    tx = MagicMock()
    tx.run.return_value.single.return_value = {"id": "x"}
    session.execute_write.side_effect = lambda work: work(tx)
    assert save_approved_task(driver, NEW_TASK) == "x"
    query = tx.run.call_args.args[0]
    assert "max(existing.number)" in query and "number: number" in query


def test_save_prepares_constraints_and_backfill_first() -> None:
    driver, _ = driver_with_writes(None)
    save_approved_task(driver, NEW_TASK)
    queries = [call.args[0] for call in driver.execute_query.call_args_list]
    assert "task_number" in queries[1]
    assert "t.number IS NULL" in queries[2]


def test_save_retries_when_a_concurrent_save_took_the_number() -> None:
    driver, session = driver_with_writes(ConstraintError("dup"), None)
    assert save_approved_task(driver, NEW_TASK) == "x"
    assert session.execute_write.call_count == 2


def test_save_gives_up_after_repeated_collisions() -> None:
    driver, session = driver_with_writes(*[ConstraintError("dup")] * 3)
    with pytest.raises(ConstraintError):
        save_approved_task(driver, NEW_TASK)
    assert session.execute_write.call_count == 3


def test_fetch_numbers_unnumbered_tasks_first() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)
    fetch_tasks(driver)
    queries = [call.args[0] for call in driver.execute_query.call_args_list]
    assert any("t.number IS NULL" in q for q in queries)
    assert "t.number AS number" in queries[-1]


def test_fetch_survives_a_concurrent_backfill() -> None:
    driver = MagicMock()
    ok = ([], None, None)
    driver.execute_query.side_effect = [ok, ok, ConstraintError("dup"), ok]
    assert fetch_tasks(driver) == []
