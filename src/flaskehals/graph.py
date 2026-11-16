"""Neo4j persistence for synchronised pull request data.

All writes use MERGE on GitHub IDs (or names) so repeated syncs update
existing nodes instead of creating duplicates. Relationships derived from
labels are replaced on each sync, so GitHub stays the source of truth.
"""

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import LiteralString

from neo4j import Driver, ManagedTransaction

from flaskehals.github import Comment, PullRequest
from flaskehals.interpretation import LabelInfo, ReviewOutcome

URI_ENV = "NEO4J_URI"
USERNAME_ENV = "NEO4J_USERNAME"
PASSWORD_ENV = "NEO4J_PASSWORD"
DATABASE_ENV = "NEO4J_DATABASE"


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str
    database: str | None = None  # None = server default


@dataclass(frozen=True)
class SyncedComment:
    comment: Comment
    outcome: ReviewOutcome | None


@dataclass(frozen=True)
class SyncedPullRequest:
    pull_request: PullRequest
    labels: LabelInfo
    comments: tuple[SyncedComment, ...]


def load_neo4j_config(env: Mapping[str, str] | None = None) -> Neo4jConfig | None:
    """Load Neo4j settings, or None if any required value is missing."""
    if env is None:
        env = os.environ
    uri = env.get(URI_ENV, "").strip()
    username = env.get(USERNAME_ENV, "").strip()
    password = env.get(PASSWORD_ENV, "")
    if not uri or not username or not password:
        return None
    database = env.get(DATABASE_ENV, "").strip() or None
    return Neo4jConfig(uri=uri, username=username, password=password, database=database)


CONSTRAINTS: tuple[LiteralString, ...] = (
    (
        "CREATE CONSTRAINT repository_full_name IF NOT EXISTS "
        "FOR (n:Repository) REQUIRE n.full_name IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT pull_request_github_id IF NOT EXISTS "
        "FOR (n:PullRequest) REQUIRE n.github_id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT comment_github_id IF NOT EXISTS "
        "FOR (n:Comment) REQUIRE n.github_id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT developer_name IF NOT EXISTS "
        "FOR (n:Developer) REQUIRE n.name IS UNIQUE"
    ),
    "CREATE CONSTRAINT label_name IF NOT EXISTS FOR (n:Label) REQUIRE n.name IS UNIQUE",
)

_UPSERT_PULL_REQUEST: LiteralString = """
MERGE (r:Repository {full_name: $repository})
MERGE (p:PullRequest {github_id: $pr.github_id})
SET p.number = $pr.number,
    p.title = $pr.title,
    p.url = $pr.url,
    p.state = $pr.state,
    p.draft = $pr.draft,
    p.created_at = datetime($pr.created_at),
    p.updated_at = datetime($pr.updated_at),
    p.closed_at = datetime($pr.closed_at),
    p.merged_at = datetime($pr.merged_at),
    p.additions = $pr.additions,
    p.deletions = $pr.deletions,
    p.changed_files = $pr.changed_files,
    p.priority = $priority
MERGE (p)-[:IN_REPOSITORY]->(r)
WITH p
// Replace label-derived relationships so relabelling in GitHub is reflected.
OPTIONAL MATCH (p)<-[old:AUTHORED|ASSIGNED_TO_REVIEW]-(:Developer)
DELETE old
WITH DISTINCT p
OPTIONAL MATCH (p)-[old:HAS_LABEL]->(:Label)
DELETE old
WITH DISTINCT p
FOREACH (name IN $labels |
    MERGE (l:Label {name: name})
    MERGE (p)-[:HAS_LABEL]->(l))
FOREACH (name IN CASE WHEN $developer IS NULL THEN [] ELSE [$developer] END |
    MERGE (d:Developer {name: name})
        ON CREATE SET d.picture = toLower(name) + '.png'
    MERGE (d)-[:AUTHORED]->(p))
FOREACH (name IN CASE WHEN $reviewer IS NULL THEN [] ELSE [$reviewer] END |
    MERGE (d:Developer {name: name})
        ON CREATE SET d.picture = toLower(name) + '.png'
    MERGE (d)-[:ASSIGNED_TO_REVIEW]->(p))
"""

_DELETE_REMOVED_COMMENTS: LiteralString = """
MATCH (c:Comment)-[:ON]->(:PullRequest {github_id: $pr_id})
WHERE NOT c.github_id IN $comment_ids
DETACH DELETE c
"""

_UPSERT_COMMENTS: LiteralString = """
MATCH (p:PullRequest {github_id: $pr_id})
UNWIND $comments AS row
MERGE (c:Comment {github_id: row.github_id})
SET c.author = row.author,
    c.body = row.body,
    c.created_at = datetime(row.created_at),
    c.updated_at = datetime(row.updated_at),
    c.outcome = row.outcome
MERGE (c)-[:ON]->(p)
WITH c
// Comments belong to the PR's assigned reviewer, which may have changed.
OPTIONAL MATCH (c)<-[old:WROTE]-(:Developer)
DELETE old
WITH DISTINCT c
FOREACH (name IN CASE WHEN $reviewer IS NULL THEN [] ELSE [$reviewer] END |
    MERGE (d:Developer {name: name})
        ON CREATE SET d.picture = toLower(name) + '.png'
    MERGE (d)-[:WROTE]->(c))
"""


def ensure_constraints(driver: Driver, database: str | None = None) -> None:
    for constraint in CONSTRAINTS:
        driver.execute_query(constraint, database_=database)


def _write_pull_request(
    tx: ManagedTransaction, repository: str, synced: SyncedPullRequest
) -> None:
    pr = synced.pull_request
    tx.run(
        _UPSERT_PULL_REQUEST,
        repository=repository,
        pr=asdict(pr),
        labels=list(pr.labels),
        priority=synced.labels.priority,
        developer=synced.labels.developer,
        reviewer=synced.labels.reviewer,
    )
    comments = [
        {
            **asdict(c.comment),
            "outcome": c.outcome.value if c.outcome else None,
        }
        for c in synced.comments
    ]
    tx.run(
        _DELETE_REMOVED_COMMENTS,
        pr_id=pr.github_id,
        comment_ids=[c["github_id"] for c in comments],
    )
    tx.run(
        _UPSERT_COMMENTS,
        pr_id=pr.github_id,
        comments=comments,
        reviewer=synced.labels.reviewer,
    )


def write_pull_requests(
    driver: Driver,
    repository: str,
    pull_requests: list[SyncedPullRequest],
    database: str | None = None,
) -> None:
    """Write all pull requests in a single transaction (all or nothing)."""

    def work(tx: ManagedTransaction) -> None:
        for synced in pull_requests:
            _write_pull_request(tx, repository, synced)

    with driver.session(database=database) as session:
        session.execute_write(work)
