"""Unit tests for the developer overview queries and picture resolution."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from flaskehals.developers import (
    DEFAULT_AVATAR,
    DeveloperOverview,
    fetch_developer_overview,
    resolve_picture,
)


def test_fetch_maps_records_including_assigned_tasks() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = (
        [
            {
                "name": "Hans",
                "picture": "hans.png",
                "open_pull_requests": 2,
                "review_assignments": 1,
                "assigned_tasks": 2,
            },
            {
                "name": "Idle",
                "picture": None,
                "open_pull_requests": 0,
                "review_assignments": 0,
                "assigned_tasks": 0,
            },
        ],
        None,
        None,
    )
    assert fetch_developer_overview(driver, "db") == [
        DeveloperOverview("Hans", "hans.png", 2, 1, 2),
        DeveloperOverview("Idle", None, 0, 0, 0),
    ]
    assert driver.execute_query.call_args.kwargs == {"database_": "db"}


def test_query_is_read_only_and_counts_only_open_pull_requests() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)
    fetch_developer_overview(driver)
    query = driver.execute_query.call_args.args[0]
    assert "state: 'open'" in query
    assert not any(w in query for w in ("CREATE", "MERGE", "SET ", "DELETE"))


def test_resolve_existing_picture(tmp_path: Path) -> None:
    (tmp_path / "peter.png").write_bytes(b"x")
    assert resolve_picture("peter.png", tmp_path) == tmp_path / "peter.png"


@pytest.mark.parametrize(
    "picture",
    [None, "", "missing.png", "../secret.png", "/etc/passwd", "sub/peter.png", ".."],
)
def test_resolve_falls_back_to_default(tmp_path: Path, picture: str | None) -> None:
    (tmp_path / "peter.png").write_bytes(b"x")
    (tmp_path.parent / "secret.png").write_bytes(b"x")
    assert resolve_picture(picture, tmp_path) == DEFAULT_AVATAR


def test_default_avatar_and_seed_picture_exist() -> None:
    assert DEFAULT_AVATAR.is_file()
    assert resolve_picture("peter.png") != DEFAULT_AVATAR
