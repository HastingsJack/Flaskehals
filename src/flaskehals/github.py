"""GitHub REST client: reads pull requests and comments, and edits PR labels.

The only write operations are adding and removing labels.
"""

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self
from urllib.parse import quote

import httpx

API_URL = "https://api.github.com"
TOKEN_ENV = "GITHUB_TOKEN"
REPOSITORY_ENV = "GITHUB_REPOSITORY"
# Safety cap on pagination (100 items per page) so a bad "next" link can't
# cause unbounded requests.
MAX_PAGES = 50
_REPOSITORY_PATTERN = re.compile(r"^[\w.-]+/[\w.-]+$")


class GitHubError(Exception):
    """GitHub could not be reached or returned an error."""


class RateLimitError(GitHubError):
    """The GitHub API rate limit has been reached."""

    def __init__(self, reset_at: datetime | None) -> None:
        when = reset_at.isoformat() if reset_at else "unknown"
        super().__init__(f"GitHub API rate limit reached; resets at {when}")
        self.reset_at = reset_at


@dataclass(frozen=True)
class GitHubConfig:
    token: str
    repository: str  # "owner/name"


@dataclass(frozen=True)
class PullRequest:
    github_id: int
    number: int
    title: str
    url: str
    state: str  # "open" or "closed"
    draft: bool
    created_at: str
    updated_at: str
    closed_at: str | None
    merged_at: str | None
    additions: int
    deletions: int
    changed_files: int
    labels: tuple[str, ...]
    head_ref: str = ""  # source branch name, e.g. "feat/task-1"


@dataclass(frozen=True)
class Comment:
    github_id: int
    author: str
    body: str
    created_at: str
    updated_at: str


def load_github_config(env: Mapping[str, str] | None = None) -> GitHubConfig | None:
    """Load GitHub settings, or None if missing or malformed."""
    if env is None:
        env = os.environ
    token = env.get(TOKEN_ENV, "").strip()
    repository = env.get(REPOSITORY_ENV, "").strip()
    if not token or not _REPOSITORY_PATTERN.match(repository):
        return None
    return GitHubConfig(token=token, repository=repository)


def _parse_pull_request(data: dict[str, Any]) -> PullRequest:
    return PullRequest(
        github_id=data["id"],
        number=data["number"],
        title=data["title"],
        url=data["html_url"],
        state=data["state"],
        draft=data.get("draft", False),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        closed_at=data.get("closed_at"),
        merged_at=data.get("merged_at"),
        additions=data["additions"],
        deletions=data["deletions"],
        changed_files=data["changed_files"],
        labels=tuple(label["name"] for label in data.get("labels", [])),
        head_ref=str((data.get("head") or {}).get("ref", "")),
    )


def _parse_comment(data: dict[str, Any]) -> Comment:
    user = data.get("user") or {}  # null for deleted ("ghost") accounts
    return Comment(
        github_id=data["id"],
        author=user.get("login", "ghost"),
        body=data.get("body") or "",
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


def _is_rate_limited(response: httpx.Response) -> bool:
    if response.status_code not in (403, 429):
        return False
    return (
        response.headers.get("x-ratelimit-remaining") == "0"
        or "retry-after" in response.headers
    )


def _reset_time(response: httpx.Response) -> datetime | None:
    reset = response.headers.get("x-ratelimit-reset")
    if reset and reset.isdigit():
        return datetime.fromtimestamp(int(reset), tz=UTC)
    return None


class GitHubClient:
    """Fetches pull request data for one repository.

    Any failure raises GitHubError immediately; there are no automatic
    retries, so a rate limit stops all further requests. The only writes are
    adding and removing labels.
    """

    def __init__(
        self, config: GitHubConfig, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.repository = config.repository
        self._http = httpx.Client(
            base_url=API_URL,
            headers={
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10.0,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _get(
        self, url: str, params: dict[str, str | int] | None = None
    ) -> httpx.Response:
        return self._send("GET", url, params=params)

    def _send(
        self,
        method: str,
        url: str,
        params: dict[str, str | int] | None = None,
        json: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> httpx.Response:
        try:
            response = self._http.request(method, url, params=params, json=json)
        except httpx.HTTPError as exc:
            raise GitHubError(f"Could not reach GitHub: {exc}") from exc
        if _is_rate_limited(response):
            raise RateLimitError(_reset_time(response))
        if response.is_error and not (allow_not_found and response.status_code == 404):
            raise GitHubError(
                f"GitHub returned {response.status_code} for {response.request.url}"
            )
        return response

    def _get_all_pages(
        self, path: str, params: dict[str, str | int] | None = None
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        url: str | None = path
        # Pass query values via params: httpx replaces (not merges) a query
        # string already present in the URL.
        params = {"per_page": 100, **(params or {})}
        pages = 0
        while url is not None:
            pages += 1
            if pages > MAX_PAGES:
                raise GitHubError(f"Stopped after {MAX_PAGES} pages of {path}")
            response = self._get(url, params)
            items.extend(response.json())
            url = response.links.get("next", {}).get("url")
            # The "next" URL already has the full query string. Must be None,
            # not {}: an empty dict would also wipe the URL's query.
            params = None
        return items

    def list_pull_request_numbers(self, state: str = "all") -> list[int]:
        """Numbers of pull requests: "all" (default), "open" or "closed"."""
        items = self._get_all_pages(f"/repos/{self.repository}/pulls", {"state": state})
        return [item["number"] for item in items]

    def get_pull_request(self, number: int) -> PullRequest:
        # Only the single-PR endpoint includes additions/deletions/changed_files.
        response = self._get(f"/repos/{self.repository}/pulls/{number}")
        return _parse_pull_request(response.json())

    def list_comments(self, number: int) -> list[Comment]:
        """Conversation comments (not inline review comments)."""
        items = self._get_all_pages(
            f"/repos/{self.repository}/issues/{number}/comments"
        )
        return [_parse_comment(item) for item in items]

    def add_labels(self, number: int, labels: Sequence[str]) -> None:
        """Add labels to a pull request (labels are created if missing)."""
        if not labels:
            return
        self._send(
            "POST",
            f"/repos/{self.repository}/issues/{number}/labels",
            json={"labels": list(labels)},
        )

    def remove_label(self, number: int, label: str) -> None:
        """Remove one label from a pull request. A label already gone is fine."""
        self._send(
            "DELETE",
            f"/repos/{self.repository}/issues/{number}/labels/{quote(label, safe='')}",
            allow_not_found=True,
        )
