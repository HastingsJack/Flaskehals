"""Turn a DeveloperGraph into a Neo4j Browser-style graph for streamlit-agraph.

No Streamlit code here: colours, captions and node/edge construction are pure
functions so they can be tested without a browser.
"""

from streamlit_agraph import Config, Edge, Node

from flaskehals.developer_graph import DeveloperGraph, GraphNode

# One fixed colour per node label (similar in spirit to the Neo4j Browser).
LABEL_COLORS: dict[str, str] = {
    "Developer": "#4C8EDA",
    "PullRequest": "#57C7E3",
    "Task": "#F79767",
    "Label": "#D9C8AE",
}
FALLBACK_COLOR = "#A5ABB6"
DEVELOPER_NODE_SIZE = 35
NODE_SIZE = 25
CAPTION_MAX_LENGTH = 24


def label_color(label: str) -> str:
    return LABEL_COLORS.get(label, FALLBACK_COLOR)


def primary_label(node: GraphNode) -> str:
    return node.labels[0] if node.labels else "Node"


def node_caption(node: GraphNode) -> str:
    """Short text drawn on the node: its name or title, else its label."""
    props = node.properties
    text = ""
    for key in ("name", "title", "full_name"):
        if props.get(key):
            text = str(props[key])
            break
    if "number" in props and text:
        text = f"#{props['number']} {text}"
    if len(text) > CAPTION_MAX_LENGTH:
        text = text[: CAPTION_MAX_LENGTH - 1] + "…"
    return text or primary_label(node)


def graph_legend(graph: DeveloperGraph) -> tuple[list[str], list[str]]:
    """(node labels, relationship types) present in the graph, sorted."""
    labels = sorted({primary_label(node) for node in graph.nodes})
    types = sorted({edge.type for edge in graph.edges})
    return labels, types


def build_agraph(graph: DeveloperGraph) -> tuple[list[Node], list[Edge], Config]:
    nodes = [
        Node(
            id=node.id,
            label=node_caption(node),
            title=primary_label(node),
            color=label_color(primary_label(node)),
            size=DEVELOPER_NODE_SIZE if node.id == graph.developer_id else NODE_SIZE,
        )
        for node in graph.nodes
    ]
    edges = [
        Edge(source=edge.source, target=edge.target, label=edge.type)
        for edge in graph.edges
    ]
    config = Config(
        width=700,
        height=450,
        directed=True,
        physics=True,
        hierarchical=False,
    )
    return nodes, edges, config
