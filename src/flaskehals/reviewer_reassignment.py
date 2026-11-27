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

from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.db import UNAVAILABLE_MESSAGE
from flaskehals.github import GitHubClient, GitHubError
from flaskehals.github_labels import change_labels, undo_label_changes
from flaskehals.pr_planning import reviewer_label_changes
from flaskehals.reviewer_recommendations import (
    ReviewerReassignmentError,
    save_reviewer_change,
    validate_reviewer_change,
)


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
        change_labels(client, pr_number, add, remove)
    except GitHubError as exc:
        raise ReviewerReassignmentError(f"GitHub failed: {exc}") from exc

    try:
        save_reviewer_change(driver, task_id, pr_number, new_reviewer, expected_current)
    except (Neo4jError, DriverError) as exc:
        undo_label_changes(client, pr_number, add, remove)
        raise ReviewerReassignmentError(UNAVAILABLE_MESSAGE) from exc
    except ReviewerReassignmentError:
        undo_label_changes(client, pr_number, add, remove)
        raise
