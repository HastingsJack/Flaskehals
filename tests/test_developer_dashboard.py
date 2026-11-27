"""One test per scenario in features/developer-dashboard.feature (AppTest)."""

from pathlib import Path

import pytest
from conftest import TEST_PASSWORD, TEST_USERNAME
from neo4j.exceptions import ServiceUnavailable
from streamlit.testing.v1 import AppTest

from flaskehals.developers import DeveloperOverview, MergeStats

APP_PATH = str(Path(__file__).parents[1] / "src" / "flaskehals" / "app.py")


def open_dashboard(
    monkeypatch: pytest.MonkeyPatch, developers: list[DeveloperOverview]
) -> AppTest:
    calls: list[object] = []

    def fake_fetch(*args: object) -> list[DeveloperOverview]:
        calls.append(args)
        return developers

    monkeypatch.setattr("flaskehals.developers.fetch_developer_overview", fake_fetch)
    at = AppTest.from_file(APP_PATH).run()
    at.text_input(key="login_username").input(TEST_USERNAME)
    at.text_input(key="login_password").input(TEST_PASSWORD)
    at.button[0].click().run()
    assert not at.exception
    assert calls  # developers came from the Neo4j layer, not hardcoded
    return at


pytestmark = pytest.mark.usefixtures("auth_env", "neo4j_env")


def image_kinds(at: AppTest) -> list[str]:
    """Classify each rendered image: the default SVG avatar or a PNG picture."""
    urls = [i.proto.imgs[0].url for i in at.get("image")]  # type: ignore[attr-defined]
    return ["default" if u.startswith("data:image/svg+xml") else "png" for u in urls]


PEOPLE = [
    DeveloperOverview("Hans", "no-such-file.png", 2, 1, 0),
    DeveloperOverview("Peter", "peter.png", 0, 3, 0),
]


def test_display_all_developers_with_picture_and_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = open_dashboard(monkeypatch, PEOPLE)
    # Peter's configured picture is shown; Hans's file is missing -> default.
    assert image_kinds(at) == ["default", "png"]
    names = [m.value for m in at.markdown]
    assert "**Hans**" in names
    assert "**Peter**" in names


def test_display_developer_workload(monkeypatch: pytest.MonkeyPatch) -> None:
    at = open_dashboard(monkeypatch, PEOPLE)
    values = [(m.label, m.value) for m in at.metric if "merged" not in m.label]
    assert values == [
        ("Open PRs", "2"), ("Assigned for review", "1"), ("Assigned tasks", "0"),
        ("Open PRs", "0"), ("Assigned for review", "3"), ("Assigned tasks", "0"),
    ]  # fmt: skip


def test_developer_without_work_is_shown_with_zeros(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = open_dashboard(monkeypatch, [DeveloperOverview("Idle", None, 0, 0, 0)])
    assert "**Idle**" in [m.value for m in at.markdown]
    assert [m.value for m in at.metric] == ["0"] * 7


def test_missing_picture_shows_default_avatar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = open_dashboard(monkeypatch, [DeveloperOverview("Nopic", None, 1, 0, 0)])
    assert "**Nopic**" in [m.value for m in at.markdown]
    assert image_kinds(at) == ["default"]


def test_empty_state_when_no_developers(monkeypatch: pytest.MonkeyPatch) -> None:
    at = open_dashboard(monkeypatch, [])
    assert [i.value for i in at.info] == [
        "No developers found. Run the GitHub sync to import them."
    ]
    assert not at.error


def test_neo4j_failure_shows_error_not_empty_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object) -> list[DeveloperOverview]:
        raise ServiceUnavailable("down")

    monkeypatch.setattr("flaskehals.developers.fetch_developer_overview", boom)
    at = AppTest.from_file(APP_PATH).run()
    at.text_input(key="login_username").input(TEST_USERNAME)
    at.text_input(key="login_password").input(TEST_PASSWORD)
    at.button[0].click().run()
    assert any("Neo4j" in e.value for e in at.error)
    assert not at.info
    assert not at.exception


def test_missing_neo4j_configuration_fails_securely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NEO4J_PASSWORD")
    monkeypatch.setattr("flaskehals.developers.fetch_developer_overview", lambda *a: [])
    at = AppTest.from_file(APP_PATH).run()
    at.text_input(key="login_username").input(TEST_USERNAME)
    at.text_input(key="login_password").input(TEST_PASSWORD)
    at.button[0].click().run()
    assert any("not configured" in e.value for e in at.error)
    assert not at.info


def test_assigned_task_count_is_displayed(monkeypatch: pytest.MonkeyPatch) -> None:
    at = open_dashboard(monkeypatch, [DeveloperOverview("Busy", None, 0, 0, 2)])
    assert [(m.label, m.value) for m in at.metric][2] == ("Assigned tasks", "2")


def test_merge_statistics_are_displayed(monkeypatch: pytest.MonkeyPatch) -> None:
    stats = MergeStats(1, 4, 2, 5)
    at = open_dashboard(monkeypatch, [DeveloperOverview("Busy", None, 0, 0, 0, stats)])
    assert [(m.label, m.value) for m in at.metric if "merged" in m.label] == [
        ("Authored & merged (7d)", "1"),
        ("Authored & merged (30d)", "4"),
        ("Commented & merged (7d)", "2"),
        ("Commented & merged (30d)", "5"),
    ]


def test_merge_statistics_default_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    at = open_dashboard(monkeypatch, [DeveloperOverview("Idle", None, 0, 0, 0)])
    assert [m.value for m in at.metric if "merged" in m.label] == ["0"] * 4
