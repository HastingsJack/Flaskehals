"""Streamlit page for creating a task: specification, assignment, approval.

Presentation only: generation and database access come in through
``TaskServices``. State changes happen in button callbacks, which run before
the widgets are drawn and so may safely set widget values.
"""

from dataclasses import dataclass

import streamlit as st

from flaskehals.db import DataStoreError
from flaskehals.developer_scoring import AssignmentResult
from flaskehals.layout import button_row
from flaskehals.models import NewTask
from flaskehals.score_view import render_developer_result
from flaskehals.specification import SpecificationError
from flaskehals.task_input import (
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    validate_feedback,
    validate_task_input,
)
from flaskehals.task_services import TaskServices, evaluate

TITLE_KEY = "task_title"
DESCRIPTION_KEY = "task_description"
DRAFT_KEY = "task_draft"
SPEC_KEY = "task_spec"
FEEDBACK_KEY = "task_feedback"
DEVELOPER_KEY = "task_developer"
ERROR_KEY = "task_error"
NOTICE_KEY = "task_notice"
PERSISTED_KEYS = (
    TITLE_KEY,
    DESCRIPTION_KEY,
    DRAFT_KEY,
    SPEC_KEY,
    FEEDBACK_KEY,
    DEVELOPER_KEY,
)

OPENROUTER_CONFIG_ERROR = (
    "Specification generation is not configured. Set OPENROUTER_API_KEY."
)
SAVED_MESSAGE = "Task saved and assigned to {developer}."
REJECTED_MESSAGE = "Task rejected and not saved. Your description is still here."


@dataclass(frozen=True)
class TaskDraft:
    """The task as it was when its specification was generated."""

    title: str
    description: str
    result: AssignmentResult


def keep_draft_state() -> None:
    """Streamlit drops widget state on pages not drawn; re-assign it to keep it."""
    for key in PERSISTED_KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def _generate_specification(
    services: TaskServices,
    title: str,
    description: str,
    current: str | None,
    feedback: str | None,
) -> str | None:
    """Call the generator. On failure show the error and return None."""
    if services.generate is None:
        st.session_state[ERROR_KEY] = OPENROUTER_CONFIG_ERROR
        return None
    try:
        return services.generate(title, description, current, feedback)
    except SpecificationError as exc:
        st.session_state[ERROR_KEY] = str(exc)
        return None


def _apply_evaluation(draft: TaskDraft, previous: str | None) -> None:
    """Follow the recommendation unless the project manager chose someone else."""
    selected = st.session_state.get(DEVELOPER_KEY)
    names = {score.name for score in draft.result.scores}
    if selected is None or selected == previous or selected not in names:
        st.session_state[DEVELOPER_KEY] = draft.result.recommended


def _generate(services: TaskServices) -> None:
    st.session_state.pop(ERROR_KEY, None)
    st.session_state.pop(NOTICE_KEY, None)
    title = st.session_state.get(TITLE_KEY, "")
    description = st.session_state.get(DESCRIPTION_KEY, "")
    if problem := validate_task_input(title, description):
        st.session_state[ERROR_KEY] = problem
        return
    specification = _generate_specification(services, title, description, None, None)
    if specification is None:
        return
    result = evaluate(services, title, specification)
    st.session_state[DRAFT_KEY] = TaskDraft(title.strip(), description, result)
    st.session_state[SPEC_KEY] = specification
    st.session_state[FEEDBACK_KEY] = ""
    st.session_state[DEVELOPER_KEY] = result.recommended


def _regenerate(services: TaskServices) -> None:
    st.session_state.pop(ERROR_KEY, None)
    draft: TaskDraft = st.session_state[DRAFT_KEY]
    current = st.session_state.get(SPEC_KEY, "")
    feedback = st.session_state.get(FEEDBACK_KEY, "")
    if problem := validate_feedback(feedback):
        st.session_state[ERROR_KEY] = problem
        return
    specification = _generate_specification(
        services, draft.title, draft.description, current, feedback
    )
    if specification is None:
        return
    result = evaluate(services, draft.title, specification)
    updated = TaskDraft(draft.title, draft.description, result)
    st.session_state[DRAFT_KEY] = updated
    st.session_state[SPEC_KEY] = specification
    st.session_state[FEEDBACK_KEY] = ""
    _apply_evaluation(updated, draft.result.recommended)


def _approve(services: TaskServices) -> None:
    st.session_state.pop(ERROR_KEY, None)
    draft: TaskDraft = st.session_state[DRAFT_KEY]
    specification = st.session_state.get(SPEC_KEY, "").strip()
    developer = st.session_state.get(DEVELOPER_KEY)
    if not specification:
        st.session_state[ERROR_KEY] = "The specification must not be empty."
        return
    if not developer:
        st.session_state[ERROR_KEY] = "Select a developer before approving."
        return
    task = NewTask(
        title=draft.title,
        description=draft.description,
        specification=specification,
        assigned_developer=developer,
        recommended_developer=draft.result.recommended,
    )
    try:
        services.save_task(task)
    except DataStoreError as exc:
        st.session_state[ERROR_KEY] = f"The task was not saved. {exc}"
        return
    _clear_draft()
    st.session_state[TITLE_KEY] = ""
    st.session_state[DESCRIPTION_KEY] = ""
    st.session_state[NOTICE_KEY] = SAVED_MESSAGE.format(developer=developer)


def _reject() -> None:
    st.session_state.pop(ERROR_KEY, None)
    _clear_draft()
    st.session_state[NOTICE_KEY] = REJECTED_MESSAGE


def _clear_draft() -> None:
    for key in (DRAFT_KEY, SPEC_KEY, FEEDBACK_KEY, DEVELOPER_KEY):
        st.session_state.pop(key, None)


def render_task_creation(services: TaskServices) -> None:
    st.title("New task")
    if services.generate is None:
        st.error(OPENROUTER_CONFIG_ERROR)
    if notice := st.session_state.get(NOTICE_KEY):
        st.success(notice)
    if error := st.session_state.get(ERROR_KEY):
        st.error(error)

    draft: TaskDraft | None = st.session_state.get(DRAFT_KEY)
    locked = draft is not None
    st.text_input(
        "Task title", key=TITLE_KEY, max_chars=MAX_TITLE_LENGTH, disabled=locked
    )
    st.text_area(
        "Task description",
        key=DESCRIPTION_KEY,
        max_chars=MAX_DESCRIPTION_LENGTH,
        height=150,
        disabled=locked,
    )
    if draft is None:
        st.button(
            "Generate specification",
            on_click=_generate,
            args=(services,),
            disabled=services.generate is None,
        )
        return
    _render_draft(services, draft)


def _render_draft(services: TaskServices, draft: TaskDraft) -> None:
    st.subheader("Technical specification")
    st.text_area("Specification (editable)", key=SPEC_KEY, height=420)
    st.text_area(
        "Feedback for regeneration (optional)",
        key=FEEDBACK_KEY,
        help="Regeneration uses your original description, the specification "
        "above (including your edits) and this feedback.",
    )
    st.button(
        "Regenerate specification",
        on_click=_regenerate,
        args=(services,),
        disabled=services.generate is None,
    )

    st.subheader("Assignment")
    render_developer_result(draft.result)
    names = [score.name for score in draft.result.scores]
    st.selectbox(
        "Assign to",
        options=names,
        index=None,
        placeholder="Select a developer",
        key=DEVELOPER_KEY,
        disabled=not names,
    )
    approve, reject = button_row(2)
    approve.button(
        "Approve and save task",
        type="primary",
        on_click=_approve,
        args=(services,),
        disabled=not names,
    )
    reject.button("Reject task", on_click=_reject)
