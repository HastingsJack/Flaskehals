"""Neo4j access for tasks and the developer profiles used to recommend assignees.

No Streamlit code here. Data model:

    (:Developer)-[:ASSIGNED_TO]->(:Task)     the final assignee
    (:Developer)-[:RECOMMENDED]->(:Task)     the original recommendation
    (:Developer)-[:PREVIOUSLY_ASSIGNED_TO {assigned_at, unassigned_at}]->(:Task)
                                             a past assignee, kept after re-assignment

The original recommendation is also kept as ``Task.recommended_developer`` so
it survives even if that developer node is later removed. Tasks are only ever
stored once approved; rejected tasks are never written.
"""

import uuid
from dataclasses import dataclass
from typing import LiteralString

from neo4j import Driver, ManagedTransaction
from neo4j.exceptions import ConstraintError

from flaskehals.assignment import DeveloperProfile
from flaskehals.developers import WORKLOAD_COLUMNS

TASK_CONSTRAINT: LiteralString = (
    "CREATE CONSTRAINT task_id IF NOT EXISTS FOR (n:Task) REQUIRE n.id IS UNIQUE"
)

TASK_NUMBER_CONSTRAINT: LiteralString = "CREATE CONSTRAINT task_number IF NOT EXISTS FOR (n:Task) REQUIRE n.number IS UNIQUE"

# Numbers tasks created before task numbers existed, oldest first, continuing
# after the highest number in use. Repeatable: numbered tasks are never touched.
_BACKFILL_NUMBERS: LiteralString = """
MATCH (t:Task) WHERE t.number IS NULL
WITH t ORDER BY t.created_at, t.id
WITH collect(t) AS missing
OPTIONAL MATCH (n:Task) WHERE n.number IS NOT NULL
WITH missing, coalesce(max(n.number), 0) AS base
UNWIND range(0, size(missing) - 1) AS i
WITH missing[i] AS t, base + i + 1 AS number
SET t.number = number
"""

# Number allocation attempts when concurrent saves collide on the unique number.
_SAVE_ATTEMPTS = 3

# History used for relevance matching: PR titles and technology-like labels
# (the dev:/reviewer:/priority: labels are workflow metadata, not experience)
# plus the title and specification of previously assigned tasks.
_DEVELOPER_PROFILES: LiteralString = f"""
MATCH (d:Developer)
RETURN d.name AS name,
       d.experience_level AS experience_level,
       {WORKLOAD_COLUMNS},
       [(d)-[:AUTHORED|ASSIGNED_TO_REVIEW]->(p:PullRequest) | p.title]
         + [(d)-[:AUTHORED|ASSIGNED_TO_REVIEW]->(:PullRequest)-[:HAS_LABEL]->(l:Label)
              WHERE NOT l.name =~ '(?i)(dev|reviewer|priority):.*' | l.name]
         + [(d)-[:ASSIGNED_TO]->(t:Task) | t.title + ' ' + t.specification]
         AS history
ORDER BY toLower(d.name), d.name
"""

_SAVE_TASK: LiteralString = """
MATCH (assignee:Developer {name: $assigned_developer})
OPTIONAL MATCH (existing:Task)
WITH assignee, coalesce(max(existing.number), 0) + 1 AS number
CREATE (t:Task {
    id: $id,
    number: number,
    title: $title,
    description: $description,
    specification: $specification,
    status: 'approved',
    recommended_developer: $recommended_developer,
    created_at: datetime(),
    assigned_at: datetime()
})
CREATE (assignee)-[:ASSIGNED_TO]->(t)
WITH t
OPTIONAL MATCH (recommended:Developer {name: $recommended_developer})
FOREACH (_ IN CASE WHEN recommended IS NULL THEN [] ELSE [1] END |
    CREATE (recommended)-[:RECOMMENDED]->(t))
RETURN t.id AS id
"""

_FETCH_TASKS: LiteralString = """
MATCH (t:Task)
OPTIONAL MATCH (a:Developer)-[:ASSIGNED_TO]->(t)
RETURN t.id AS id,
       t.number AS number,
       t.title AS title,
       t.description AS description,
       t.specification AS specification,
       t.status AS status,
       t.recommended_developer AS recommended_developer,
       a.name AS assigned_developer,
       toString(t.created_at) AS created_at,
       [(p:Developer)-[r:PREVIOUSLY_ASSIGNED_TO]->(t) | {
           developer: p.name,
           assigned_at: toString(r.assigned_at),
           unassigned_at: toString(r.unassigned_at)
       }] AS previous_assignments
ORDER BY t.created_at DESC, t.id
"""

# Current assignee and the chosen developer, read inside the write transaction
# so the checks and the change see the same state.
_REASSIGN_STATE: LiteralString = """
MATCH (t:Task {id: $task_id})
OPTIONAL MATCH (current:Developer)-[:ASSIGNED_TO]->(t)
OPTIONAL MATCH (target:Developer {name: $new_developer})
RETURN current.name AS current, target.name AS target
"""

# The old assignment becomes a PREVIOUSLY_ASSIGNED_TO edge, so history is kept
# and workload (which only counts ASSIGNED_TO) moves to the new developer.
_REASSIGN: LiteralString = """
MATCH (t:Task {id: $task_id})
MATCH (old:Developer)-[current:ASSIGNED_TO]->(t)
MATCH (target:Developer {name: $new_developer})
WITH t, old, current, target, datetime() AS now,
     coalesce(t.assigned_at, t.created_at) AS since
DELETE current
CREATE (old)-[:PREVIOUSLY_ASSIGNED_TO {assigned_at: since, unassigned_at: now}]->(t)
CREATE (target)-[:ASSIGNED_TO]->(t)
SET t.assigned_at = now
"""


class DataStoreError(Exception):
    """Neo4j is missing, unreachable or failed. The message is safe to show."""


class TaskSaveError(DataStoreError):
    """The task could not be saved. The message is safe to show."""


class ReassignmentError(DataStoreError):
    """The task could not be re-assigned. The message is safe to show."""


@dataclass(frozen=True)
class PreviousAssignment:
    developer: str
    assigned_at: str
    unassigned_at: str


@dataclass(frozen=True)
class NewTask:
    title: str
    description: str  # the project manager's original description
    specification: str  # the approved (possibly edited) specification
    assigned_developer: str  # final assignee
    recommended_developer: str | None  # original recommendation, if any


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    description: str
    specification: str
    status: str
    recommended_developer: str | None
    assigned_developer: str | None
    created_at: str
    previous_assignments: tuple[PreviousAssignment, ...] = ()
    number: int | None = None  # global, shown as "Task-N"


def fetch_developer_profiles(
    driver: Driver, database: str | None = None
) -> list[DeveloperProfile]:
    """Return every developer with workload, experience level and history."""
    records, _, _ = driver.execute_query(_DEVELOPER_PROFILES, database_=database)
    return [
        DeveloperProfile(
            name=record["name"],
            open_pull_requests=record["open_pull_requests"],
            review_assignments=record["review_assignments"],
            assigned_tasks=record["assigned_tasks"],
            experience_level=record["experience_level"],
            history_texts=tuple(
                text for text in record["history"] if isinstance(text, str)
            ),
        )
        for record in records
    ]


def _prepare_numbering(driver: Driver, database: str | None) -> None:
    """Create the constraints and number any task that has no number yet."""
    driver.execute_query(TASK_CONSTRAINT, database_=database)
    driver.execute_query(TASK_NUMBER_CONSTRAINT, database_=database)
    try:
        driver.execute_query(_BACKFILL_NUMBERS, database_=database)
    except ConstraintError:
        pass  # another session numbered the same tasks first


def save_approved_task(
    driver: Driver, task: NewTask, database: str | None = None
) -> str:
    """Store an approved task in a single transaction and return its id.

    The task gets the next task number in the same transaction, so a failed
    save uses no number. If a concurrent save took the number first, the unique
    constraint rejects this one and the save is retried with a fresh number.
    Raises TaskSaveError if the assigned developer does not exist. Neo4j
    errors propagate to the caller.
    """
    task_id = str(uuid.uuid4())

    def work(tx: ManagedTransaction) -> str | None:
        record = tx.run(
            _SAVE_TASK,
            id=task_id,
            title=task.title,
            description=task.description,
            specification=task.specification,
            assigned_developer=task.assigned_developer,
            recommended_developer=task.recommended_developer,
        ).single()
        return None if record is None else record["id"]

    _prepare_numbering(driver, database)
    saved_id: str | None = None
    with driver.session(database=database) as session:
        for attempt in range(_SAVE_ATTEMPTS):
            try:
                saved_id = session.execute_write(work)
                break
            except ConstraintError:
                if attempt == _SAVE_ATTEMPTS - 1:
                    raise
    if saved_id is None:
        raise TaskSaveError(
            f"Developer '{task.assigned_developer}' no longer exists in Neo4j."
        )
    return saved_id


def fetch_tasks(driver: Driver, database: str | None = None) -> list[Task]:
    """Return all stored tasks, newest first.

    Tasks created before task numbers existed are numbered first.
    """
    _prepare_numbering(driver, database)
    records, _, _ = driver.execute_query(_FETCH_TASKS, database_=database)
    tasks = []
    for record in records:
        data = record.data()
        previous = sorted(
            (
                PreviousAssignment(**item)
                for item in data.pop("previous_assignments", [])
            ),
            key=lambda item: item.unassigned_at,
        )
        tasks.append(Task(**data, previous_assignments=tuple(previous)))
    return tasks


def reassign_task(
    driver: Driver,
    task_id: str,
    new_developer: str,
    expected_current: str | None,
    database: str | None = None,
) -> None:
    """Move a task to another developer in a single transaction.

    ``expected_current`` is the assignee the caller saw; if the task has since
    moved, nothing is changed. Raises ReassignmentError for an unknown task or
    developer, an unchanged assignee or a stale view. Neo4j errors propagate,
    and then nothing was changed.
    """

    def work(tx: ManagedTransaction) -> None:
        state = tx.run(
            _REASSIGN_STATE, task_id=task_id, new_developer=new_developer
        ).single()
        if state is None:
            raise ReassignmentError("The task no longer exists.")
        if state["current"] is None:
            raise ReassignmentError("The task has no current assignee to replace.")
        if state["current"] != expected_current:
            raise ReassignmentError(
                f"The task is now assigned to {state['current']}. Reload and try again."
            )
        if state["current"] == new_developer:
            raise ReassignmentError(
                f"{new_developer} is already assigned to this task."
            )
        if state["target"] is None:
            raise ReassignmentError(
                f"Developer '{new_developer}' no longer exists in Neo4j."
            )
        tx.run(_REASSIGN, task_id=task_id, new_developer=new_developer)

    with driver.session(database=database) as session:
        session.execute_write(work)
