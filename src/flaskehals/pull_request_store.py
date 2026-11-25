"""Neo4j storage for synchronised pull request data.

All writes use MERGE on GitHub IDs (or names) so repeated syncs update
existing nodes instead of creating duplicates. Relationships derived from
labels are replaced on each sync, so GitHub stays the source of truth.
"""

from dataclasses import asdict, dataclass
from typing import LiteralString

from neo4j import Driver, ManagedTransaction

from flaskehals.github import Comment, PullRequest
from flaskehals.interpretation import LabelInfo, ReviewOutcome


@dataclass(frozen=True)
class SyncedComment:
    comment: Comment
    outcome: ReviewOutcome | None


@dataclass(frozen=True)
class SyncedPullRequest:
    pull_request: PullRequest
    labels: LabelInfo
    comments: tuple[SyncedComment, ...]


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
) -> None:
    """Write all pull requests in a single transaction (all or nothing)."""

    def work(tx: ManagedTransaction) -> None:
        for synced in pull_requests:
            _write_pull_request(tx, repository, synced)

    with driver.session() as session:
        session.execute_write(work)
