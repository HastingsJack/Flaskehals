import pytest
from conftest import TEST_PASSWORD, TEST_PASSWORD_HASH, TEST_USERNAME

from flaskehals.auth import AuthConfig, load_auth_config, verify_credentials

VALID_ENV = {"AUTH_USERNAME": TEST_USERNAME, "AUTH_PASSWORD_HASH": TEST_PASSWORD_HASH}


def test_load_config_from_env() -> None:
    config = load_auth_config(VALID_ENV)
    assert config == AuthConfig(TEST_USERNAME, TEST_PASSWORD_HASH.encode())


@pytest.mark.parametrize(
    "env",
    [
        {},
        {"AUTH_PASSWORD_HASH": TEST_PASSWORD_HASH},
        {"AUTH_USERNAME": TEST_USERNAME},
        {"AUTH_USERNAME": "  ", "AUTH_PASSWORD_HASH": TEST_PASSWORD_HASH},
        {"AUTH_USERNAME": TEST_USERNAME, "AUTH_PASSWORD_HASH": ""},
        {"AUTH_USERNAME": TEST_USERNAME, "AUTH_PASSWORD_HASH": "not-a-bcrypt-hash"},
        # A plaintext password in the hash variable must not be accepted.
        {"AUTH_USERNAME": TEST_USERNAME, "AUTH_PASSWORD_HASH": TEST_PASSWORD},
    ],
    ids=[
        "nothing",
        "no-username",
        "no-hash",
        "blank-username",
        "blank-hash",
        "malformed-hash",
        "plaintext-password",
    ],
)
def test_missing_or_invalid_config_returns_none(env: dict[str, str]) -> None:
    assert load_auth_config(env) is None


@pytest.fixture
def config() -> AuthConfig:
    loaded = load_auth_config(VALID_ENV)
    assert loaded is not None
    return loaded


def test_valid_credentials(config: AuthConfig) -> None:
    assert verify_credentials(config, TEST_USERNAME, TEST_PASSWORD)


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("someone-else", TEST_PASSWORD),
        (TEST_USERNAME, "wrong password"),
        ("someone-else", "wrong password"),
        ("", ""),
        (TEST_USERNAME.upper(), TEST_PASSWORD),
    ],
)
def test_invalid_credentials(config: AuthConfig, username: str, password: str) -> None:
    assert not verify_credentials(config, username, password)
