"""Neo4j persistence for tasks (features/task-creation-developer-assignment.feature)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from flaskehals.assignment import DeveloperProfile
from flaskehals.tasks import (
    NewTask,
    ReassignmentError,
    Task,
    TaskSaveError,
    fetch_developer_profiles,
    fetch_tasks,
    reassign_task,
    save_approved_task,
)

NEW_TASK = NewTask(
    title="CSV export",
    description="original words",
    specification="## Objective\nedited",
    assigned_developer="Peter",
    recommended_developer="Hans",
)


def driver_saving(record: dict[str, str] | None) -> tuple[MagicMock, MagicMock]:
    """A driver whose write transaction runs the work function against a fake tx."""
    tx = MagicMock()
    tx.run.return_value.single.return_value = record
    session = MagicMock()
    session.execute_write.side_effect = lambda work: work(tx)
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    return driver, tx


def test_save_stores_all_task_fields_in_one_write() -> None:
    driver, tx = driver_saving({"id": "x"})
    task_id = save_approved_task(driver, NEW_TASK, "db")
    assert task_id == "x"
    assert tx.run.call_args.kwargs["id"]
    kwargs = tx.run.call_args.kwargs
    assert kwargs["title"] == "CSV export"
    assert kwargs["description"] == "original words"
    assert kwargs["specification"] == "## Objective\nedited"
    assert kwargs["assigned_developer"] == "Peter"
    assert kwargs["recommended_developer"] == "Hans"
    query = tx.run.call_args.args[0]
    assert "status: 'approved'" in query
    assert "ASSIGNED_TO" in query
    assert "RECOMMENDED" in query
    driver.session.assert_called_once_with(database="db")


def test_save_raises_when_assignee_does_not_exist() -> None:
    driver, _ = driver_saving(None)
    with pytest.raises(TaskSaveError, match="Peter"):
        save_approved_task(driver, NEW_TASK)


def test_save_propagates_database_errors() -> None:
    driver = MagicMock()
    driver.execute_query.side_effect = RuntimeError("down")
    with pytest.raises(RuntimeError):
        save_approved_task(driver, NEW_TASK)


def test_fetch_tasks_maps_records() -> None:
    row: dict[str, Any] = {
        "id": "1",
        "title": "T",
        "description": "D",
        "specification": "S",
        "status": "approved",
        "recommended_developer": "Hans",
        "assigned_developer": "Peter",
        "created_at": "2026-11-16T10:00:00Z",
    }
    record = MagicMock()
    record.data.return_value = row
    driver = MagicMock()
    driver.execute_query.return_value = ([record], None, None)
    assert fetch_tasks(driver, "db") == [Task(**row)]
    assert driver.execute_query.call_args.kwargs == {"database_": "db"}


def test_fetch_developer_profiles_maps_records_and_drops_null_history() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = (
        [
            {
                "name": "Hans",
                "experience_level": "senior",
                "open_pull_requests": 1,
                "review_assignments": 2,
                "assigned_tasks": 3,
                "history": ["Fix login", None, "python"],
            },
            {
                "name": "New",
                "experience_level": None,
                "open_pull_requests": 0,
                "review_assignments": 0,
                "assigned_tasks": 0,
                "history": [],
            },
        ],
        None,
        None,
    )
    assert fetch_developer_profiles(driver) == [
        DeveloperProfile("Hans", 1, 2, 3, "senior", ("Fix login", "python")),
        DeveloperProfile("New"),
    ]


# --- Re-assignment (features/tasks/task-reassignment.feature) ---------------


def reassign_with(state: dict[str, str | None] | None) -> tuple[MagicMock, MagicMock]:
    tx = MagicMock()
    tx.run.return_value.single.return_value = state
    session = MagicMock()
    session.execute_write.side_effect = lambda work: work(tx)
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    return driver, tx


def test_reassign_moves_assignment_in_one_transaction() -> None:
    driver, tx = reassign_with({"current": "Peter", "target": "Hans"})
    reassign_task(driver, "1", "Hans", "Peter", "db")
    assert tx.run.call_count == 2
    write_query = tx.run.call_args_list[1].args[0]
    assert "PREVIOUSLY_ASSIGNED_TO" in write_query and "DELETE" in write_query
    assert tx.run.call_args_list[1].kwargs == {"task_id": "1", "new_developer": "Hans"}


@pytest.mark.parametrize(
    ("state", "expected", "message"),
    [
        (None, "Peter", "no longer exists"),
        ({"current": "Peter", "target": "Peter"}, "Peter", "already assigned"),
        ({"current": "Zed", "target": "Hans"}, "Peter", "now assigned to Zed"),
        ({"current": "Peter", "target": None}, "Peter", "Developer 'Hans'"),
    ],
)
def test_reassign_refuses_invalid_changes_without_writing(
    state: dict[str, str | None] | None, expected: str, message: str
) -> None:
    new = "Peter" if state and state["target"] == "Peter" else "Hans"
    driver, tx = reassign_with(state)
    with pytest.raises(ReassignmentError, match=message):
        reassign_task(driver, "1", new, expected)
    assert tx.run.call_count == 1  # only the read; nothing written


def test_fetch_tasks_orders_previous_assignments_chronologically() -> None:
    record = MagicMock()
    record.data.return_value = {
        "id": "1", "title": "t", "description": "d", "specification": "s",
        "status": "approved", "recommended_developer": None,
        "assigned_developer": "C", "created_at": "2026-01-01",
        "previous_assignments": [
            {"developer": "B", "assigned_at": "2026-01-02", "unassigned_at": "2026-01-03"},
            {"developer": "A", "assigned_at": "2026-01-01", "unassigned_at": "2026-01-02"},
        ],
    }  # fmt: skip
    driver = MagicMock()
    driver.execute_query.return_value = ([record], None, None)
    (task,) = fetch_tasks(driver)
    assert [p.developer for p in task.previous_assignments] == ["A", "B"]
