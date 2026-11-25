"""Neo4j storage for reviewer recommendations on a task's pull requests.

No Streamlit code here. Data model:

    (:Task)-[:HAS_PULL_REQUEST]->(:PullRequest)
    (:Task)-[:HAS_REVIEWER_RECOMMENDATION]->(:ReviewerRecommendation)
    (:ReviewerRecommendation)-[:HAS_REASSIGNMENT]->(:ReviewerReassignment)

A recommendation is stored once per (task, pull request). Its reasoning is
never rewritten, so what is shown later is the reasoning at the time. When the
project manager picks a different reviewer (features/tasks/
task-reviewer-reassignment.feature) only ``reviewer`` changes, and a
:ReviewerReassignment records who it changed from and to, and when. Candidates (name,
score and the reasons behind it) are kept as a JSON string because Neo4j
properties cannot hold nested values. ``labelled`` stays false until the
labels have been written to GitHub, so a failed labelling is retried on the
next run without creating a second recommendation.

The :PullRequest node is merged on its GitHub id, the same key the sync uses,
so the link survives whichever of the two runs first.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, LiteralString

from neo4j import Driver, ManagedTransaction

from flaskehals.db import DataStoreError
from flaskehals.developer_scoring import DeveloperScore
from flaskehals.github import PullRequest
from flaskehals.pr_planning import PullRequestPlan

_SAVE: LiteralString = """
MATCH (t:Task {id: $task_id})
MERGE (p:PullRequest {github_id: $github_id})
  ON CREATE SET p.number = $number, p.title = $title, p.url = $url
MERGE (t)-[:HAS_PULL_REQUEST]->(p)
MERGE (r:ReviewerRecommendation {key: $key})
  ON CREATE SET r.task_id = $task_id,
                r.pr_number = $number,
                r.pr_url = $url,
                r.developer = $developer,
                r.reviewer = $reviewer,
                r.notice = $notice,
                r.candidates = $candidates,
                r.created_at = datetime(),
                r.labelled = false
MERGE (t)-[:HAS_REVIEWER_RECOMMENDATION]->(r)
RETURN r.key AS key
"""

_MARK_LABELLED: LiteralString = """
MATCH (r:ReviewerRecommendation {key: $key})
SET r.labelled = true
RETURN r.key AS key
"""

_FETCH: LiteralString = """
MATCH (r:ReviewerRecommendation)
RETURN r.task_id AS task_id,
       r.pr_number AS pr_number,
       r.pr_url AS pr_url,
       r.developer AS developer,
       r.reviewer AS reviewer,
       r.notice AS notice,
       r.candidates AS candidates,
       toString(r.created_at) AS created_at,
       r.labelled AS labelled,
       head([(:Task {id: r.task_id})-[:HAS_PULL_REQUEST]->(p:PullRequest
              {number: r.pr_number}) | p.state]) AS pr_state,
       [(r)-[:HAS_REASSIGNMENT]->(h:ReviewerReassignment) | {
           from_reviewer: h.from_reviewer,
           changed_at: toString(h.changed_at)
       }] AS reassignments
ORDER BY r.created_at, r.key
"""


# What the reviewer change is validated against; read in the same transaction
# as the change so the checks and the change see the same state.
_REVIEWER_STATE: LiteralString = """
MATCH (t:Task {id: $task_id})-[:HAS_REVIEWER_RECOMMENDATION]->
      (r:ReviewerRecommendation {pr_number: $pr_number})
OPTIONAL MATCH (dev:Developer)-[:ASSIGNED_TO]->(t)
OPTIONAL MATCH (target:Developer {name: $new_reviewer})
RETURN r.reviewer AS current, dev.name AS developer, target.name AS target
LIMIT 1
"""

# Also moves the ASSIGNED_TO_REVIEW edge (what the sync derives from the
# reviewer: label), so workload is right before the next sync runs.
_CHANGE_REVIEWER: LiteralString = """
MATCH (t:Task {id: $task_id})-[:HAS_REVIEWER_RECOMMENDATION]->
      (r:ReviewerRecommendation {pr_number: $pr_number})
MATCH (target:Developer {name: $new_reviewer})
CREATE (r)-[:HAS_REASSIGNMENT]->(:ReviewerReassignment {
    from_reviewer: r.reviewer,
    to_reviewer: $new_reviewer,
    changed_at: datetime()
})
SET r.reviewer = $new_reviewer
WITH t, target
MATCH (t)-[:HAS_PULL_REQUEST]->(p:PullRequest {number: $pr_number})
OPTIONAL MATCH (:Developer)-[old:ASSIGNED_TO_REVIEW]->(p)
DELETE old
WITH DISTINCT p, target
MERGE (target)-[:ASSIGNED_TO_REVIEW]->(p)
"""


class RecommendationSaveError(Exception):
    """The recommendation could not be stored. The message is safe to show."""


class ReviewerReassignmentError(DataStoreError):
    """The reviewer could not be changed. The message is safe to show."""


@dataclass(frozen=True)
class PreviousReviewer:
    reviewer: str
    assigned_at: str
    unassigned_at: str


@dataclass(frozen=True)
class ReviewerRecommendation:
    task_id: str
    pr_number: int
    pr_url: str
    developer: str  # the task's developer when the recommendation was made
    reviewer: str | None  # None when no suitable reviewer was found
    notice: str | None
    candidates: tuple[DeveloperScore, ...]  # same type task assignment uses
    created_at: str
    labelled: bool  # labels written to GitHub
    pr_state: str | None = None  # "open"/"closed" as last synced; None if unknown
    # Chronological. ``reviewer`` is the current one; the original
    # recommendation is previous_reviewers[0] when there are any.
    previous_reviewers: tuple[PreviousReviewer, ...] = ()

    @property
    def recommended_reviewer(self) -> str | None:
        """Who the scoring originally recommended, whoever reviews now."""
        if self.previous_reviewers:
            return self.previous_reviewers[0].reviewer
        return self.reviewer


def recommendation_key(task_id: str, github_id: int) -> str:
    return f"{task_id}:{github_id}"


def _encode(plan: PullRequestPlan) -> str:
    return json.dumps(
        [
            {
                "name": score.name,
                "total": round(score.total, 1),
                "explanation": list(score.explanation),
            }
            for score in plan.assignment.scores
        ]
    )


def _decode(text: str | None) -> tuple[DeveloperScore, ...]:
    """Candidates from stored JSON; unreadable data yields no candidates."""
    try:
        items = json.loads(text or "[]")
        return tuple(
            DeveloperScore(
                name=str(item["name"]),
                total=float(item["total"]),
                explanation=tuple(str(line) for line in item["explanation"]),
            )
            for item in items
        )
    except (ValueError, KeyError, TypeError):
        return ()


def save_recommendation(
    driver: Driver,
    pr: PullRequest,
    plan: PullRequestPlan,
) -> None:
    """Store the recommendation and PR link in one transaction.

    Safe to repeat: an existing recommendation for the same task and pull
    request is left unchanged. Raises RecommendationSaveError if the task no
    longer exists. Neo4j errors propagate, and then nothing was stored.
    """
    records, _, _ = driver.execute_query(
        _SAVE,
        task_id=plan.task.id,
        github_id=pr.github_id,
        number=pr.number,
        title=pr.title,
        url=pr.url,
        key=recommendation_key(plan.task.id, pr.github_id),
        developer=plan.developer,
        reviewer=plan.reviewer,
        notice=plan.assignment.notice,
        candidates=_encode(plan),
    )
    if not records:
        raise RecommendationSaveError("The task no longer exists in Neo4j.")


def find_recommendation(
    recommendations: Iterable[ReviewerRecommendation], task_id: str, pr_number: int
) -> ReviewerRecommendation | None:
    """The stored recommendation for this task and pull request number."""
    return next(
        (
            rec
            for rec in recommendations
            if rec.task_id == task_id and rec.pr_number == pr_number
        ),
        None,
    )


def mark_labelled(driver: Driver, task_id: str, github_id: int) -> None:
    """Record that the labels for this recommendation are now on GitHub."""
    driver.execute_query(
        _MARK_LABELLED,
        key=recommendation_key(task_id, github_id),
    )


def _history(
    created_at: str, reassignments: Iterable[dict[str, Any]]
) -> tuple[PreviousReviewer, ...]:
    """Each reviewer who was replaced, with when they were assigned and replaced."""
    changes = sorted(reassignments, key=lambda item: item["changed_at"])
    since = created_at
    previous = []
    for change in changes:
        previous.append(
            PreviousReviewer(change["from_reviewer"] or "", since, change["changed_at"])
        )
        since = change["changed_at"]
    return tuple(previous)


def check_reviewer_change(state: Any, new_reviewer: str, expected_current: str) -> None:
    """Raise ReviewerReassignmentError unless ``new_reviewer`` may take over.

    ``state`` is the row from _REVIEWER_STATE (None if the recommendation is
    gone); ``expected_current`` is the reviewer the caller saw.
    """
    if state is None:
        raise ReviewerReassignmentError(
            "The task or its pull request no longer exists."
        )
    current = state["current"] or ""
    if current != expected_current:
        raise ReviewerReassignmentError(
            f"The reviewer is now {current or 'unassigned'}. Reload and try again."
        )
    if new_reviewer == current:
        raise ReviewerReassignmentError(f"{new_reviewer} is already the reviewer.")
    if new_reviewer == state["developer"]:
        raise ReviewerReassignmentError(
            f"{new_reviewer} is the task's developer and cannot review their own pull request."
        )
    if state["target"] is None:
        raise ReviewerReassignmentError(
            f"Developer '{new_reviewer}' does not exist in Neo4j."
        )


def validate_reviewer_change(
    driver: Driver,
    task_id: str,
    pr_number: int,
    new_reviewer: str,
    expected_current: str,
) -> None:
    """Read-only check, so GitHub is only touched for a change that can be saved."""
    records, _, _ = driver.execute_query(
        _REVIEWER_STATE, task_id=task_id, pr_number=pr_number, new_reviewer=new_reviewer
    )
    check_reviewer_change(
        records[0] if records else None, new_reviewer, expected_current
    )


def save_reviewer_change(
    driver: Driver,
    task_id: str,
    pr_number: int,
    new_reviewer: str,
    expected_current: str,
) -> None:
    """Change the reviewer and record the history in one transaction.

    Re-checks everything in the transaction. Raises ReviewerReassignmentError
    if the change is not allowed any more. Neo4j errors propagate, and then
    nothing was changed.
    """

    def work(tx: ManagedTransaction) -> None:
        state = tx.run(
            _REVIEWER_STATE,
            task_id=task_id,
            pr_number=pr_number,
            new_reviewer=new_reviewer,
        ).single()
        check_reviewer_change(state, new_reviewer, expected_current)
        tx.run(
            _CHANGE_REVIEWER,
            task_id=task_id,
            pr_number=pr_number,
            new_reviewer=new_reviewer,
        )

    with driver.session() as session:
        session.execute_write(work)


def fetch_recommendations(driver: Driver) -> list[ReviewerRecommendation]:
    """All stored recommendations, oldest first."""
    records, _, _ = driver.execute_query(_FETCH)
    return [
        ReviewerRecommendation(
            task_id=record["task_id"],
            pr_number=record["pr_number"],
            pr_url=record["pr_url"] or "",
            developer=record["developer"],
            reviewer=record["reviewer"],
            notice=record["notice"],
            candidates=_decode(record["candidates"]),
            created_at=record["created_at"],
            labelled=bool(record["labelled"]),
            pr_state=record.get("pr_state"),
            previous_reviewers=_history(
                record["created_at"], record.get("reassignments") or []
            ),
        )
        for record in records
    ]
