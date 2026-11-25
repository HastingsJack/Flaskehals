"""Task search (features/tasks/task-search.feature).

Pure functions, no Streamlit or Neo4j. Tasks are filtered in memory after they
are loaded, so the search text never reaches a database query.
"""

from collections.abc import Sequence

from flaskehals.models import Task
from flaskehals.task_numbers import parse_number_query

MAX_QUERY_LENGTH = 100


def validate_query(query: str) -> str | None:
    """Return a message safe to show if the query is unusable, else None."""
    if len(query.strip()) > MAX_QUERY_LENGTH:
        return f"Search must be at most {MAX_QUERY_LENGTH} characters."
    if any(not char.isprintable() for char in query):
        return "Search contains characters that are not allowed."
    return None


def search_tasks(tasks: Sequence[Task], query: str) -> list[Task]:
    """Tasks matching the query, in their original order.

    ``Task-7``, ``task-7`` or ``7`` match the task with exactly that number
    (so ``1`` never finds ``Task-12``). Anything else matches tasks whose title
    or assigned developer contains it, case-insensitively. Surrounding
    whitespace is ignored and an empty query matches every task.
    """
    number = parse_number_query(query)
    if number is not None:
        return [task for task in tasks if task.number == number]
    needle = query.strip().casefold()
    if not needle:
        return list(tasks)
    return [
        task
        for task in tasks
        if needle in task.title.casefold()
        or needle in (task.assigned_developer or "").casefold()
    ]
