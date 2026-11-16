"""Neo4j persistence for tasks (features/task-creation-developer-assignment.feature)."""

from unittest.mock import MagicMock

import pytest

from flaskehals.assignment import DeveloperProfile
from flaskehals.tasks import (
    NewTask,
    Task,
    TaskSaveError,
    fetch_developer_profiles,
    fetch_tasks,
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
    row = {
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
