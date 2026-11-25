"""Scenarios from features/tasks/task-search.feature."""

import pytest
from test_task_creation import Fakes, fakes, go_to, open_task_page  # noqa: F401

from flaskehals.task_search import MAX_QUERY_LENGTH, search_tasks, validate_query
from flaskehals.tasks import Task

pytestmark = pytest.mark.usefixtures("auth_env", "neo4j_env")


def make(task_id: str, title: str, assignee: str | None) -> Task:
    return Task(task_id, title, "d", "s", "approved", None, assignee, "2026-11-16")


TASKS = [
    make("1", "Add login page", "Hans"),
    make("2", "CSV export", "Peter"),
    make("3", "Fix hans bug", None),
]


def titles(tasks: list[Task]) -> list[str]:
    return [t.title for t in tasks]


def test_empty_or_blank_query_returns_all_tasks_in_order() -> None:
    assert search_tasks(TASKS, "") == TASKS
    assert search_tasks(TASKS, "   ") == TASKS


def test_matches_title_case_insensitively() -> None:
    assert titles(search_tasks(TASKS, "LOGIN")) == ["Add login page"]


def test_matches_assigned_developer() -> None:
    assert titles(search_tasks(TASKS, "peter")) == ["CSV export"]


def test_title_and_assignee_both_match() -> None:
    assert titles(search_tasks(TASKS, "Hans")) == ["Add login page", "Fix hans bug"]


def test_surrounding_whitespace_is_ignored() -> None:
    assert titles(search_tasks(TASKS, "  csv  ")) == ["CSV export"]


def test_no_match_returns_empty_list() -> None:
    assert search_tasks(TASKS, "zzz") == []


def test_validation_rejects_long_and_control_characters() -> None:
    assert validate_query("login") is None
    assert validate_query("x" * MAX_QUERY_LENGTH) is None
    assert validate_query("x" * (MAX_QUERY_LENGTH + 1))
    assert validate_query("bad\x00input")


def test_search_field_filters_overview(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = TASKS
    at = go_to(open_task_page(), "Tasks")
    assert len(at.expander) == 3
    at.text_input(key="task_search").input("csv").run()
    assert [e.label for e in at.expander] == ["CSV export - Peter"]
    at.text_input(key="task_search").input("").run()
    assert len(at.expander) == 3


def test_no_match_shows_message(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = TASKS
    at = go_to(open_task_page(), "Tasks")
    at.text_input(key="task_search").input("zzz").run()
    assert [i.value for i in at.info] == ["No task found."]
    assert not at.expander


def test_invalid_input_is_rejected(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = TASKS
    at = go_to(open_task_page(), "Tasks")
    at.text_input(key="task_search").input("bad\x00").run()
    assert at.error
    assert not at.expander


def test_search_field_finds_task_by_number(fakes: Fakes) -> None:  # noqa: F811
    fakes.tasks = [
        Task("1", "Add login page", "d", "s", "approved", None, "Hans", "x", number=7),
        Task("2", "CSV export", "d", "s", "approved", None, "Peter", "x", number=12),
    ]
    at = go_to(open_task_page(), "Tasks")
    assert [e.label for e in at.expander] == [
        "Task-7 - Add login page - Hans",
        "Task-12 - CSV export - Peter",
    ]
    at.text_input(key="task_search").input("task-7").run()
    assert [e.label for e in at.expander] == ["Task-7 - Add login page - Hans"]
