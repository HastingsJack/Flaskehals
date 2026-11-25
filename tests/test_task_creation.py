"""Scenarios from features/task-creation-developer-assignment.feature (AppTest)."""

from pathlib import Path

import pytest
from conftest import TEST_PASSWORD, TEST_USERNAME
from neo4j.exceptions import ServiceUnavailable
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Button

from flaskehals.developer_scoring import DeveloperProfile
from flaskehals.models import NewTask, PreviousAssignment, Task
from flaskehals.reviewer_recommendations import ReviewerRecommendation
from flaskehals.specification import SpecificationError

APP_PATH = str(Path(__file__).parents[1] / "src" / "flaskehals" / "app.py")

PYTHON_DEV = DeveloperProfile(
    "Hans", open_pull_requests=1, history_texts=("Postgres CSV export",)
)
OTHER_DEV = DeveloperProfile("Peter", history_texts=("React dashboard",))
SPEC = "## Objective\nExport CSV from Postgres"


class Fakes:
    """Replaces OpenRouter and Neo4j for the app under test."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.profiles: list[DeveloperProfile] = [PYTHON_DEV, OTHER_DEV]
        self.specs = [SPEC]
        self.generate_error: Exception | None = None
        self.profiles_error: Exception | None = None
        self.save_error: Exception | None = None
        self.generate_calls: list[tuple[str, str, str | None, str | None]] = []
        self.saved: list[NewTask] = []
        self.tasks: list[Task] = []
        self.recommendations: list[ReviewerRecommendation] = []
        self.reassign_error: Exception | None = None
        self.reassigned: list[tuple[str, str, str | None]] = []
        monkeypatch.setattr(
            "flaskehals.specification.generate_specification", self.generate
        )
        monkeypatch.setattr(
            "flaskehals.tasks.fetch_developer_profiles", self.fetch_profiles
        )
        monkeypatch.setattr("flaskehals.tasks.save_approved_task", self.save)
        monkeypatch.setattr("flaskehals.tasks.fetch_tasks", lambda *a: self.tasks)
        monkeypatch.setattr("flaskehals.tasks.reassign_task", self.reassign)
        monkeypatch.setattr(
            "flaskehals.reviewer_recommendations.fetch_recommendations",
            lambda *a: self.recommendations,
        )
        monkeypatch.setattr(
            "flaskehals.developers.fetch_developer_overview", lambda *a: []
        )

    def generate(self, config, title, description, spec=None, feedback=None):  # type: ignore[no-untyped-def]
        self.generate_calls.append((title, description, spec, feedback))
        if self.generate_error:
            raise self.generate_error
        return self.specs.pop(0) if len(self.specs) > 1 else self.specs[0]

    def fetch_profiles(self, *args: object) -> list[DeveloperProfile]:
        if self.profiles_error:
            raise self.profiles_error
        return self.profiles

    def reassign(
        self,
        driver: object,
        task_id: str,
        developer: str,
        current: str | None,
    ) -> None:
        if self.reassign_error:
            raise self.reassign_error
        self.reassigned.append((task_id, developer, current))

    def save(self, driver: object, task: NewTask) -> str:
        if self.save_error:
            raise self.save_error
        self.saved.append(task)
        return "id"


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Fakes:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    return Fakes(monkeypatch)


pytestmark = pytest.mark.usefixtures("auth_env", "neo4j_env")


def button(at: AppTest, label: str) -> Button:
    return next(b for b in at.button if b.label == label)


def open_task_page() -> AppTest:
    at = AppTest.from_file(APP_PATH).run()
    at.text_input(key="login_username").input(TEST_USERNAME)
    at.text_input(key="login_password").input(TEST_PASSWORD)
    at.button[0].click().run()
    return go_to(at, "New task")


PAGE_PATHS = {"Dashboard": "", "New task": "new-task", "Tasks": "tasks"}


def go_to(at: AppTest, page: str) -> AppTest:
    """Open a page by URL path.

    AppTest.switch_page only takes file paths, so for callable st.navigation
    pages we select the registered page hash directly.
    """
    path = PAGE_PATHS[page]
    at._page_hash = next(
        h
        for h, info in at._registered_pages.items()
        if info.get("url_pathname") == path
    )
    return at.run()


def fill(
    at: AppTest, title: str = "CSV export", description: str = "Export it"
) -> AppTest:
    at.text_input(key="task_title").input(title)
    return at.text_area(key="task_description").input(description).run()


def generated(at: AppTest) -> AppTest:
    fill(at)
    return button(at, "Generate specification").click().run()


def test_open_task_creation_form(fakes: Fakes) -> None:
    at = open_task_page()
    assert not at.exception
    assert at.text_input(key="task_title").label == "Task title"
    assert at.text_area(key="task_description").label == "Task description"
    assert not button(at, "Generate specification").disabled
    assert not at.error


def test_missing_openrouter_key_disables_generation(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY")
    at = open_task_page()
    assert any("OPENROUTER_API_KEY" in e.value for e in at.error)
    assert button(at, "Generate specification").disabled


def test_generate_sends_description_and_shows_specification(fakes: Fakes) -> None:
    at = generated(open_task_page())
    assert fakes.generate_calls == [("CSV export", "Export it", None, None)]
    assert at.text_area(key="task_spec").value == SPEC
    assert not at.error


@pytest.mark.parametrize(
    ("title", "description"), [("", "d"), ("t", "  ")], ids=["title", "description"]
)
def test_empty_input_is_rejected_without_calling_openrouter(
    fakes: Fakes, title: str, description: str
) -> None:
    at = fill(open_task_page(), title, description)
    button(at, "Generate specification").click().run()
    assert at.error
    assert fakes.generate_calls == []


def test_openrouter_failure_shows_error_and_preserves_description(
    fakes: Fakes,
) -> None:
    fakes.generate_error = SpecificationError("down")
    at = generated(open_task_page())
    assert [e.value for e in at.error] == ["down"]
    assert at.text_area(key="task_description").value == "Export it"
    assert not at.text_area(key="task_description").disabled
    assert not any(t.key == "task_spec" for t in at.text_area)


def test_regenerate_sends_original_description_edited_spec_and_feedback(
    fakes: Fakes,
) -> None:
    fakes.specs = [SPEC, "## Objective\nUpdated"]
    at = generated(open_task_page())
    at.text_area(key="task_spec").input("edited spec")
    at.text_area(key="task_feedback").input("add auth")
    button(at, "Regenerate specification").click().run()
    assert fakes.generate_calls[-1] == (
        "CSV export",
        "Export it",
        "edited spec",
        "add auth",
    )
    assert at.text_area(key="task_spec").value == "## Objective\nUpdated"
    assert at.text_area(key="task_description").value == "Export it"
    assert at.text_area(key="task_description").disabled


def test_regenerate_without_feedback(fakes: Fakes) -> None:
    fakes.specs = [SPEC, "## Objective\nUpdated"]
    at = generated(open_task_page())
    button(at, "Regenerate specification").click().run()
    assert fakes.generate_calls[-1][3] == ""
    assert at.text_area(key="task_spec").value == "## Objective\nUpdated"
    assert not at.error


def test_failed_regeneration_keeps_current_specification(fakes: Fakes) -> None:
    at = generated(open_task_page())
    at.text_area(key="task_spec").input("my edit")
    fakes.generate_error = SpecificationError("down")
    button(at, "Regenerate specification").click().run()
    assert at.error
    assert at.text_area(key="task_spec").value == "my edit"


def test_developer_is_recommended_as_default_selection(fakes: Fakes) -> None:
    at = generated(open_task_page())
    assert at.selectbox(key="task_developer").value == "Hans"
    assert at.selectbox(key="task_developer").options == ["Hans", "Peter"]
    assert any("Hans" in i.value for i in at.info)


def test_recommendation_is_reevaluated_after_regeneration(fakes: Fakes) -> None:
    fakes.specs = [SPEC, "## Objective\nBuild a React dashboard"]
    at = generated(open_task_page())
    assert at.selectbox(key="task_developer").value == "Hans"
    button(at, "Regenerate specification").click().run()
    assert at.selectbox(key="task_developer").value == "Peter"


def test_manual_override_survives_regeneration(fakes: Fakes) -> None:
    fakes.specs = [SPEC, "## Objective\nBuild a React dashboard"]
    at = generated(open_task_page())
    at.selectbox(key="task_developer").select("Hans").run()
    at.selectbox(key="task_developer").select("Peter").run()
    fakes.specs = [SPEC]  # regenerated spec still recommends Hans
    button(at, "Regenerate specification").click().run()
    assert at.selectbox(key="task_developer").value == "Peter"


def test_empty_developer_list_notifies_and_blocks_approval(fakes: Fakes) -> None:
    fakes.profiles = []
    at = generated(open_task_page())
    assert any("No developers" in w.value for w in at.warning)
    assert at.selectbox(key="task_developer").value is None
    assert button(at, "Approve and save task").disabled


def test_no_suitable_developer_allows_manual_selection(fakes: Fakes) -> None:
    fakes.profiles = [
        DeveloperProfile("A", open_pull_requests=2),
        DeveloperProfile("B", open_pull_requests=2),
    ]
    at = generated(open_task_page())
    assert any("manually" in w.value for w in at.warning)
    assert at.selectbox(key="task_developer").value is None
    at.selectbox(key="task_developer").select("B").run()
    button(at, "Approve and save task").click().run()
    assert [t.assigned_developer for t in fakes.saved] == ["B"]
    assert fakes.saved[0].recommended_developer is None


def test_neo4j_failure_loading_developers_still_shows_specification(
    fakes: Fakes,
) -> None:
    fakes.profiles_error = ServiceUnavailable("down")
    at = generated(open_task_page())
    assert at.text_area(key="task_spec").value == SPEC
    assert any("Neo4j" in w.value for w in at.warning)
    assert button(at, "Approve and save task").disabled


def test_accept_saves_edited_spec_original_description_and_recommendation(
    fakes: Fakes,
) -> None:
    at = generated(open_task_page())
    at.text_area(key="task_spec").input("final spec").run()
    at.selectbox(key="task_developer").select("Peter").run()
    button(at, "Approve and save task").click().run()
    assert fakes.saved == [
        NewTask(
            title="CSV export",
            description="Export it",
            specification="final spec",
            assigned_developer="Peter",
            recommended_developer="Hans",
        )
    ]
    assert any("Peter" in s.value for s in at.success)
    assert not at.error
    assert not any(t.key == "task_spec" for t in at.text_area)


def test_reject_does_not_save_and_keeps_description(fakes: Fakes) -> None:
    at = generated(open_task_page())
    button(at, "Reject task").click().run()
    assert fakes.saved == []
    assert at.text_area(key="task_description").value == "Export it"
    assert at.text_input(key="task_title").value == "CSV export"
    assert not at.text_area(key="task_description").disabled


def test_database_failure_on_save_shows_error_and_is_not_reported_saved(
    fakes: Fakes,
) -> None:
    fakes.save_error = ServiceUnavailable("down")
    at = generated(open_task_page())
    button(at, "Approve and save task").click().run()
    assert any("not saved" in e.value for e in at.error)
    assert not at.success
    assert at.text_area(key="task_spec").value == SPEC


def test_draft_survives_visiting_another_page(fakes: Fakes) -> None:
    at = generated(open_task_page())
    at.text_area(key="task_spec").input("my edit").run()
    go_to(at, "Dashboard")
    at = go_to(at, "New task")
    assert at.text_area(key="task_spec").value == "my edit"
    assert at.selectbox(key="task_developer").value == "Hans"
    assert at.text_area(key="task_description").value == "Export it"


def test_view_previously_created_tasks(fakes: Fakes) -> None:
    fakes.tasks = [
        Task(
            "1",
            "CSV export",
            "Export it",
            "## Objective\nx",
            "approved",
            "Hans",
            "Peter",
            "2026-11-16T10:00:00Z",
        )
    ]
    at = open_task_page()
    at = go_to(at, "Tasks")
    assert [e.label for e in at.expander] == ["CSV export - Peter"]
    assert any("Hans" in m.value for m in at.markdown)


def test_task_overview_empty_and_failure(
    fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = go_to(open_task_page(), "Tasks")
    assert [i.value for i in at.info] == ["No approved tasks yet."]

    def boom(*args: object) -> list[Task]:
        raise ServiceUnavailable("down")

    monkeypatch.setattr("flaskehals.tasks.fetch_tasks", boom)
    at = at.run()
    assert any("Neo4j" in e.value for e in at.error)
    assert not at.info


# --- Re-assignment (features/tasks/task-reassignment.feature) ---------------

TASK = Task(
    "1", "CSV export", "Export it", SPEC, "approved", "Peter", "Peter",
    "2026-11-16T10:00:00Z",
)  # fmt: skip


def reassignment_open(fakes: Fakes) -> AppTest:
    fakes.tasks = [TASK]
    at = go_to(open_task_page(), "Tasks")
    return button(at, "Re-assign").click().run()


def test_each_assigned_task_offers_reassign(fakes: Fakes) -> None:
    fakes.tasks = [TASK]
    at = go_to(open_task_page(), "Tasks")
    assert [b.label for b in at.button if b.label != "Log out"] == ["Re-assign"]


def test_reassign_panel_shows_current_developer_and_recommends_another(
    fakes: Fakes,
) -> None:
    at = reassignment_open(fakes)
    box = at.selectbox(key="reassign_developer")
    assert any("Currently assigned to:** Peter" in m.value for m in at.markdown)
    assert box.value == "Hans"  # Peter is current; Hans is recommended instead
    assert any("(current)" in str(o) for o in box.options)


def test_confirm_reassigns_to_selected_developer(fakes: Fakes) -> None:
    at = reassignment_open(fakes)
    at = button(at, "Confirm re-assignment").click().run()
    assert fakes.reassigned == [("1", "Hans", "Peter")]
    assert any("re-assigned from Peter to Hans" in s.value for s in at.success)
    assert [b.label for b in at.button if b.label != "Log out"] == ["Re-assign"]


def test_confirm_without_selection_is_rejected(fakes: Fakes) -> None:
    at = reassignment_open(fakes)
    at.selectbox(key="reassign_developer").set_value(None).run()
    at = button(at, "Confirm re-assignment").click().run()
    assert fakes.reassigned == []
    assert any("Select a developer" in e.value for e in at.error)


def test_confirm_same_developer_makes_no_change(fakes: Fakes) -> None:
    at = reassignment_open(fakes)
    at.selectbox(key="reassign_developer").set_value("Peter").run()
    at = button(at, "Confirm re-assignment").click().run()
    assert fakes.reassigned == []
    assert any("already assigned" in e.value for e in at.error)


def test_cancel_leaves_assignment_unchanged(fakes: Fakes) -> None:
    at = reassignment_open(fakes)
    at = button(at, "Cancel").click().run()
    assert fakes.reassigned == []
    assert [b.label for b in at.button if b.label != "Log out"] == ["Re-assign"]


def test_no_suitable_developer_notifies_and_allows_manual_choice(
    fakes: Fakes,
) -> None:
    fakes.profiles = [
        DeveloperProfile("Peter", open_pull_requests=1),
        DeveloperProfile("Zed", open_pull_requests=1),
    ]
    at = reassignment_open(fakes)
    assert any("manually" in w.value for w in at.warning)
    assert at.selectbox(key="reassign_developer").value is None
    at.selectbox(key="reassign_developer").set_value("Zed").run()
    at = button(at, "Confirm re-assignment").click().run()
    assert fakes.reassigned == [("1", "Zed", "Peter")]


def test_database_failure_keeps_task_assigned_and_not_reported(
    fakes: Fakes,
) -> None:
    fakes.reassign_error = ServiceUnavailable("down")
    at = reassignment_open(fakes)
    at = button(at, "Confirm re-assignment").click().run()
    assert any("not re-assigned" in e.value for e in at.error)
    assert not at.success
    assert any("Currently assigned to:** Peter" in m.value for m in at.markdown)


def test_assignment_history_is_listed_in_order(fakes: Fakes) -> None:
    fakes.tasks = [
        Task(
            "1", "CSV export", "Export it", SPEC, "approved", "Peter", "Hans",
            "2026-11-16T10:00:00Z",
            (
                PreviousAssignment("Hans", "2026-11-16T10:00:00Z", "2026-11-17T10:00:00Z"),
                PreviousAssignment("Zed", "2026-11-17T10:00:00Z", "2026-11-18T10:00:00Z"),
            ),
        )
    ]  # fmt: skip
    at = go_to(open_task_page(), "Tasks")
    lines = [m.value for m in at.markdown if m.value.startswith("- ")]
    assert lines == [
        "- Hans: 2026-11-16 to 2026-11-17",
        "- Zed: 2026-11-17 to 2026-11-18",
    ]


def test_reassignment_notice_is_not_kept_after_leaving_the_page(
    fakes: Fakes,
) -> None:
    at = reassignment_open(fakes)
    at = button(at, "Confirm re-assignment").click().run()
    assert at.success
    at = go_to(go_to(at, "Dashboard"), "Tasks")
    assert not at.success
