"""Re-assign a task and keep the ``dev:`` label of its pull requests in step.

No Streamlit code here. See features/tasks/task-reassignment-github-labels.feature.
The application calls the GitHub API when the project manager confirms; no
webhook is involved (the application only runs locally).

Order of the steps, and why (the same as for a reviewer change):

1. Check in Neo4j that the change is allowed (read-only), so GitHub is only
   touched for a change that can be saved.
2. Change the ``dev:`` label of every open pull request of the task on GitHub.
   Only that label is touched. If one fails, the ones already changed are
   restored.
3. Save the new developer and the pull requests' author in one Neo4j
   transaction. If that fails, the labels are restored on a best-effort basis.

If a restore fails, the next sync reads the label from GitHub back into the
graph.
"""

from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.db import UNAVAILABLE_MESSAGE, DataStoreError
from flaskehals.github import GitHubClient, GitHubError
from flaskehals.github_labels import Labels, change_labels, undo_label_changes
from flaskehals.pr_planning import developer_label_changes
from flaskehals.tasks import (
    fetch_open_pull_request_numbers,
    reassign_task,
    validate_reassignment,
)


def _restore(client: GitHubClient, changed: list[tuple[int, Labels, Labels]]) -> None:
    for number, add, remove in changed:
        undo_label_changes(client, number, add, remove)


def reassign_task_and_labels(
    driver: Driver,
    client: GitHubClient,
    task_id: str,
    new_developer: str,
    expected_current: str | None,
) -> None:
    """Move the task and the ``dev:`` label of its open pull requests.

    Raises DataStoreError, whose message is safe to show, and then the task and
    the labels are as they were.
    """
    try:
        validate_reassignment(driver, task_id, new_developer, expected_current)
        numbers = fetch_open_pull_request_numbers(driver, task_id)
    except (Neo4jError, DriverError) as exc:
        raise DataStoreError(UNAVAILABLE_MESSAGE) from exc

    changed: list[tuple[int, Labels, Labels]] = []
    open_numbers: list[int] = []
    try:
        for number in numbers:
            pr = client.get_pull_request(number)
            if pr.state != "open":
                continue
            open_numbers.append(number)
            add, remove = developer_label_changes(pr.labels, new_developer)
            change_labels(client, number, add, remove)
            changed.append((number, add, remove))
    except GitHubError as exc:
        _restore(client, changed)
        raise DataStoreError(f"GitHub failed: {exc}") from exc

    try:
        reassign_task(driver, task_id, new_developer, expected_current, open_numbers)
    except (Neo4jError, DriverError) as exc:
        _restore(client, changed)
        raise DataStoreError(UNAVAILABLE_MESSAGE) from exc
    except DataStoreError:
        _restore(client, changed)
        raise
