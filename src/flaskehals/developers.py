"""Developer overview: read-only Neo4j queries and picture resolution.

No Streamlit code here, so it can be tested and reused independently.

Workload definitions (see features/developer-dashboard.feature):
- open pull requests: open PRs the developer authored (drafts included)
- review assignments: open PRs the developer is assigned to review
- assigned tasks: approved tasks assigned to the developer, whether or not
  they have a pull request
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, LiteralString

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


# --- Graph details (nodes and relationships around one developer) -----------

# The query's LIMIT bounds the graph, which is rendered in the browser.

# The developer's direct neighbours (RECOMMENDED is deliberately left out), plus the labels of any pull request
# among them (two hops, following only HAS_LABEL).
_DEVELOPER_GRAPH: LiteralString = """
MATCH (d:Developer {name: $name})
OPTIONAL MATCH (d)-[r1:AUTHORED|ASSIGNED_TO_REVIEW|ASSIGNED_TO]-(n1)
OPTIONAL MATCH (n1:PullRequest)-[r2:HAS_LABEL]->(n2)
RETURN {id: elementId(d), labels: labels(d), properties: properties(d)} AS developer,
       CASE WHEN r1 IS NULL THEN NULL ELSE {
           id: elementId(r1), type: type(r1),
           source: elementId(startNode(r1)), target: elementId(endNode(r1))
       } END AS edge1,
       CASE WHEN n1 IS NULL THEN NULL ELSE {
           id: elementId(n1), labels: labels(n1), properties: properties(n1)
       } END AS node1,
       CASE WHEN r2 IS NULL THEN NULL ELSE {
           id: elementId(r2), type: type(r2),
           source: elementId(startNode(r2)), target: elementId(endNode(r2))
       } END AS edge2,
       CASE WHEN n2 IS NULL THEN NULL ELSE {
           id: elementId(n2), labels: labels(n2), properties: properties(n2)
       } END AS node2
LIMIT 500
"""


@dataclass(frozen=True)
class GraphNode:
    id: str
    labels: tuple[str, ...]
    properties: Mapping[str, str | int | float | bool]


@dataclass(frozen=True)
class GraphEdge:
    id: str
    type: str
    source: str  # node id; the arrow points source -> target
    target: str


@dataclass(frozen=True)
class DeveloperGraph:
    developer_id: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    def relationship_counts(self) -> dict[str, int]:
        """Connected nodes per relationship type, direct neighbours only."""
        direct = Counter(
            edge.type
            for edge in self.edges
            if self.developer_id in (edge.source, edge.target)
        )
        return dict(sorted(direct.items()))


def _property_value(value: Any) -> str | int | float | bool:
    # Dates and other driver types are shown as text.
    return value if isinstance(value, str | int | float | bool) else str(value)


def _to_node(raw: Mapping[str, Any]) -> GraphNode:
    return GraphNode(
        id=raw["id"],
        labels=tuple(raw["labels"]),
        properties={k: _property_value(v) for k, v in raw["properties"].items()},
    )


def _to_edge(raw: Mapping[str, Any]) -> GraphEdge:
    return GraphEdge(raw["id"], raw["type"], raw["source"], raw["target"])


def fetch_developer_graph(
    driver: Driver, name: str, database: str | None = None
) -> DeveloperGraph | None:
    """Return the developer's node and surrounding graph, or None if unknown."""
    records, _, _ = driver.execute_query(
        _DEVELOPER_GRAPH, name=name, database_=database
    )
    if not records:
        return None
    nodes: dict[str, GraphNode] = {}
    edges: dict[str, GraphEdge] = {}
    developer = _to_node(records[0]["developer"])
    nodes[developer.id] = developer
    for record in records:
        for node_key in ("node1", "node2"):
            if record[node_key] is not None:
                node = _to_node(record[node_key])
                nodes[node.id] = node
        for edge_key in ("edge1", "edge2"):
            if record[edge_key] is not None:
                edge = _to_edge(record[edge_key])
                edges[edge.id] = edge
    return DeveloperGraph(developer.id, tuple(nodes.values()), tuple(edges.values()))
