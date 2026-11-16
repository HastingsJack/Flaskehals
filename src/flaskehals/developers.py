"""Developer overview: read-only Neo4j queries and picture resolution.

No Streamlit code here, so it can be tested and reused independently.

Workload definitions (see features/developer-dashboard.feature):
- open pull requests: open PRs the developer authored (drafts included)
- review assignments: open PRs the developer is assigned to review
- assigned tasks: approved tasks assigned to the developer, whether or not
  they have a pull request
"""

from dataclasses import dataclass
from pathlib import Path
from typing import LiteralString

from neo4j import Driver

ASSETS_DIR = Path(__file__).parents[2] / "assets"
DEVELOPER_PICTURES_DIR = ASSETS_DIR / "developers"
DEFAULT_AVATAR = ASSETS_DIR / "default_avatar.svg"

WORKLOAD_COLUMNS: LiteralString = """
COUNT { (d)-[:AUTHORED]->(:PullRequest {state: 'open'}) } AS open_pull_requests,
       COUNT { (d)-[:ASSIGNED_TO_REVIEW]->(:PullRequest {state: 'open'}) }
           AS review_assignments,
       COUNT { (d)-[:ASSIGNED_TO]->(:Task {status: 'approved'}) } AS assigned_tasks"""

_DEVELOPER_OVERVIEW: LiteralString = f"""
MATCH (d:Developer)
RETURN d.name AS name,
       d.picture AS picture,
       {WORKLOAD_COLUMNS}
ORDER BY toLower(d.name), d.name
"""


@dataclass(frozen=True)
class DeveloperOverview:
    name: str
    picture: str | None
    open_pull_requests: int
    review_assignments: int
    assigned_tasks: int = 0


def fetch_developer_overview(
    driver: Driver, database: str | None = None
) -> list[DeveloperOverview]:
    """Return every developer with workload counts (zero when no work)."""
    records, _, _ = driver.execute_query(_DEVELOPER_OVERVIEW, database_=database)
    return [
        DeveloperOverview(
            name=record["name"],
            picture=record["picture"],
            open_pull_requests=record["open_pull_requests"],
            review_assignments=record["review_assignments"],
            assigned_tasks=record["assigned_tasks"],
        )
        for record in records
    ]


def resolve_picture(picture: str | None, pictures_dir: Path | None = None) -> Path:
    """Return the developer's picture file, or the default avatar.

    ``picture`` comes from the database, so it is treated as untrusted: only a
    bare filename of an existing file inside ``pictures_dir`` is accepted.
    """
    directory = DEVELOPER_PICTURES_DIR if pictures_dir is None else pictures_dir
    if not picture or picture != Path(picture).name or picture in {".", ".."}:
        return DEFAULT_AVATAR
    candidate = directory / picture
    return candidate if candidate.is_file() else DEFAULT_AVATAR
