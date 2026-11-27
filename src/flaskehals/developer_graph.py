"""The nodes and relationships around one developer, read from Neo4j.

No Streamlit code here. The query's LIMIT bounds the graph, which is rendered
in the browser.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, LiteralString

from neo4j import Driver

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
    return value if isinstance(value, str | int | float | bool) else str(value)


def _to_node(raw: Mapping[str, Any]) -> GraphNode:
    return GraphNode(
        id=raw["id"],
        labels=tuple(raw["labels"]),
        properties={k: _property_value(v) for k, v in raw["properties"].items()},
    )


def _to_edge(raw: Mapping[str, Any]) -> GraphEdge:
    return GraphEdge(raw["id"], raw["type"], raw["source"], raw["target"])


def fetch_developer_graph(driver: Driver, name: str) -> DeveloperGraph | None:
    """Return the developer's node and surrounding graph, or None if unknown."""
    records, _, _ = driver.execute_query(_DEVELOPER_GRAPH, name=name)
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
