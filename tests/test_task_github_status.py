"""Feature: features/tasks/task-github-status-in-title.feature"""

from unittest.mock import MagicMock

import pytest

from flaskehals.models import Task
from flaskehals.pr_status import (
    PullRequestStatus as S,
)
from flaskehals.pr_status import (
    classify,
    classify_rows,
    format_status,
    summarise,
)
from flaskehals.task_overview_page import expander_title
from flaskehals.tasks import fetch_tasks


def task(
    statuses: tuple[S, ...] = (), dev: str | None = "Hans", title: str = "Add login"
) -> Task:
    return Task(
        "u1",
        title,
        "d",
        "s",
        "approved",
        None,
        dev,
        "2026",
        number=1,
        pull_request_statuses=statuses,
    )


@pytest.mark.parametrize(
    ("state", "draft", "merged", "expected"),
    [
        ("open", False, False, S.OPEN),
        ("open", True, False, S.DRAFT),
        ("closed", False, True, S.MERGED),
        ("closed", False, False, S.CLOSED),
        (None, None, False, S.OPEN),
    ],
)
def test_classify(state, draft, merged, expected) -> None:
    assert classify(state, draft, merged) is expected


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ((), (S.NO_PR, 0)),
        ((S.MERGED, S.OPEN), (S.OPEN, 2)),
        ((S.DRAFT, S.CLOSED), (S.DRAFT, 2)),
        ((S.CLOSED, S.MERGED), (S.MERGED, 2)),
        ((S.OPEN, S.OPEN), (S.OPEN, 2)),
    ],
)
def test_summarise(statuses, expected) -> None:
    assert summarise(statuses) == expected


def test_title_has_status_in_brackets_at_the_end() -> None:
    title = expander_title(task((S.OPEN,)))
    assert title == r"Task\-1 - Add login - Hans :green-badge[\[Open\]]".replace(
        r"\-", "-"
    )


def test_no_pr_shows_the_task_status_never_no_pr() -> None:
    title = expander_title(task(dev=None))
    assert "No PR" not in title
    assert "unassigned" in title
    assert title.endswith(r":gray-badge[\[Approved\]]")


def test_title_shows_count() -> None:
    assert r"\[Open \(2\)\]" in expander_title(task((S.OPEN, S.OPEN)))


@pytest.mark.parametrize(
    ("status", "colour"),
    [
        (S.OPEN, "green"),
        (S.DRAFT, "gray"),
        (S.MERGED, "violet"),
        (S.CLOSED, "red"),
        (S.NO_PR, "gray"),
    ],
)
def test_colours(status, colour) -> None:
    assert format_status(status, 1).startswith(f":{colour}-badge[")


def test_status_is_text() -> None:
    assert "Merged" in format_status(S.MERGED, 1)


def test_markup_in_title_is_escaped() -> None:
    title = expander_title(task(title="**bold** :red[x] [l](http://e)"))
    assert "**" not in title.replace(r"\*", "")
    assert ":red[x]" not in title


def test_fetch_tasks_builds_statuses_from_neo4j_only() -> None:
    driver = MagicMock()
    row = MagicMock()
    row.data.return_value = {
        "id": "u1",
        "number": 1,
        "title": "t",
        "description": "d",
        "specification": "s",
        "status": "approved",
        "recommended_developer": None,
        "assigned_developer": "Hans",
        "created_at": "2026",
        "pull_requests": [
            {"state": "open", "draft": False, "merged": False},
            {"state": "closed", "draft": False, "merged": True},
        ],
        "previous_assignments": [],
    }
    driver.execute_query.return_value = ([row], None, None)
    [fetched] = fetch_tasks(driver)
    assert fetched.pull_request_statuses == (S.OPEN, S.MERGED)
    assert "HAS_PULL_REQUEST" in driver.execute_query.call_args_list[-1].args[0]


def test_fetch_tasks_without_pull_requests() -> None:
    assert classify_rows([]) == ()
