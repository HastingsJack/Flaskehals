"""Change the reviewer of a task's pull request, in GitHub and in Neo4j.

No Streamlit code here. See features/tasks/task-reviewer-reassignment.feature.

Order of the steps, and why:

1. Check in Neo4j that the change is allowed (read-only), so GitHub is only
   touched for a change that can be saved.
2. Read the pull request from GitHub: it must still be open, and its current
   labels decide what to add and remove.
3. Change the ``reviewer:`` label on GitHub. Only that label is touched.
4. Save the new reviewer and the history in Neo4j.

If step 4 fails, step 3 is undone on a best-effort basis. GitHub and Neo4j
cannot share a transaction, and both failing in a row is rare. If the undo
itself fails, the next sync reads the label from GitHub back into the graph.
"""

import logging

from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.db import UNAVAILABLE_MESSAGE
from flaskehals.github import GitHubClient, GitHubError
from flaskehals.pr_planning import reviewer_label_changes
from flaskehals.reviewer_recommendations import (
    ReviewerReassignmentError,
    save_reviewer_change,
    validate_reviewer_change,
)

logger = logging.getLogger(__name__)

Labels = tuple[str, ...]


def _undo(client: GitHubClient, number: int, add: Labels, remove: Labels) -> None:
    """Put the labels back. Never raises: the original error is the one to report."""
    try:
        for label in add:
            client.remove_label(number, label)
        client.add_labels(number, remove)
    except GitHubError as exc:
        logger.error("Could not restore the labels on #%d: %s", number, exc)


def _change_labels(
    client: GitHubClient, number: int, add: Labels, remove: Labels
) -> None:
    """Add first, so a failure never leaves the pull request without a reviewer."""
    try:
        client.add_labels(number, add)
        for label in remove:
            client.remove_label(number, label)
    except GitHubError:
        _undo(client, number, add, remove)
        raise


def reassign_reviewer(
    driver: Driver,
    client: GitHubClient,
    task_id: str,
    pr_number: int,
    new_reviewer: str,
    expected_current: str,
) -> None:
    """Make ``new_reviewer`` the reviewer, or raise and leave the reviewer as it was.

    ``expected_current`` is the reviewer the caller saw; if it has changed
    since, nothing is changed. Raises ReviewerReassignmentError, whose message
    is safe to show.
    """
    try:
        validate_reviewer_change(
            driver, task_id, pr_number, new_reviewer, expected_current
        )
    except (Neo4jError, DriverError) as exc:
        raise ReviewerReassignmentError(UNAVAILABLE_MESSAGE) from exc

    try:
        pr = client.get_pull_request(pr_number)
        if pr.state != "open":
            raise ReviewerReassignmentError("The pull request is not open any more.")
        add, remove = reviewer_label_changes(pr.labels, new_reviewer)
        _change_labels(client, pr_number, add, remove)
    except GitHubError as exc:
        raise ReviewerReassignmentError(f"GitHub failed: {exc}") from exc

    try:
        save_reviewer_change(driver, task_id, pr_number, new_reviewer, expected_current)
    except (Neo4jError, DriverError) as exc:
        _undo(client, pr_number, add, remove)
        raise ReviewerReassignmentError(UNAVAILABLE_MESSAGE) from exc
    except ReviewerReassignmentError:
        _undo(client, pr_number, add, remove)
        raise
