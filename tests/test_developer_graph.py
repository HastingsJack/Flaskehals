"""Tests for features/dashboard/developer-graph-details.feature."""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from conftest import TEST_PASSWORD, TEST_USERNAME
from neo4j.exceptions import ServiceUnavailable
from streamlit.testing.v1 import AppTest

from flaskehals.developer_graph import (
    DeveloperGraph,
    GraphEdge,
    GraphNode,
    fetch_developer_graph,
)
from flaskehals.developers import DeveloperOverview
from flaskehals.graph_view import (
    FALLBACK_COLOR,
    build_agraph,
    graph_legend,
    label_color,
    node_caption,
)

APP_PATH = str(Path(__file__).parents[1] / "src" / "flaskehals" / "app.py")

pytestmark = pytest.mark.usefixtures("auth_env", "neo4j_env")

HANS = GraphNode("d1", ("Developer",), {"name": "Hans"})
PR = GraphNode(
    "p1", ("PullRequest",), {"number": 7, "title": "Fix login", "state": "open"}
)
REVIEW_PR = GraphNode("p2", ("PullRequest",), {"number": 8, "title": "Add API"})
TASK = GraphNode("t1", ("Task",), {"title": "Write docs", "status": "approved"})
LABEL = GraphNode("l1", ("Label",), {"name": "bug"})
LABEL2 = GraphNode("l2", ("Label",), {"name": "ui"})

FULL_GRAPH = DeveloperGraph(
    "d1",
    (HANS, PR, REVIEW_PR, TASK, LABEL),
    (
        GraphEdge("e1", "AUTHORED", "d1", "p1"),
        GraphEdge("e2", "ASSIGNED_TO_REVIEW", "d1", "p2"),
        GraphEdge("e3", "ASSIGNED_TO", "d1", "t1"),
        GraphEdge("e4", "HAS_LABEL", "p1", "l1"),
    ),
)
LONELY_GRAPH = DeveloperGraph("d9", (GraphNode("d9", ("Developer",), {}),), ())


# --- data layer ---------------------------------------------------------


def node_map(node: GraphNode) -> dict[str, object]:
    return {"id": node.id, "labels": list(node.labels), "properties": node.properties}


def edge_map(edge: GraphEdge) -> dict[str, str]:
    return {
        "id": edge.id,
        "type": edge.type,
        "source": edge.source,
        "target": edge.target,
    }


def test_fetch_builds_graph_and_deduplicates_shared_nodes() -> None:
    driver = MagicMock()
    # Two rows share the same developer, PR and edge (two labels on one PR).
    row_bug = {
        "developer": node_map(HANS),
        "edge1": edge_map(FULL_GRAPH.edges[0]),
        "node1": node_map(PR),
        "edge2": edge_map(FULL_GRAPH.edges[3]),
        "node2": node_map(LABEL),
    }
    row_second = {
        **row_bug,
        "edge2": edge_map(GraphEdge("e5", "HAS_LABEL", "p1", "l2")),
        "node2": node_map(LABEL2),
    }
    driver.execute_query.return_value = ([row_bug, row_second], None, None)
    graph = fetch_developer_graph(driver, "Hans")
    assert graph is not None
    assert {n.id for n in graph.nodes} == {"d1", "p1", "l1", "l2"}
    assert {e.id for e in graph.edges} == {"e1", "e4", "e5"}
    assert graph.developer_id == "d1"
    assert driver.execute_query.call_args.kwargs == {"name": "Hans"}


def test_fetch_developer_without_relationships_returns_only_the_developer() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = (
        [
            {
                "developer": node_map(HANS),
                "edge1": None,
                "node1": None,
                "edge2": None,
                "node2": None,
            }
        ],
        None,
        None,
    )
    graph = fetch_developer_graph(driver, "Hans")
    assert graph is not None
    assert [n.id for n in graph.nodes] == ["d1"]
    assert graph.edges == ()
    assert graph.relationship_counts() == {}


def test_fetch_unknown_developer_returns_none() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)
    assert fetch_developer_graph(driver, "Nobody") is None


def test_fetch_converts_driver_types_to_text() -> None:
    driver = MagicMock()
    created = object()
    raw = {"id": "d1", "labels": ["Developer"], "properties": {"since": created}}
    driver.execute_query.return_value = (
        [
            {
                "developer": raw,
                "edge1": None,
                "node1": None,
                "edge2": None,
                "node2": None,
            }
        ],
        None,
        None,
    )
    graph = fetch_developer_graph(driver, "Hans")
    assert graph is not None
    assert graph.nodes[0].properties == {"since": str(created)}


def test_graph_query_is_read_only_and_parameterised() -> None:
    driver = MagicMock()
    driver.execute_query.return_value = ([], None, None)
    fetch_developer_graph(driver, "Hans")
    query = driver.execute_query.call_args.args[0]
    assert "$name" in query
    assert "RECOMMENDED" not in query
    assert "Hans" not in query
    assert not any(w in query for w in ("CREATE", "MERGE", "SET ", "DELETE"))


def test_relationship_counts_only_include_direct_relationships() -> None:
    assert FULL_GRAPH.relationship_counts() == {
        "ASSIGNED_TO": 1,
        "ASSIGNED_TO_REVIEW": 1,
        "AUTHORED": 1,
    }


def test_graph_counts_match_dashboard_workload_counts() -> None:
    """Open authored PRs, review PRs and tasks in the graph equal the row counts."""
    overview = DeveloperOverview("Hans", None, 1, 1, 1)
    by_id = {n.id: n for n in FULL_GRAPH.nodes}
    counts = FULL_GRAPH.relationship_counts()
    assert counts["AUTHORED"] == overview.open_pull_requests
    assert counts["ASSIGNED_TO_REVIEW"] == overview.review_assignments
    assert counts["ASSIGNED_TO"] == overview.assigned_tasks
    assert by_id["p1"].properties["state"] == "open"
    assert by_id["t1"].properties["status"] == "approved"


# --- graph view ---------------------------------------------------------


def test_nodes_with_same_label_share_colour_and_labels_differ() -> None:
    assert label_color("PullRequest") == label_color("PullRequest")
    colours = {label_color(n.labels[0]) for n in FULL_GRAPH.nodes}
    assert len(colours) == 4
    assert label_color("Unknown") == FALLBACK_COLOR


def test_node_captions_use_name_or_title() -> None:
    assert node_caption(HANS) == "Hans"
    assert node_caption(PR) == "#7 Fix login"
    assert node_caption(LABEL) == "bug"
    assert node_caption(GraphNode("x", ("Thing",), {})) == "Thing"
    long = GraphNode("y", ("Task",), {"title": "x" * 100})
    assert len(node_caption(long)) <= 24


def test_agraph_has_labelled_directed_edges_and_larger_developer() -> None:
    nodes, edges, config = build_agraph(FULL_GRAPH)
    assert not hasattr(config, "edges")  # arrowheads not disabled: directed
    assert {e.__dict__["label"] for e in edges} == {
        "AUTHORED",
        "ASSIGNED_TO_REVIEW",
        "ASSIGNED_TO",
        "HAS_LABEL",
    }
    sizes = {n.id: n.size for n in nodes}
    assert sizes["d1"] > sizes["p1"]


def test_legend_lists_labels_and_relationship_types() -> None:
    labels, types = graph_legend(FULL_GRAPH)
    assert labels == ["Developer", "Label", "PullRequest", "Task"]
    assert "HAS_LABEL" in types and "AUTHORED" in types


# --- dashboard UI -------------------------------------------------------

PEOPLE = [
    DeveloperOverview("Hans", None, 1, 1, 1),
    DeveloperOverview("Lonely", None, 0, 0, 0),
]


def open_dashboard(
    monkeypatch: pytest.MonkeyPatch,
    graph_for: Callable[[str], DeveloperGraph | None],
) -> tuple[AppTest, list[str]]:
    fetched: list[str] = []

    def fake_graph(driver: object, name: str) -> DeveloperGraph | None:
        fetched.append(name)
        return graph_for(name)

    monkeypatch.setattr(
        "flaskehals.developers.fetch_developer_overview", lambda *a: PEOPLE
    )
    monkeypatch.setattr("flaskehals.developer_graph.fetch_developer_graph", fake_graph)
    at = AppTest.from_file(APP_PATH).run()
    at.text_input(key="login_username").input(TEST_USERNAME)
    at.text_input(key="login_password").input(TEST_PASSWORD)
    at.button[0].click().run()
    assert not at.exception
    return at, fetched


def graph_for(name: str) -> DeveloperGraph | None:
    return FULL_GRAPH if name == "Hans" else LONELY_GRAPH


def test_each_developer_has_a_collapsed_expander_and_nothing_is_fetched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at, fetched = open_dashboard(monkeypatch, graph_for)
    assert [e.label for e in at.expander] == ["Neo4j nodes and relationships"] * 2
    assert not at.session_state["graph_expander_Hans"]
    assert fetched == []


def test_expanding_shows_counts_and_legend_from_neo4j(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at, fetched = open_dashboard(monkeypatch, graph_for)
    at.session_state["graph_expander_Hans"] = True
    at.run()
    assert not at.exception
    assert fetched == ["Hans"]
    captions = [c.value for c in at.caption]
    assert "ASSIGNED_TO: 1 · ASSIGNED_TO_REVIEW: 1 · AUTHORED: 1" in captions
    legend = " ".join(m.value for m in at.markdown)
    assert "HAS_LABEL" in legend and "PullRequest" in legend


def test_collapsing_hides_the_graph_again(monkeypatch: pytest.MonkeyPatch) -> None:
    at, _ = open_dashboard(monkeypatch, graph_for)
    at.session_state["graph_expander_Hans"] = True
    at.run()
    at.session_state["graph_expander_Hans"] = False
    at.run()
    assert not any("AUTHORED" in c.value for c in at.caption)


def test_expanders_are_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    at, fetched = open_dashboard(monkeypatch, graph_for)
    at.session_state["graph_expander_Hans"] = True
    at.run()
    at.session_state["graph_expander_Lonely"] = True
    at.run()
    assert set(fetched) == {"Hans", "Lonely"}
    at.session_state["graph_expander_Lonely"] = False
    at.run()
    assert at.session_state["graph_expander_Hans"]
    assert any("AUTHORED" in c.value for c in at.caption)


def test_developer_without_relationships_shows_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at, _ = open_dashboard(monkeypatch, graph_for)
    at.session_state["graph_expander_Lonely"] = True
    at.run()
    assert [i.value for i in at.info] == ["This developer has no connected nodes."]


def test_neo4j_failure_while_expanding_is_contained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(name: str) -> DeveloperGraph | None:
        raise ServiceUnavailable("bolt://user:secret@host down")

    at, _ = open_dashboard(monkeypatch, boom)
    at.session_state["graph_expander_Hans"] = True
    at.run()
    assert not at.exception
    assert [e.value for e in at.error] == ["Could not reach Neo4j. Is it running?"]
    assert "secret" not in at.error[0].value
    # The rest of the dashboard still renders.
    assert [m.label for m in at.metric][:3] == [
        "Open PRs",
        "Assigned for review",
        "Assigned tasks",
    ]
