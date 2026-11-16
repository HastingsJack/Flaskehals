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
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.github import GitHubClient, GitHubError, load_github_config
from flaskehals.graph import (
    SyncedComment,
    SyncedPullRequest,
    ensure_constraints,
    load_neo4j_config,
    write_pull_requests,
)
from flaskehals.interpretation import interpret_comment, interpret_labels

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


def sync(
    client: GitHubClient, driver: Driver, database: str | None = None
) -> SyncResult:
    pull_requests = fetch_pull_requests(client)
    ensure_constraints(driver, database)
    write_pull_requests(driver, client.repository, pull_requests, database)
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
        with (
            GitHubClient(github_config) as client,
            GraphDatabase.driver(
                neo4j_config.uri, auth=(neo4j_config.username, neo4j_config.password)
            ) as driver,
        ):
            # Fail fast with a clear error, rather than the driver retrying
            # for ~30s and spending GitHub requests first.
            try:
                driver.verify_connectivity()
            except (Neo4jError, DriverError) as exc:
                logger.error(
                    "Cannot connect to Neo4j at %s - is it running? (%s)",
                    neo4j_config.uri,
                    exc,
                )
                return 1
            result = sync(client, driver, neo4j_config.database)
    except GitHubError as exc:
        logger.error("Sync failed, Neo4j was not changed: %s", exc)
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
