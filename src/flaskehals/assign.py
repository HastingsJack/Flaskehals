"""Label open pull requests with their task's developer and a recommended reviewer.

Run with: uv run flaskehals-assign

features/githubsync/pull-request-task-assignment.feature. The application only
runs locally, so it polls GitHub instead of receiving webhooks. For each open
pull request whose branch names a task (e.g. feat/task-1):

1. the recommendation and reasoning are stored in Neo4j,
2. then the ``dev:`` and ``reviewer:`` labels are written to GitHub,
3. then the recommendation is marked as labelled.

Storing first means a Neo4j failure never leaves a label without a stored
recommendation; marking last means a GitHub failure is retried on the next
run without creating a second recommendation. One failing pull request does
not stop the others, except a GitHub rate limit, which stops the run.
"""

import logging
import sys
from dataclasses import dataclass

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.assignment import DeveloperProfile
from flaskehals.github import (
    GitHubClient,
    GitHubError,
    PullRequest,
    RateLimitError,
    load_github_config,
)
from flaskehals.graph import load_neo4j_config
from flaskehals.pr_assignment import (
    Skipped,
    label_changes,
    plan_pull_request,
)
from flaskehals.reviewer_recommendations import (
    RecommendationSaveError,
    ReviewerRecommendation,
    fetch_recommendations,
    find_recommendation,
    mark_labelled,
    save_recommendation,
)
from flaskehals.tasks import Task, fetch_developer_profiles, fetch_tasks

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssignResult:
    labelled: int = 0
    skipped: int = 0
    failed: int = 0


def _apply_labels(
    client: GitHubClient,
    pr: PullRequest,
    developer: str,
    reviewer: str | None,
) -> None:
    add, remove = label_changes(pr.labels, developer, reviewer)
    for label in remove:
        client.remove_label(pr.number, label)
    client.add_labels(pr.number, add)


def _process(
    client: GitHubClient,
    driver: Driver,
    database: str | None,
    pr: PullRequest,
    tasks: list[Task],
    profiles: list[DeveloperProfile],
    stored: list[ReviewerRecommendation],
) -> bool:
    """Handle one pull request. Returns True if it was labelled, False if skipped."""
    plan = plan_pull_request(pr, tasks, profiles)
    if isinstance(plan, Skipped):
        return False
    existing = find_recommendation(stored, plan.task.id, pr.number)
    if existing is not None and existing.labelled:
        return False
    if existing is None:
        save_recommendation(driver, pr, plan, database)
        developer, reviewer = plan.developer, plan.reviewer
    else:
        # Labelling failed on an earlier run: reuse what was stored.
        developer, reviewer = existing.developer, existing.reviewer
    _apply_labels(client, pr, developer, reviewer)
    mark_labelled(driver, plan.task.id, pr.github_id, database)
    return True


def assign(
    client: GitHubClient, driver: Driver, database: str | None = None
) -> AssignResult:
    """Process every open pull request. Raises if GitHub or Neo4j cannot be read."""
    # Read everything before changing anything.
    numbers = client.list_pull_request_numbers("open")
    tasks = fetch_tasks(driver, database)
    profiles = fetch_developer_profiles(driver, database)
    stored = fetch_recommendations(driver, database)

    labelled = skipped = failed = 0
    for number in numbers:
        try:
            pr = client.get_pull_request(number)
            if _process(client, driver, database, pr, tasks, profiles, stored):
                labelled += 1
            else:
                skipped += 1
        except RateLimitError as exc:
            logger.error("Stopping: %s", exc)
            failed += 1
            break
        except (GitHubError, RecommendationSaveError) as exc:
            logger.error("Pull request #%d failed: %s", number, exc)
            failed += 1
        except (Neo4jError, DriverError) as exc:
            logger.error("Pull request #%d failed writing to Neo4j: %s", number, exc)
            failed += 1
    return AssignResult(labelled, skipped, failed)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    load_dotenv()

    github_config = load_github_config()
    neo4j_config = load_neo4j_config()
    if github_config is None or neo4j_config is None:
        logger.error(
            "Not configured. Set GITHUB_TOKEN (with write access to Issues), "
            "GITHUB_REPOSITORY (owner/name), NEO4J_URI, NEO4J_USERNAME and "
            "NEO4J_PASSWORD."
        )
        return 1

    try:
        with (
            GitHubClient(github_config) as client,
            GraphDatabase.driver(
                neo4j_config.uri, auth=(neo4j_config.username, neo4j_config.password)
            ) as driver,
        ):
            try:
                driver.verify_connectivity()
            except (Neo4jError, DriverError) as exc:
                logger.error(
                    "Cannot connect to Neo4j at %s - is it running? (%s)",
                    neo4j_config.uri,
                    exc,
                )
                return 1
            result = assign(client, driver, neo4j_config.database)
    except GitHubError as exc:
        logger.error("Could not read pull requests, nothing was changed: %s", exc)
        return 1
    except (Neo4jError, DriverError) as exc:
        logger.error("Could not read from Neo4j, nothing was changed: %s", exc)
        return 1

    logger.info(
        "%d labelled, %d skipped, %d failed",
        result.labelled,
        result.skipped,
        result.failed,
    )
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
