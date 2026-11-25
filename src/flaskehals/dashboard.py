"""Streamlit presentation of the developer overview."""

from collections.abc import Callable
from html import escape

import streamlit as st
from streamlit_agraph import agraph

from flaskehals.db import DataStoreError
from flaskehals.developer_graph import DeveloperGraph
from flaskehals.developers import DeveloperOverview, resolve_picture
from flaskehals.graph_view import build_agraph, graph_legend, label_color

EMPTY_MESSAGE = "No developers found. Run the GitHub sync to import them."
TASKS_NOTE = "Approved tasks assigned to this developer."
GRAPH_EXPANDER_LABEL = "Neo4j nodes and relationships"
NO_CONNECTIONS_MESSAGE = "This developer has no connected nodes."
GRAPH_NOT_FOUND_MESSAGE = "This developer was not found in Neo4j."
SELECT_NODE_HINT = "Click a node to inspect its properties."

GraphLoader = Callable[[str], DeveloperGraph | None]


def render_developer_overview(
    developers: list[DeveloperOverview], load_graph: GraphLoader
) -> None:
    st.subheader("Developers")
    if not developers:
        st.info(EMPTY_MESSAGE)
        return
    for developer in developers:
        with st.container(border=True):
            picture, name, open_prs, reviews, tasks = st.columns([1, 3, 2, 2, 2])
            picture.image(str(resolve_picture(developer.picture)), width=64)
            name.markdown(f"**{developer.name}**")
            open_prs.metric("Open PRs", developer.open_pull_requests)
            reviews.metric("Assigned for review", developer.review_assignments)
            tasks.metric("Assigned tasks", developer.assigned_tasks, help=TASKS_NOTE)

            _render_graph_expander(developer.name, load_graph)


def _render_graph_expander(name: str, load_graph: GraphLoader) -> None:
    # A keyed expander reports whether it is open, so Neo4j is only queried for
    # developers the user has expanded. Each developer keeps its own state.
    expander = st.expander(
        GRAPH_EXPANDER_LABEL, key=f"graph_expander_{name}", on_change="rerun"
    )
    if not expander.open:
        return
    with expander:
        try:
            graph = load_graph(name)
        except DataStoreError as exc:
            st.error(str(exc))
            return
        if graph is None:
            st.warning(GRAPH_NOT_FOUND_MESSAGE)
            return
        _render_graph(graph)


def _render_graph(graph: DeveloperGraph) -> None:
    counts = graph.relationship_counts()
    if counts:
        st.caption(" · ".join(f"{kind}: {count}" for kind, count in counts.items()))
    else:
        st.info(NO_CONNECTIONS_MESSAGE)
    _render_legend(graph)
    nodes, edges, config = build_agraph(graph)
    selected_id = agraph(nodes=nodes, edges=edges, config=config)
    selected = next((n for n in graph.nodes if n.id == selected_id), None)
    if selected is None:
        st.caption(SELECT_NODE_HINT)
        return
    st.markdown(f"**{', '.join(selected.labels)}**")
    st.json(dict(selected.properties), expanded=True)


def _render_legend(graph: DeveloperGraph) -> None:
    labels, types = graph_legend(graph)
    swatches = " ".join(
        f'<span style="color:{label_color(label)}">●</span> {escape(label)}'
        for label in labels
    )
    st.markdown(
        f"{swatches}<br/>Relationships: {escape(', '.join(types)) or '—'}",
        unsafe_allow_html=True,
    )
