"""One test per scenario in features/login.feature, driven via Streamlit's AppTest."""

from pathlib import Path

import pytest
from conftest import TEST_PASSWORD, TEST_USERNAME
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parents[1] / "src" / "flaskehals" / "app.py")


@pytest.fixture(autouse=True)
def no_developers(neo4j_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Login tests don't care about developers; avoid touching a real Neo4j."""
    monkeypatch.setattr("flaskehals.developers.fetch_developer_overview", lambda *a: [])


def run_app() -> AppTest:
    return AppTest.from_file(APP_PATH).run()


def on_login_page(at: AppTest) -> bool:
    return any(t.value == "Log in" for t in at.subheader) and not on_dashboard(at)


def on_dashboard(at: AppTest) -> bool:
    return any(t.value == "Dashboard" for t in at.title)


def submit_login(at: AppTest, username: str, password: str) -> AppTest:
    at.text_input(key="login_username").input(username)
    at.text_input(key="login_password").input(password)
    return at.button[0].click().run()


def log_in(at: AppTest) -> AppTest:
    submit_login(at, TEST_USERNAME, TEST_PASSWORD)
    assert on_dashboard(at)
    return at


@pytest.mark.usefixtures("auth_env")
def test_display_login_page_when_unauthenticated() -> None:
    at = run_app()
    assert on_login_page(at)
    assert not on_dashboard(at)
    assert not at.exception


@pytest.mark.usefixtures("auth_env")
def test_successfully_authenticate_with_valid_credentials() -> None:
    at = submit_login(run_app(), TEST_USERNAME, TEST_PASSWORD)
    assert at.session_state["authenticated"] is True
    assert on_dashboard(at)
    assert not at.error


@pytest.mark.usefixtures("auth_env")
@pytest.mark.parametrize(
    ("username", "password"),
    [("someone-else", TEST_PASSWORD), (TEST_USERNAME, "wrong password")],
    ids=["invalid-username", "invalid-password"],
)
def test_reject_invalid_credentials(username: str, password: str) -> None:
    at = submit_login(run_app(), username, password)
    assert "authenticated" not in at.session_state
    assert [e.value for e in at.error] == ["Invalid username or password."]
    assert on_login_page(at)


@pytest.mark.usefixtures("auth_env")
def test_maintain_authenticated_session() -> None:
    at = log_in(run_app())
    at.run()  # the application reruns
    assert at.session_state["authenticated"] is True
    assert on_dashboard(at)


@pytest.mark.usefixtures("auth_env")
def test_log_out() -> None:
    at = log_in(run_app())
    at.button[0].click().run()
    assert "authenticated" not in at.session_state
    assert on_login_page(at)


@pytest.mark.usefixtures("auth_env")
def test_prevent_access_after_logout() -> None:
    at = log_in(run_app())
    at.button[0].click().run()
    at.run()  # attempt to access the dashboard again
    assert on_login_page(at)
    assert not on_dashboard(at)


@pytest.mark.usefixtures("auth_env")
@pytest.mark.parametrize("missing", ["AUTH_USERNAME", "AUTH_PASSWORD_HASH"])
def test_handle_missing_configuration(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    monkeypatch.delenv(missing)
    at = run_app()
    assert any("not configured" in e.value for e in at.error)
    assert not on_dashboard(at)
    assert not at.text_input  # no login form is offered
    assert not at.exception


@pytest.mark.usefixtures("auth_env")
def test_existing_session_denied_if_configuration_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = log_in(run_app())
    monkeypatch.delenv("AUTH_PASSWORD_HASH")
    at.run()
    assert not on_dashboard(at)
    assert "authenticated" not in at.session_state
