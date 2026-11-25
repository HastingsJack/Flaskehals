"""Synchronise GitHub pull requests into Neo4j.

Run with: uv run flaskehals-sync

All GitHub data is fetched before anything is written, and the Neo4j write
is a single transaction. If GitHub fails partway through, existing Neo4j
data is left untouched.
"""

import logging
import sys
from dataclasses import dataclass

from dotenv import load_dotenv
from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.db import DataStoreError, load_neo4j_config, open_driver
from flaskehals.github import GitHubClient, GitHubError, load_github_config
from flaskehals.interpretation import interpret_comment, interpret_labels
from flaskehals.pull_request_store import (
    SyncedComment,
    SyncedPullRequest,
    write_pull_requests,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResult:
    pull_requests: int
    comments: int


def fetch_pull_requests(client: GitHubClient) -> list[SyncedPullRequest]:
    """Fetch all pull requests and comments and interpret labels/comments."""
    result: list[SyncedPullRequest] = []
    for number in client.list_pull_request_numbers():
        pr = client.get_pull_request(number)
        labels = interpret_labels(pr.labels)
        comments = tuple(
            SyncedComment(comment, interpret_comment(comment.body, labels.reviewer))
            for comment in client.list_comments(number)
        )
        result.append(SyncedPullRequest(pr, labels, comments))
    return result


def sync(client: GitHubClient, driver: Driver) -> SyncResult:
    pull_requests = fetch_pull_requests(client)
    write_pull_requests(driver, client.repository, pull_requests)
    return SyncResult(
        pull_requests=len(pull_requests),
        comments=sum(len(pr.comments) for pr in pull_requests),
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()

    github_config = load_github_config()
    neo4j_config = load_neo4j_config()
    if github_config is None or neo4j_config is None:
        logger.error(
            "Sync is not configured. Set GITHUB_TOKEN, GITHUB_REPOSITORY "
            "(owner/name), NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD."
        )
        return 1

    try:
        with GitHubClient(github_config) as client, open_driver(neo4j_config) as driver:
            result = sync(client, driver)
    except GitHubError as exc:
        logger.error("Sync failed, Neo4j was not changed: %s", exc)
        return 1
    except DataStoreError as exc:
        logger.error("Sync failed: %s", exc)
        return 1
    except (Neo4jError, DriverError) as exc:
        logger.error("Sync failed while writing to Neo4j: %s", exc)
        return 1

    logger.info(
        "Synchronised %d pull requests and %d comments from %s",
        result.pull_requests,
        result.comments,
        github_config.repository,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
