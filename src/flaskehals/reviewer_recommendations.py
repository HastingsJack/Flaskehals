"""Neo4j storage for reviewer recommendations on a task's pull requests.

No Streamlit code here. Data model:

    (:Task)-[:HAS_PULL_REQUEST]->(:PullRequest)
    (:Task)-[:HAS_REVIEWER_RECOMMENDATION]->(:ReviewerRecommendation)

A recommendation is stored once per (task, pull request) and then left alone,
so the reasoning shown later is the reasoning at the time. Candidates (name,
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
from typing import LiteralString

from neo4j import Driver

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
       r.labelled AS labelled
ORDER BY r.created_at, r.key
"""


class RecommendationSaveError(Exception):
    """The recommendation could not be stored. The message is safe to show."""


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
        )
        for record in records
    ]
