from unittest.mock import MagicMock

import httpx
import pytest
from fake_github import FakeGitHub, comment_json, pr_json

from flaskehals.github import GitHubError, RateLimitError
from flaskehals.interpretation import LabelInfo, ReviewOutcome
from flaskehals.sync import fetch_pull_requests, main, sync


def test_fetch_combines_pull_requests_labels_and_comments() -> None:
    fake = FakeGitHub(
        [pr_json(1, labels=("dev:Alice", "reviewer:Bob", "priority:high"))],
        {1: [comment_json(10, "[APPROVED] ok"), comment_json(11, "question?")]},
    )
    with fake.client() as client:
        [synced] = fetch_pull_requests(client)
    assert synced.pull_request.number == 1
    assert synced.labels == LabelInfo("Alice", "Bob", "high")
    assert [c.outcome for c in synced.comments] == [ReviewOutcome.APPROVED, None]


def test_unrecognised_labels_do_not_fail_sync() -> None:
    fake = FakeGitHub([pr_json(1, labels=("priority:urgent", "wontfix"))])
    with fake.client() as client:
        [synced] = fetch_pull_requests(client)
    assert synced.labels == LabelInfo()


def test_github_failure_leaves_neo4j_untouched() -> None:
    fake = FakeGitHub([pr_json(1)])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/comments"):
            return httpx.Response(500)
        fake.override = None
        response = fake.handle(request)
        fake.override = handler
        return response

    fake.override = handler
    driver = MagicMock()
    with fake.client() as client, pytest.raises(GitHubError):
        sync(client, driver)
    assert driver.mock_calls == []


def test_rate_limit_stops_requests_and_leaves_neo4j_untouched() -> None:
    fake = FakeGitHub()
    fake.override = lambda request: httpx.Response(
        403, headers={"x-ratelimit-remaining": "0"}
    )
    driver = MagicMock()
    with fake.client() as client, pytest.raises(RateLimitError):
        sync(client, driver)
    assert len(fake.requests) == 1
    assert driver.mock_calls == []


def test_main_fails_safely_without_configuration(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    for name in [
        "GITHUB_TOKEN",
        "GITHUB_REPOSITORY",
        "NEO4J_URI",
        "NEO4J_USERNAME",
        "NEO4J_PASSWORD",
    ]:
        monkeypatch.delenv(name, raising=False)
    assert main() == 1
    assert "not configured" in caplog.text
