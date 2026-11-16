"""Authentication logic, independent of the Streamlit UI.

Credentials come from environment variables. Only a bcrypt hash of the
password is ever configured; the plaintext password is never stored.
"""

import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass

import bcrypt

USERNAME_ENV = "AUTH_USERNAME"
PASSWORD_HASH_ENV = "AUTH_PASSWORD_HASH"

# Used when the username is wrong, so a failed lookup costs the same bcrypt
# work as a wrong password and response time doesn't reveal valid usernames.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt())


@dataclass(frozen=True)
class AuthConfig:
    username: str
    password_hash: bytes


def load_auth_config(env: Mapping[str, str] | None = None) -> AuthConfig | None:
    """Load credentials from the environment.

    Returns None if the username or hash is missing, blank, or the hash is
    not a valid bcrypt hash. Callers must treat None as "deny all access".
    """
    if env is None:
        env = os.environ

    username = env.get(USERNAME_ENV, "").strip()
    password_hash = env.get(PASSWORD_HASH_ENV, "").strip()
    if not username or not password_hash:
        return None

    hash_bytes = password_hash.encode()
    try:
        # Validate the hash format up front so a typo fails at startup
        # rather than on the first login attempt.
        bcrypt.checkpw(b"", hash_bytes)
    except ValueError:
        return None

    return AuthConfig(username=username, password_hash=hash_bytes)


def verify_credentials(config: AuthConfig, username: str, password: str) -> bool:
    """Return True only if both the username and password are correct."""
    username_ok = hmac.compare_digest(username.encode(), config.username.encode())
    # Always run bcrypt, even when the username is wrong (see _DUMMY_HASH).
    hash_to_check = config.password_hash if username_ok else _DUMMY_HASH
    password_ok = bcrypt.checkpw(password.encode(), hash_to_check)
    return username_ok and password_ok
