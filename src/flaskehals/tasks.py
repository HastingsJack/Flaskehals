"""Neo4j access for tasks and the developer profiles used to recommend assignees.

No Streamlit code here. Data model:

    (:Developer)-[:ASSIGNED_TO]->(:Task)     the final assignee
    (:Developer)-[:RECOMMENDED]->(:Task)     the original recommendation

The original recommendation is also kept as ``Task.recommended_developer`` so
it survives even if that developer node is later removed. Tasks are only ever
stored once approved; rejected tasks are never written.
"""

import uuid
from dataclasses import dataclass
from typing import LiteralString

from neo4j import Driver, ManagedTransaction

from flaskehals.assignment import DeveloperProfile
from flaskehals.developers import WORKLOAD_COLUMNS

TASK_CONSTRAINT: LiteralString = (
    "CREATE CONSTRAINT task_id IF NOT EXISTS FOR (n:Task) REQUIRE n.id IS UNIQUE"
)

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
CREATE (t:Task {
    id: $id,
    title: $title,
    description: $description,
    specification: $specification,
    status: 'approved',
    recommended_developer: $recommended_developer,
    created_at: datetime()
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
       t.title AS title,
       t.description AS description,
       t.specification AS specification,
       t.status AS status,
       t.recommended_developer AS recommended_developer,
       a.name AS assigned_developer,
       toString(t.created_at) AS created_at
ORDER BY t.created_at DESC, t.id
"""


class DataStoreError(Exception):
    """Neo4j is missing, unreachable or failed. The message is safe to show."""


class TaskSaveError(DataStoreError):
    """The task could not be saved. The message is safe to show."""


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


def save_approved_task(
    driver: Driver, task: NewTask, database: str | None = None
) -> str:
    """Store an approved task in a single transaction and return its id.

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

    driver.execute_query(TASK_CONSTRAINT, database_=database)
    with driver.session(database=database) as session:
        saved_id = session.execute_write(work)
    if saved_id is None:
        raise TaskSaveError(
            f"Developer '{task.assigned_developer}' no longer exists in Neo4j."
        )
    return saved_id


def fetch_tasks(driver: Driver, database: str | None = None) -> list[Task]:
    """Return all stored tasks, newest first."""
    records, _, _ = driver.execute_query(_FETCH_TASKS, database_=database)
    return [Task(**record.data()) for record in records]
