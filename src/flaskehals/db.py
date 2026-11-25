"""Neo4j connection: settings, opening a driver, and the shared constraints.

Every entry point (the Streamlit app and both command line scripts) opens its
driver here, so connection errors and the uniqueness constraints are handled
in exactly one place.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import LiteralString

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import DriverError, Neo4jError

URI_ENV = "NEO4J_URI"
USERNAME_ENV = "NEO4J_USERNAME"
PASSWORD_ENV = "NEO4J_PASSWORD"

UNAVAILABLE_MESSAGE = "Could not reach Neo4j. Is it running?"

CONSTRAINTS: tuple[LiteralString, ...] = (
    (
        "CREATE CONSTRAINT repository_full_name IF NOT EXISTS "
        "FOR (n:Repository) REQUIRE n.full_name IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT pull_request_github_id IF NOT EXISTS "
        "FOR (n:PullRequest) REQUIRE n.github_id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT comment_github_id IF NOT EXISTS "
        "FOR (n:Comment) REQUIRE n.github_id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT developer_name IF NOT EXISTS "
        "FOR (n:Developer) REQUIRE n.name IS UNIQUE"
    ),
    "CREATE CONSTRAINT label_name IF NOT EXISTS FOR (n:Label) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT task_id IF NOT EXISTS FOR (n:Task) REQUIRE n.id IS UNIQUE",
    (
        "CREATE CONSTRAINT task_number IF NOT EXISTS "
        "FOR (n:Task) REQUIRE n.number IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT reviewer_recommendation_key IF NOT EXISTS "
        "FOR (n:ReviewerRecommendation) REQUIRE n.key IS UNIQUE"
    ),
)


class DataStoreError(Exception):
    """Neo4j is missing, unreachable or failed. The message is safe to show."""


@dataclass(frozen=True)
class Neo4jConfig:
    uri: str
    username: str
    password: str


def load_neo4j_config(env: Mapping[str, str] | None = None) -> Neo4jConfig | None:
    """Load Neo4j settings, or None if any value is missing."""
    if env is None:
        env = os.environ
    uri = env.get(URI_ENV, "").strip()
    username = env.get(USERNAME_ENV, "").strip()
    password = env.get(PASSWORD_ENV, "")
    if not uri or not username or not password:
        return None
    return Neo4jConfig(uri=uri, username=username, password=password)


def open_driver(config: Neo4jConfig) -> Driver:
    """Connect, check the connection and make sure the constraints exist.

    Failing here, before any work is done, gives one clear error instead of the
    driver retrying for about 30 seconds. Raises DataStoreError.
    """
    driver = GraphDatabase.driver(config.uri, auth=(config.username, config.password))
    try:
        driver.verify_connectivity()
        for constraint in CONSTRAINTS:
            driver.execute_query(constraint)
    except (Neo4jError, DriverError) as exc:
        driver.close()
        raise DataStoreError(UNAVAILABLE_MESSAGE) from exc
    return driver
