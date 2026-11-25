"""Opening the Neo4j driver: one place for connection errors and constraints."""

from unittest.mock import MagicMock

import pytest
from neo4j.exceptions import ServiceUnavailable

from flaskehals import db
from flaskehals.db import CONSTRAINTS, DataStoreError, Neo4jConfig, open_driver

CONFIG = Neo4jConfig("neo4j://localhost:7687", "neo4j", "secret")
ENV = {"NEO4J_URI": "neo4j://x", "NEO4J_USERNAME": "u", "NEO4J_PASSWORD": "p"}


@pytest.mark.parametrize("missing", list(ENV))
def test_config_is_none_when_a_value_is_missing(missing: str) -> None:
    env = {k: v for k, v in ENV.items() if k != missing}
    assert db.load_neo4j_config(env) is None


def test_config_is_loaded_from_the_environment() -> None:
    assert db.load_neo4j_config(ENV) == Neo4jConfig("neo4j://x", "u", "p")


def test_open_driver_checks_the_connection_then_creates_every_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = MagicMock()
    monkeypatch.setattr(db.GraphDatabase, "driver", lambda *a, **k: driver)
    assert open_driver(CONFIG) is driver
    driver.verify_connectivity.assert_called_once()
    created = [call.args[0] for call in driver.execute_query.call_args_list]
    assert created == list(CONSTRAINTS)


def test_constraints_cover_every_unique_key_the_app_merges_on() -> None:
    text = " ".join(CONSTRAINTS)
    for name in ("task_number", "task_id", "reviewer_recommendation_key", "label_name"):
        assert name in text


def test_open_driver_turns_neo4j_failure_into_a_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = MagicMock()
    driver.verify_connectivity.side_effect = ServiceUnavailable("secret details")
    monkeypatch.setattr(db.GraphDatabase, "driver", lambda *a, **k: driver)
    with pytest.raises(DataStoreError) as error:
        open_driver(CONFIG)
    assert "secret details" not in str(error.value)
    driver.close.assert_called_once()
