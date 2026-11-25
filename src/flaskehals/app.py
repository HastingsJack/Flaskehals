"""Streamlit entry point.

Run with: uv run streamlit run src/flaskehals/app.py
"""

from collections.abc import Callable

import streamlit as st
from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.auth import load_auth_config, verify_credentials
from flaskehals.dashboard import render_developer_overview
from flaskehals.developers import (
    DeveloperGraph,
    DeveloperOverview,
    fetch_developer_graph,
    fetch_developer_overview,
)
from flaskehals.graph import Neo4jConfig, load_neo4j_config
from flaskehals.specification import generate_specification, load_openrouter_config
from flaskehals.task_page import (
    TaskServices,
    keep_draft_state,
    render_task_creation,
    render_task_overview,
)
from flaskehals.tasks import (
    DataStoreError,
    fetch_developer_profiles,
    fetch_tasks,
    save_approved_task,
)
from flaskehals.theme import apply_background

AUTH_KEY = "authenticated"
ERROR_KEY = "login_error"
LOGIN_ERROR_MESSAGE = "Invalid username or password."
CONFIG_ERROR_MESSAGE = (
    "Authentication is not configured. Set AUTH_USERNAME and AUTH_PASSWORD_HASH."
)
NEO4J_CONFIG_ERROR_MESSAGE = (
    "Neo4j is not configured. Set NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD."
)
NEO4J_UNAVAILABLE_MESSAGE = "Could not reach Neo4j. Is it running?"


@st.cache_resource
def get_driver(config: Neo4jConfig) -> Driver:
    return GraphDatabase.driver(config.uri, auth=(config.username, config.password))


def neo4j_call[T](work: Callable[[Driver, str | None], T]) -> T:
    """Run a Neo4j operation, turning driver failures into DataStoreError."""
    config = load_neo4j_config()
    if config is None:
        raise DataStoreError(NEO4J_CONFIG_ERROR_MESSAGE)
    try:
        return work(get_driver(config), config.database)
    except (Neo4jError, DriverError) as exc:
        raise DataStoreError(NEO4J_UNAVAILABLE_MESSAGE) from exc


def load_developers() -> list[DeveloperOverview] | None:
    """Fetch developers from Neo4j, or show an error and return None."""
    try:
        return neo4j_call(fetch_developer_overview)
    except DataStoreError as exc:
        st.error(str(exc))
        return None


def load_developer_graph(name: str) -> DeveloperGraph | None:
    return neo4j_call(lambda driver, db: fetch_developer_graph(driver, name, db))


def build_task_services() -> TaskServices:
    openrouter = load_openrouter_config()

    def generate(
        title: str, description: str, spec: str | None, feedback: str | None
    ) -> str:
        assert openrouter is not None
        return generate_specification(openrouter, title, description, spec, feedback)

    return TaskServices(
        generate=generate if openrouter is not None else None,
        load_profiles=lambda: neo4j_call(fetch_developer_profiles),
        save_task=lambda task: neo4j_call(
            lambda driver, db: save_approved_task(driver, task, db)
        ),
        load_tasks=lambda: neo4j_call(fetch_tasks),
    )


def render_login() -> None:
    st.title("Flaskehals")
    st.subheader("Log in")

    with st.form("login_form"):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        config = load_auth_config()
        if config is not None and verify_credentials(config, username, password):
            st.session_state[AUTH_KEY] = True
            st.session_state.pop(ERROR_KEY, None)
            st.rerun()
        else:
            st.session_state[ERROR_KEY] = LOGIN_ERROR_MESSAGE

    if ERROR_KEY in st.session_state:
        st.error(st.session_state[ERROR_KEY])


def render_dashboard() -> None:
    st.title("Dashboard")
    developers = load_developers()
    if developers is not None:
        render_developer_overview(developers, load_developer_graph)


def render_new_task() -> None:
    render_task_creation(build_task_services())


def render_tasks() -> None:
    render_task_overview(build_task_services())


def build_pages() -> list[st.Page]:
    """The single definition of the application's pages: titles and URL paths."""
    return [
        st.Page(
            render_dashboard, title="Dashboard", url_path="dashboard", default=True
        ),
        st.Page(render_new_task, title="New task", url_path="new-task"),
        st.Page(render_tasks, title="Tasks", url_path="tasks"),
    ]


def render_app() -> None:
    page = st.navigation(build_pages())
    if st.sidebar.button("Log out"):
        st.session_state.clear()
        st.rerun()
    keep_draft_state()
    page.run()


def main() -> None:
    # Load a local .env if present. Real environment variables take precedence.
    load_dotenv()
    apply_background()

    # Re-check config on every run: if it disappears, existing sessions lose
    # access too. Show no login form at all when it's missing.
    if load_auth_config() is None:
        st.session_state.clear()
        st.error(CONFIG_ERROR_MESSAGE)
        st.stop()

    if st.session_state.get(AUTH_KEY) is True:
        render_app()
    else:
        render_login()


main()
