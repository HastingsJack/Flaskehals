import logging

from flaskehals.github import GitHubClient, GitHubError

logger = logging.getLogger(__name__)

Labels = tuple[str, ...]


def undo_label_changes(
    client: GitHubClient, number: int, add: Labels, remove: Labels
) -> None:
    """Put the labels back. Never raises: the original error is the one to report."""
    try:
        for label in add:
            client.remove_label(number, label)
        client.add_labels(number, remove)
    except GitHubError as exc:
        logger.error("Could not restore the labels on #%d: %s", number, exc)


def change_labels(
    client: GitHubClient, number: int, add: Labels, remove: Labels
) -> None:
    """Add first, so a failure never leaves the pull request without a reviewer."""
    try:
        client.add_labels(number, add)
        for label in remove:
            client.remove_label(number, label)
    except GitHubError:
        undo_label_changes(client, number, add, remove)
        raise
