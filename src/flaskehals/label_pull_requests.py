"""Label open pull requests with their task's developer and a recommended reviewer.

Run with: uv run flaskehals-label

See features/githubsync/pull-request-task-assignment.feature. The application only
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
from dataclasses import dataclass, replace
from functools import partial

from dotenv import load_dotenv
from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.db import DataStoreError, load_neo4j_config, open_driver
from flaskehals.developer_scoring import DeveloperProfile
from flaskehals.github import (
    GitHubClient,
    GitHubError,
    PullRequest,
    RateLimitError,
    load_github_config,
)
from flaskehals.llm_recommendation import Complete, decide_with_llm
from flaskehals.models import Task
from flaskehals.pr_planning import (
    PullRequestPlan,
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
from flaskehals.specification import load_openrouter_config, request_completion
from flaskehals.tasks import fetch_developer_profiles, fetch_tasks

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LabelResult:
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


def _let_llm_decide(
    plan: PullRequestPlan,
    profiles: list[DeveloperProfile],
    complete: Complete | None,
) -> PullRequestPlan:
    """Replace the rule-based reviewer with the model's choice when it gives one.

    The task's developer is excluded, so they can never become the reviewer.
    On any failure the rule-based plan is kept, with a notice saying why.
    """
    assignment = decide_with_llm(
        complete,
        "reviewer",
        profiles,
        plan.task.title,
        plan.task.specification,
        plan.assignment,
        exclude=plan.developer,
    )
    return replace(plan, reviewer=assignment.recommended, assignment=assignment)


def _process(
    client: GitHubClient,
    driver: Driver,
    pr: PullRequest,
    tasks: list[Task],
    profiles: list[DeveloperProfile],
    stored: list[ReviewerRecommendation],
    complete: Complete | None = None,
) -> bool:
    """Handle one pull request. Returns True if it was labelled, False if skipped."""
    plan = plan_pull_request(pr, tasks, profiles)
    if isinstance(plan, Skipped):
        return False
    existing = find_recommendation(stored, plan.task.id, pr.number)
    if existing is not None and existing.labelled:
        return False
    if existing is None:
        plan = _let_llm_decide(plan, profiles, complete)
        save_recommendation(driver, pr, plan)
        developer, reviewer = plan.developer, plan.reviewer
    else:
        # Labelling failed on an earlier run: reuse what was stored.
        developer, reviewer = existing.developer, existing.reviewer
    _apply_labels(client, pr, developer, reviewer)
    mark_labelled(driver, plan.task.id, pr.github_id)
    return True


def label_pull_requests(
    client: GitHubClient, driver: Driver, complete: Complete | None = None
) -> LabelResult:
    """Process every open pull request. Raises if GitHub or Neo4j cannot be read.

    ``complete`` asks the language model to choose the reviewer; without it the
    rule-based recommendation is used.
    """
    # Read everything before changing anything.
    numbers = client.list_pull_request_numbers("open")
    tasks = fetch_tasks(driver)
    profiles = fetch_developer_profiles(driver)
    stored = fetch_recommendations(driver)

    labelled = skipped = failed = 0
    for number in numbers:
        try:
            pr = client.get_pull_request(number)
            if _process(client, driver, pr, tasks, profiles, stored, complete):
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
    return LabelResult(labelled, skipped, failed)


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

    openrouter = load_openrouter_config()
    complete = (
        partial(request_completion, openrouter, purpose="recommendation")
        if openrouter
        else None
    )
    if complete is None:
        logger.warning(
            "OPENROUTER_API_KEY is not set: using the rule-based reviewer ranking."
        )

    try:
        with GitHubClient(github_config) as client, open_driver(neo4j_config) as driver:
            result = label_pull_requests(client, driver, complete)
    except GitHubError as exc:
        logger.error("Could not read pull requests, nothing was changed: %s", exc)
        return 1
    except DataStoreError as exc:
        logger.error("%s Nothing was changed.", exc)
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
