"""Scenarios from features/tasks/task-reviewer-reassignment.feature."""

import httpx
import pytest
from fake_github import FakeGitHub, pr_json
from neo4j.exceptions import ServiceUnavailable
from test_task_creation import Fakes, button, fakes, go_to, open_task_page  # noqa: F401
from test_task_reviews import SCORES, TASK, rec, texts

from flaskehals import reviewer_reassignment as module
from flaskehals.db import DataStoreError
from flaskehals.developer_scoring import DeveloperProfile
from flaskehals.reviewer_recommendations import (
    PreviousReviewer,
    ReviewerReassignmentError,
    _history,
    check_reviewer_change,
)

pytestmark = pytest.mark.usefixtures("auth_env", "neo4j_env")

STATE = {"current": "Peter", "developer": "Hans", "target": "Niels"}


# --- Validation (Neo4j state) --------------------------------------------------


def test_valid_change_is_accepted() -> None:
    check_reviewer_change(STATE, "Niels", "Peter")


@pytest.mark.parametrize(
    ("state", "new", "expected", "message"),
    [
        (None, "Niels", "Peter", "no longer exists"),
        (STATE, "Niels", "Maria", "now Peter"),  # stale view
        (STATE, "Peter", "Peter", "already the reviewer"),
        (STATE, "Hans", "Peter", "cannot review their own"),
        ({**STATE, "target": None}, "Nobody", "Peter", "does not exist"),
    ],
)
def test_invalid_changes_are_rejected(
    state: dict[str, str | None] | None, new: str, expected: str, message: str
) -> None:
    with pytest.raises(ReviewerReassignmentError, match=message):
        check_reviewer_change(state, new, expected)


def test_history_lists_replaced_reviewers_in_order() -> None:
    history = _history(
        "2026-11-01T00:00:00Z",
        [
            {"from_reviewer": "Niels", "changed_at": "2026-11-03T00:00:00Z"},
            {"from_reviewer": "Peter", "changed_at": "2026-11-02T00:00:00Z"},
        ],
    )
    assert history == (
        PreviousReviewer("Peter", "2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z"),
        PreviousReviewer("Niels", "2026-11-02T00:00:00Z", "2026-11-03T00:00:00Z"),
    )


def test_original_recommendation_is_kept_after_reassignment() -> None:
    changed = rec(reviewer="Niels", previous_reviewers=_history("a", [
        {"from_reviewer": "Peter", "changed_at": "b"}
    ]))  # fmt: skip
    assert changed.recommended_reviewer == "Peter"
    assert rec().recommended_reviewer == "Peter"


# --- GitHub then Neo4j ---------------------------------------------------------


class Neo4j:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.validate_error: Exception | None = None
        self.save_error: Exception | None = None
        self.saved: list[tuple[str, int, str, str]] = []
        monkeypatch.setattr(module, "validate_reviewer_change", self.validate)
        monkeypatch.setattr(module, "save_reviewer_change", self.save)

    def validate(self, driver: object, *args: object) -> None:
        if self.validate_error:
            raise self.validate_error

    def save(self, driver: object, *args: object) -> None:
        if self.save_error:
            raise self.save_error
        self.saved.append(args)  # type: ignore[arg-type]


@pytest.fixture
def neo4j(monkeypatch: pytest.MonkeyPatch) -> Neo4j:
    return Neo4j(monkeypatch)


def github(**overrides: object) -> FakeGitHub:
    return FakeGitHub([pr_json(7, ("dev:Hans", "reviewer:Peter", "bug"), **overrides)])


def run(gh: FakeGitHub) -> None:
    with gh.client() as client:
        module.reassign_reviewer(None, client, "u1", 7, "Niels", "Peter")  # type: ignore[arg-type]


def test_changes_only_the_reviewer_label_then_saves(neo4j: Neo4j) -> None:
    gh = github()
    run(gh)
    assert gh.label_edits == [
        ("add", 7, ["reviewer:Niels"]),
        ("remove", 7, "reviewer:Peter"),
    ]
    assert neo4j.saved == [("u1", 7, "Niels", "Peter")]


def test_closed_pull_request_is_refused_without_changes(neo4j: Neo4j) -> None:
    gh = github(state="closed")
    with pytest.raises(ReviewerReassignmentError, match="not open"):
        run(gh)
    assert gh.label_edits == [] and neo4j.saved == []


def test_rejected_change_never_touches_github(neo4j: Neo4j) -> None:
    neo4j.validate_error = ReviewerReassignmentError("already the reviewer")
    gh = github()
    with pytest.raises(ReviewerReassignmentError):
        run(gh)
    assert gh.requests == []


def test_database_down_before_the_change_never_touches_github(neo4j: Neo4j) -> None:
    neo4j.validate_error = ServiceUnavailable("down")
    gh = github()
    with pytest.raises(ReviewerReassignmentError, match="Neo4j"):
        run(gh)
    assert gh.requests == []


def test_github_failure_leaves_the_reviewer_unchanged(neo4j: Neo4j) -> None:
    gh = github()
    gh.override = lambda request: httpx.Response(500, json={"message": "boom"})
    with pytest.raises(ReviewerReassignmentError, match="GitHub failed"):
        run(gh)
    assert neo4j.saved == []


def test_rate_limit_is_reported_with_the_reset_time(neo4j: Neo4j) -> None:
    gh = github()
    gh.override = lambda request: httpx.Response(
        403,
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1893456000"},
        json={"message": "rate limit"},
    )
    with pytest.raises(ReviewerReassignmentError, match="resets at"):
        run(gh)
    assert neo4j.saved == []


@pytest.mark.parametrize(
    "error",
    [ServiceUnavailable("down"), ReviewerReassignmentError("The reviewer is now X.")],
)
def test_failed_save_restores_the_label(neo4j: Neo4j, error: Exception) -> None:
    neo4j.save_error = error
    gh = github()
    with pytest.raises(ReviewerReassignmentError):
        run(gh)
    assert gh.label_edits == [
        ("add", 7, ["reviewer:Niels"]),
        ("remove", 7, "reviewer:Peter"),
        ("remove", 7, "reviewer:Niels"),  # undo
        ("add", 7, ["reviewer:Peter"]),
    ]


# --- The task page -------------------------------------------------------------


class Reassigns:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.error: Exception | None = None
        monkeypatch.setattr(
            "flaskehals.reviewer_reassignment.reassign_reviewer", self.reassign
        )

    def reassign(self, driver: object, client: object, *args: object) -> None:
        if self.error:
            raise self.error
        self.calls.append(args)


@pytest.fixture
def page(
    fakes: Fakes,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> Reassigns:
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "octo/repo")
    fakes.tasks = [TASK]
    fakes.recommendations = [rec()]
    fakes.profiles = [
        DeveloperProfile("Hans"),
        DeveloperProfile("Peter"),
        DeveloperProfile("Niels", open_pull_requests=1),
    ]
    return Reassigns(monkeypatch)


def start():  # type: ignore[no-untyped-def]
    at = go_to(open_task_page(), "Tasks")
    return button(at, "Re-assign reviewer").click().run()


def test_button_is_offered_for_each_pull_request(page: Reassigns) -> None:
    at = go_to(open_task_page(), "Tasks")
    assert not button(at, "Re-assign reviewer").disabled


def test_no_button_without_a_pull_request(page: Reassigns, fakes: Fakes) -> None:  # noqa: F811
    fakes.recommendations = []
    at = go_to(open_task_page(), "Tasks")
    assert all(b.label != "Re-assign reviewer" for b in at.button)


def test_no_button_for_a_closed_pull_request(page: Reassigns, fakes: Fakes) -> None:  # noqa: F811
    fakes.recommendations = [rec(pr_state="closed")]
    at = go_to(open_task_page(), "Tasks")
    assert all(b.label != "Re-assign reviewer" for b in at.button)


def test_button_is_disabled_without_github_config(
    page: Reassigns, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN")
    at = go_to(open_task_page(), "Tasks")
    assert button(at, "Re-assign reviewer").disabled


def test_shows_current_reviewer_and_never_offers_the_developer(page: Reassigns) -> None:
    at = start()
    assert "**Current reviewer:** Peter" in texts(at)
    box = at.selectbox(key="reassign_reviewer")
    # Hans is the task's developer, so he is not offered.
    assert box.options == ["Peter (current)", "Niels"]


def test_default_is_the_best_other_candidate(page: Reassigns) -> None:
    assert start().selectbox(key="reassign_reviewer").value == "Niels"


def test_confirming_changes_the_reviewer_through_the_service(page: Reassigns) -> None:
    at = start()
    button(at, "Confirm reviewer").click().run()
    assert page.calls == [("u1", 7, "Niels", "Peter")]
    assert any("changed from Peter to Niels" in s.value for s in at.success)


def test_choosing_the_current_reviewer_makes_no_change(page: Reassigns) -> None:
    at = start()
    at.selectbox(key="reassign_reviewer").select("Peter").run()
    button(at, "Confirm reviewer").click().run()
    assert page.calls == []
    assert any("already the reviewer" in e.value for e in at.error)


def test_a_selection_is_required(page: Reassigns) -> None:
    at = start()
    at.selectbox(key="reassign_reviewer").set_value(None).run()
    button(at, "Confirm reviewer").click().run()
    assert page.calls == []
    assert any("Select a developer" in e.value for e in at.error)


def test_failure_is_shown_and_the_reviewer_stays(page: Reassigns) -> None:
    page.error = DataStoreError("Could not reach Neo4j. Is it running?")
    at = start()
    button(at, "Confirm reviewer").click().run()
    assert any("was not changed" in e.value for e in at.error)
    assert not at.success


def test_cancel_changes_nothing(page: Reassigns) -> None:
    at = start()
    cancel = next(b for b in at.button if b.label == "Cancel")
    cancel.click().run()
    assert page.calls == []
    assert button(at, "Re-assign reviewer")


def test_history_is_listed_and_original_recommendation_kept(
    page: Reassigns,
    fakes: Fakes,  # noqa: F811
) -> None:
    fakes.recommendations = [
        rec(
            reviewer="Niels",
            previous_reviewers=(
                PreviousReviewer(
                    "Peter", "2026-11-25T10:00:00Z", "2026-11-26T10:00:00Z"
                ),
            ),
        )
    ]
    shown = texts(go_to(open_task_page(), "Tasks"))
    assert "Recommended reviewer: **Peter**" in shown
    assert "**Current reviewer:** Niels" in shown
    assert "- Peter: 2026-11-25 to 2026-11-26" in shown
    assert SCORES[0].name == "Peter"
