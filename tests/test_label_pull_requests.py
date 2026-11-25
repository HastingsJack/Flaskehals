"""flaskehals-label (features/githubsync/pull-request-task-assignment.feature)."""

from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest
from fake_github import FakeGitHub, pr_json
from neo4j.exceptions import ServiceUnavailable

from flaskehals import label_pull_requests as label_module
from flaskehals.developer_scoring import DeveloperProfile
from flaskehals.label_pull_requests import LabelResult, label_pull_requests
from flaskehals.models import Task
from flaskehals.reviewer_recommendations import ReviewerRecommendation

SPEC = "## Objective\nExport CSV from Postgres"
TASK = Task("u1", "CSV export", "d", SPEC, "approved", "Hans", "Hans", "x", number=1)
PROFILES = [
    DeveloperProfile("Hans", history_texts=("Postgres CSV export",)),
    DeveloperProfile("Peter", history_texts=("Postgres reviews",)),
]


def pr(number: int, branch: str, **kwargs: Any) -> dict[str, Any]:
    return pr_json(number, head={"ref": branch}, **kwargs)


class Env:
    """Fake Neo4j layer: saved recommendations are tracked in memory."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.tasks = [TASK]
        self.stored: list[ReviewerRecommendation] = []
        self.saved: list[str] = []
        self.marked: list[tuple[str, int]] = []
        self.events: list[str] = []
        self.save_error: Exception | None = None
        self.read_error: Exception | None = None
        monkeypatch.setattr(label_module, "fetch_tasks", self.fetch_tasks)
        monkeypatch.setattr(
            label_module, "fetch_developer_profiles", lambda *a: PROFILES
        )
        monkeypatch.setattr(
            label_module, "fetch_recommendations", lambda *a: self.stored
        )
        monkeypatch.setattr(label_module, "save_recommendation", self.save)
        monkeypatch.setattr(label_module, "mark_labelled", self.mark)

    def fetch_tasks(self, *args: object) -> list[Task]:
        if self.read_error:
            raise self.read_error
        return self.tasks

    def save(
        self, driver: object, request: object, plan: object, db: object = None
    ) -> None:
        if self.save_error:
            raise self.save_error
        self.events.append("save")
        self.saved.append(f"{request.number}:{plan.reviewer}")  # type: ignore[attr-defined]

    def mark(
        self, driver: object, task_id: str, github_id: int, db: object = None
    ) -> None:
        self.events.append("mark")
        self.marked.append((task_id, github_id))


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Env:
    return Env(monkeypatch)


def run(fake: FakeGitHub) -> LabelResult:
    with fake.client() as client:
        return label_pull_requests(client, MagicMock())


def test_labels_pull_request_and_stores_recommendation(env: Env) -> None:
    fake = FakeGitHub([pr(5, "feat/task-1")])
    assert run(fake) == LabelResult(labelled=1)
    assert env.saved == ["5:Peter"]
    assert env.marked == [("u1", 1005)]
    assert fake.label_edits == [("add", 5, ["dev:Hans", "reviewer:Peter"])]


def test_recommendation_is_stored_before_labels_and_marked_after(env: Env) -> None:
    fake = FakeGitHub([pr(5, "feat/task-1")])
    original = fake.handle

    def recording(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            env.events.append("labels")
        return original(request)

    fake.handle = recording  # type: ignore[method-assign]
    run(fake)
    assert env.events == ["save", "labels", "mark"]


def test_replaces_existing_reviewer_label(env: Env) -> None:
    fake = FakeGitHub([pr(5, "feat/task-1", labels=("dev:Hans", "reviewer:Bob"))])
    run(fake)
    assert fake.label_edits == [
        ("remove", 5, "reviewer:Bob"),
        ("add", 5, ["reviewer:Peter"]),
    ]


def test_skips_pull_requests_without_a_task_closed_and_drafts(env: Env) -> None:
    fake = FakeGitHub(
        [
            pr(1, "main"),
            pr(2, "feat/task-99"),
            pr(3, "feat/task-1", state="closed"),
            pr(4, "feat/task-1", draft=True),
        ]
    )
    assert run(fake) == LabelResult(skipped=3)  # the closed one is never listed
    assert fake.label_edits == [] and env.saved == []


def test_a_labelled_pull_request_is_processed_only_once(env: Env) -> None:
    env.stored = [
        ReviewerRecommendation("u1", 5, "u", "Hans", "Peter", None, (), "x", True)
    ]
    fake = FakeGitHub([pr(5, "feat/task-1")])
    assert run(fake) == LabelResult(skipped=1)
    assert env.saved == [] and fake.label_edits == []


def test_second_pull_request_for_same_task_gets_its_own_recommendation(
    env: Env,
) -> None:
    env.stored = [
        ReviewerRecommendation("u1", 5, "u", "Hans", "Peter", None, (), "x", True)
    ]
    fake = FakeGitHub([pr(5, "feat/task-1"), pr(6, "feat/task-1-fix")])
    assert run(fake) == LabelResult(labelled=1, skipped=1)
    assert env.saved == ["6:Peter"]


def test_unlabelled_stored_recommendation_is_labelled_without_a_new_one(
    env: Env,
) -> None:
    env.stored = [
        ReviewerRecommendation("u1", 5, "u", "Hans", "Maria", None, (), "x", False)
    ]
    fake = FakeGitHub([pr(5, "feat/task-1")])
    assert run(fake) == LabelResult(labelled=1)
    assert env.saved == []
    assert fake.label_edits == [("add", 5, ["dev:Hans", "reviewer:Maria"])]
    assert env.marked == [("u1", 1005)]


def test_github_failure_while_labelling_keeps_recommendation_and_continues(
    env: Env,
) -> None:
    fake = FakeGitHub([pr(5, "feat/task-1"), pr(6, "feat/task-1-b")])
    original = fake.handle
    fake.handle = lambda r: (  # type: ignore[method-assign]
        httpx.Response(500)
        if r.method == "POST" and "/issues/5/" in r.url.path
        else original(r)
    )
    assert run(fake) == LabelResult(labelled=1, failed=1)
    assert env.saved == ["5:Peter", "6:Peter"]  # recommendation kept for #5
    assert env.marked == [("u1", 1006)]  # #5 stays unlabelled, retried next run


def test_neo4j_failure_adds_no_label_and_continues(env: Env) -> None:
    env.save_error = ServiceUnavailable("down")
    fake = FakeGitHub([pr(5, "feat/task-1"), pr(6, "feat/task-1-b")])
    assert run(fake) == LabelResult(failed=2)
    assert fake.label_edits == [] and env.marked == []


def test_rate_limit_stops_the_run(env: Env) -> None:
    fake = FakeGitHub([pr(5, "feat/task-1"), pr(6, "feat/task-1-b")])
    original = fake.handle
    fake.handle = lambda r: (  # type: ignore[method-assign]
        httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
        if r.method == "POST"
        else original(r)
    )
    assert run(fake) == LabelResult(failed=1)


def test_github_failure_listing_changes_nothing(env: Env) -> None:
    fake = FakeGitHub()
    fake.override = lambda r: httpx.Response(500)
    from flaskehals.github import GitHubError

    with pytest.raises(GitHubError):
        run(fake)
    assert env.saved == [] and env.marked == []


def test_neo4j_failure_reading_changes_nothing(env: Env) -> None:
    env.read_error = ServiceUnavailable("down")
    fake = FakeGitHub([pr(5, "feat/task-1")])
    with pytest.raises(ServiceUnavailable):
        run(fake)
    assert fake.label_edits == []


def test_missing_configuration_stops_before_contacting_anything(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for name in ("GITHUB_TOKEN", "GITHUB_REPOSITORY", "NEO4J_URI", "NEO4J_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(label_module, "load_dotenv", lambda: None)
    assert label_module.main() == 1
    assert "Not configured" in caplog.text
