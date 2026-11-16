import httpx
import pytest
from fake_github import REPO, FakeGitHub, comment_json, pr_json

from flaskehals.github import (
    MAX_PAGES,
    GitHubConfig,
    GitHubError,
    RateLimitError,
    load_github_config,
)


def test_load_config() -> None:
    env = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "octo/repo"}
    assert load_github_config(env) == GitHubConfig("t", "octo/repo")


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"GITHUB_TOKEN": "t"},
        {"GITHUB_REPOSITORY": "octo/repo"},
        {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "not-a-repo"},
        {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "https://github.com/octo/repo"},
    ],
)
def test_missing_or_invalid_config(env: dict[str, str]) -> None:
    assert load_github_config(env) is None


def test_lists_all_pull_requests_including_closed() -> None:
    fake = FakeGitHub([pr_json(1), pr_json(2, state="closed")])
    with fake.client() as client:
        assert client.list_pull_request_numbers() == [1, 2]
    assert fake.requests[0].url.params["state"] == "all"


def test_pull_request_details() -> None:
    fake = FakeGitHub([pr_json(7, labels=("dev:Alice",), draft=True)])
    with fake.client() as client:
        pr = client.get_pull_request(7)
    assert (pr.number, pr.title, pr.url) == (
        7,
        "PR 7",
        f"https://github.com/{REPO}/pull/7",
    )
    assert pr.draft is True
    assert (pr.created_at, pr.updated_at) == (
        "2026-11-01T10:00:00Z",
        "2026-11-02T10:00:00Z",
    )
    assert (pr.additions, pr.deletions, pr.changed_files) == (10, 2, 3)
    assert pr.labels == ("dev:Alice",)


def test_comments() -> None:
    fake = FakeGitHub([pr_json(1)], {1: [comment_json(5, "Nice", author="jack")]})
    with fake.client() as client:
        [comment] = client.list_comments(1)
    assert (comment.github_id, comment.author, comment.body) == (5, "jack", "Nice")
    assert comment.created_at == "2026-11-03T10:00:00Z"


def test_comment_from_deleted_user() -> None:
    data = comment_json(5, "Hi") | {"user": None}
    fake = FakeGitHub([pr_json(1)], {1: [data]})
    with fake.client() as client:
        assert client.list_comments(1)[0].author == "ghost"


def test_follows_pagination() -> None:
    pages = {
        "1": (
            [pr_json(1)],
            {"Link": f'<https://api.github.com/repos/{REPO}/pulls?page=2>; rel="next"'},
        ),
        "2": ([pr_json(2)], {}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        body, headers = pages[request.url.params.get("page", "1")]
        return httpx.Response(200, json=body, headers=headers)

    fake = FakeGitHub()
    fake.override = handler
    with fake.client() as client:
        assert client.list_pull_request_numbers() == [1, 2]


def test_github_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    fake = FakeGitHub()
    fake.override = handler
    with (
        fake.client() as client,
        pytest.raises(GitHubError, match="Could not reach GitHub"),
    ):
        client.list_pull_request_numbers()


def test_github_server_error() -> None:
    fake = FakeGitHub()
    fake.override = lambda request: httpx.Response(502)
    with fake.client() as client, pytest.raises(GitHubError, match="502"):
        client.list_pull_request_numbers()


@pytest.mark.parametrize(
    ("status", "headers"),
    [
        (403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1800000000"}),
        (429, {"retry-after": "60"}),
    ],
    ids=["primary", "secondary"],
)
def test_rate_limit(status: int, headers: dict[str, str]) -> None:
    fake = FakeGitHub()
    fake.override = lambda request: httpx.Response(status, headers=headers)
    with fake.client() as client, pytest.raises(RateLimitError, match="rate limit"):
        client.list_pull_request_numbers()
    assert len(fake.requests) == 1  # no retries


def test_forbidden_without_rate_limit_is_plain_error() -> None:
    fake = FakeGitHub()
    fake.override = lambda request: httpx.Response(
        403, headers={"x-ratelimit-remaining": "42"}
    )
    with fake.client() as client, pytest.raises(GitHubError) as exc_info:
        client.list_pull_request_numbers()
    assert not isinstance(exc_info.value, RateLimitError)


def test_pagination_is_capped() -> None:
    # A "next" link that always points back at itself must not loop forever.
    link = f'<https://api.github.com/repos/{REPO}/pulls?page=1>; rel="next"'
    fake = FakeGitHub()
    fake.override = lambda request: httpx.Response(200, json=[], headers={"Link": link})
    with fake.client() as client, pytest.raises(GitHubError, match="Stopped after"):
        client.list_pull_request_numbers()
    assert len(fake.requests) == MAX_PAGES
