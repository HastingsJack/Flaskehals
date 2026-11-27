"""Developer overview: read-only Neo4j query and picture resolution.

No Streamlit code here, so it can be tested and reused independently.

Workload definitions (see features/developer-dashboard.feature):
- open pull requests: open PRs the developer authored (drafts included)
- review assignments: open PRs the developer is assigned to review
- assigned tasks: approved tasks assigned to the developer, whether or not
  they have a pull request
- merge statistics (see features/dashboard/developer-merge-statistics.feature),
  over rolling windows ending now:
  - authored and merged: PRs the developer authored that were merged
  - commented and merged: merged PRs the developer wrote a comment on, other
    than their own. Comments are attributed to the PR's reviewer label by the
    sync (WROTE), not to the GitHub login, so that relationship is used.
  Each PR is counted once.
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

MERGE_STATS_COLUMNS: LiteralString = """
COUNT { (d)-[:AUTHORED]->(p:PullRequest)
        WHERE p.merged_at >= datetime() - duration({days: 7}) }
    AS authored_merged_7d,
COUNT { (d)-[:AUTHORED]->(p:PullRequest)
        WHERE p.merged_at >= datetime() - duration({days: 30}) }
    AS authored_merged_30d,
COUNT { MATCH (d)-[:WROTE]->(:Comment)-[:ON]->(p:PullRequest)
        WHERE p.merged_at >= datetime() - duration({days: 7})
          AND NOT (d)-[:AUTHORED]->(p)
        RETURN DISTINCT p } AS commented_merged_7d,
COUNT { MATCH (d)-[:WROTE]->(:Comment)-[:ON]->(p:PullRequest)
        WHERE p.merged_at >= datetime() - duration({days: 30})
          AND NOT (d)-[:AUTHORED]->(p)
        RETURN DISTINCT p } AS commented_merged_30d"""

_DEVELOPER_OVERVIEW: LiteralString = f"""
MATCH (d:Developer)
RETURN d.name AS name,
       d.picture AS picture,
       {WORKLOAD_COLUMNS},
       {MERGE_STATS_COLUMNS}
ORDER BY toLower(d.name), d.name
"""


@dataclass(frozen=True)
class MergeStats:
    authored_merged_7d: int = 0
    authored_merged_30d: int = 0
    commented_merged_7d: int = 0
    commented_merged_30d: int = 0


@dataclass(frozen=True)
class DeveloperOverview:
    name: str
    picture: str | None
    open_pull_requests: int
    review_assignments: int
    assigned_tasks: int = 0
    merge_stats: MergeStats = MergeStats()


def fetch_developer_overview(driver: Driver) -> list[DeveloperOverview]:
    """Return every developer with workload counts (zero when no work)."""
    records, _, _ = driver.execute_query(_DEVELOPER_OVERVIEW)
    return [
        DeveloperOverview(
            name=record["name"],
            picture=record["picture"],
            open_pull_requests=record["open_pull_requests"],
            review_assignments=record["review_assignments"],
            assigned_tasks=record["assigned_tasks"],
            merge_stats=MergeStats(
                authored_merged_7d=record["authored_merged_7d"],
                authored_merged_30d=record["authored_merged_30d"],
                commented_merged_7d=record["commented_merged_7d"],
                commented_merged_30d=record["commented_merged_30d"],
            ),
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
