"""An in-memory fake of the GitHub REST endpoints used by the sync."""

from collections.abc import Callable
from typing import Any

import httpx

from flaskehals.github import GitHubClient, GitHubConfig

REPO = "octo/repo"


def pr_json(
    number: int, labels: tuple[str, ...] = (), **overrides: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": 1000 + number,
        "number": number,
        "title": f"PR {number}",
        "html_url": f"https://github.com/{REPO}/pull/{number}",
        "state": "open",
        "draft": False,
        "created_at": "2026-11-01T10:00:00Z",
        "updated_at": "2026-11-02T10:00:00Z",
        "closed_at": None,
        "merged_at": None,
        "additions": 10,
        "deletions": 2,
        "changed_files": 3,
        "labels": [{"name": name} for name in labels],
    }
    data.update(overrides)
    return data


def comment_json(github_id: int, body: str, author: str = "jack") -> dict[str, Any]:
    return {
        "id": github_id,
        "user": {"login": author},
        "body": body,
        "created_at": "2026-11-03T10:00:00Z",
        "updated_at": "2026-11-03T10:00:00Z",
    }


class FakeGitHub:
    def __init__(
        self,
        pulls: list[dict[str, Any]] | None = None,
        comments: dict[int, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.pulls = pulls or []
        self.comments = comments or {}
        self.requests: list[httpx.Request] = []
        # Set to make every request return this response instead.
        self.override: Callable[[httpx.Request], httpx.Response] | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.override is not None:
            return self.override(request)
        path = request.url.path
        if path == f"/repos/{REPO}/pulls":
            return httpx.Response(200, json=self.pulls)
        for pr in self.pulls:
            if path == f"/repos/{REPO}/pulls/{pr['number']}":
                return httpx.Response(200, json=pr)
            if path == f"/repos/{REPO}/issues/{pr['number']}/comments":
                return httpx.Response(200, json=self.comments.get(pr["number"], []))
        return httpx.Response(404, json={"message": "Not Found"})

    def client(self) -> GitHubClient:
        return GitHubClient(
            GitHubConfig(token="test-token", repository=REPO),
            transport=httpx.MockTransport(self.handle),
        )
