"""Streamlit entry point.

Run with: uv run streamlit run src/flaskehals/app.py
"""

from collections.abc import Callable
from functools import partial
from typing import Concatenate

import streamlit as st
from dotenv import load_dotenv
from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from flaskehals.auth import load_auth_config, verify_credentials
from flaskehals.dashboard import render_developer_overview
from flaskehals.db import (
    UNAVAILABLE_MESSAGE,
    DataStoreError,
    Neo4jConfig,
    load_neo4j_config,
    open_driver,
)
from flaskehals.developer_graph import DeveloperGraph, fetch_developer_graph
from flaskehals.developers import DeveloperOverview, fetch_developer_overview
from flaskehals.github import GitHubClient, load_github_config
from flaskehals.reviewer_reassignment import reassign_reviewer
from flaskehals.reviewer_recommendations import fetch_recommendations
from flaskehals.specification import (
    OpenRouterConfig,
    generate_specification,
    load_openrouter_config,
    request_completion,
)
from flaskehals.task_creation_page import keep_draft_state, render_task_creation
from flaskehals.task_overview_page import render_task_overview
from flaskehals.task_reassignment import reassign_task_and_labels
from flaskehals.task_services import TaskServices
from flaskehals.tasks import (
    fetch_developer_profiles,
    fetch_tasks,
    reassign_task,
    save_approved_task,
)
from flaskehals.theme import apply_background

AUTH_KEY = "authenticated"
ERROR_KEY = "login_error"
LOGIN_ERROR_MESSAGE = "Invalid username or password."
CONFIG_ERROR_MESSAGE = (
    "Authentication is not configured. Set AUTH_USERNAME and AUTH_PASSWORD_HASH."
)
GITHUB_CONFIG_ERROR_MESSAGE = (
    "GitHub is not configured. Set GITHUB_TOKEN and GITHUB_REPOSITORY."
)
NEO4J_CONFIG_ERROR_MESSAGE = (
    "Neo4j is not configured. Set NEO4J_URI, NEO4J_USERNAME and NEO4J_PASSWORD."
)


@st.cache_resource
def get_driver(config: Neo4jConfig) -> Driver:
    """One driver per session of the server, shared by every page run."""
    return open_driver(config)


def neo4j_call[**P, T](
    work: Callable[Concatenate[Driver, P], T], *args: P.args, **kwargs: P.kwargs
) -> T:
    """Run ``work(driver, *args)``, turning driver failures into DataStoreError."""
    config = load_neo4j_config()
    if config is None:
        raise DataStoreError(NEO4J_CONFIG_ERROR_MESSAGE)
    try:
        return work(get_driver(config), *args, **kwargs)
    except (Neo4jError, DriverError) as exc:
        raise DataStoreError(UNAVAILABLE_MESSAGE) from exc


def load_developers() -> list[DeveloperOverview] | None:
    """Fetch developers from Neo4j, or show an error and return None."""
    try:
        return neo4j_call(fetch_developer_overview)
    except DataStoreError as exc:
        st.error(str(exc))
        return None


def load_developer_graph(name: str) -> DeveloperGraph | None:
    return neo4j_call(fetch_developer_graph, name)


def reassign_reviewer_on_github(
    task_id: str, pr_number: int, new_reviewer: str, expected_current: str
) -> None:
    """Change the reviewer in GitHub and Neo4j. Needs GITHUB_TOKEN to be set."""
    config = load_github_config()
    if config is None:
        raise DataStoreError(GITHUB_CONFIG_ERROR_MESSAGE)
    with GitHubClient(config) as client:
        neo4j_call(
            reassign_reviewer,
            client,
            task_id,
            pr_number,
            new_reviewer,
            expected_current,
        )


def _complete(config: OpenRouterConfig, messages: list[dict[str, str]]) -> str:
    return request_completion(config, messages, "recommendation")


def reassign_task_on_github(
    task_id: str, new_developer: str, expected_current: str
) -> None:
    """Re-assign the task and update the dev: label of its open pull requests."""
    config = load_github_config()
    if config is None:
        raise DataStoreError(GITHUB_CONFIG_ERROR_MESSAGE)
    with GitHubClient(config) as client:
        neo4j_call(
            reassign_task_and_labels, client, task_id, new_developer, expected_current
        )


def build_task_services() -> TaskServices:
    openrouter = load_openrouter_config()
    return TaskServices(
        generate=partial(generate_specification, openrouter) if openrouter else None,
        complete=(partial(_complete, openrouter) if openrouter else None),
        load_profiles=partial(neo4j_call, fetch_developer_profiles),
        save_task=partial(neo4j_call, save_approved_task),
        load_tasks=partial(neo4j_call, fetch_tasks),
        reassign_task=(
            reassign_task_on_github
            if load_github_config()
            else partial(neo4j_call, reassign_task)
        ),
        github_labels=load_github_config() is not None,
        load_recommendations=partial(neo4j_call, fetch_recommendations),
        reassign_reviewer=(
            reassign_reviewer_on_github if load_github_config() else None
        ),
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
