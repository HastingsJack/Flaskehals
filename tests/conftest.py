from unittest.mock import MagicMock

import bcrypt
import pytest

TEST_USERNAME = "reviewer"
TEST_PASSWORD = "correct horse battery staple"
# Low cost factor keeps the tests fast; production hashes should use the default.
TEST_PASSWORD_HASH = bcrypt.hashpw(
    TEST_PASSWORD.encode(), bcrypt.gensalt(rounds=4)
).decode()


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_USERNAME", TEST_USERNAME)
    monkeypatch.setenv("AUTH_PASSWORD_HASH", TEST_PASSWORD_HASH)


@pytest.fixture(autouse=True)
def no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop a developer's real .env from leaking into tests.

    app.py re-imports load_dotenv on every AppTest run, so patching the dotenv
    module covers it. sync.py imported it once at import time, so it needs
    its own patch.
    """

    def noop(*args: object, **kwargs: object) -> bool:
        return False

    monkeypatch.setattr("dotenv.load_dotenv", noop)
    monkeypatch.setattr("flaskehals.sync.load_dotenv", noop)


@pytest.fixture
def neo4j_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neo4j settings, and a driver that never really connects."""
    monkeypatch.setenv("NEO4J_URI", "neo4j://localhost:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setattr("flaskehals.db.open_driver", lambda config: MagicMock())
