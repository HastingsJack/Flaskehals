"""Validation of the text the project manager types when creating a task.

Pure functions with no Streamlit and no I/O. Each returns a message that is
safe to show, or None when the input is valid.
"""

MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 10_000
MAX_FEEDBACK_LENGTH = 5_000


def validate_task_input(title: str, description: str) -> str | None:
    """Return a user-facing problem with the task text, or None if valid."""
    if not title.strip():
        return "Enter a task title."
    if not description.strip():
        return "Enter a task description."
    if len(title) > MAX_TITLE_LENGTH:
        return f"The title must be at most {MAX_TITLE_LENGTH} characters."
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return f"The description must be at most {MAX_DESCRIPTION_LENGTH} characters."
    return None


def validate_feedback(feedback: str) -> str | None:
    if len(feedback) > MAX_FEEDBACK_LENGTH:
        return f"The feedback must be at most {MAX_FEEDBACK_LENGTH} characters."
    return None
