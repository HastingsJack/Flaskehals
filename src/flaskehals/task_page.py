"""Streamlit pages for task creation and the task overview.

Presentation only: generation and database access come in through
``TaskServices``. State changes happen in button callbacks, which run before
the widgets are drawn and so may safely set widget values.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import streamlit as st

from flaskehals.assignment import (
    AssignmentResult,
    DeveloperProfile,
    DeveloperScore,
    recommend_developer,
)
from flaskehals.reviewer_recommendations import ReviewerRecommendation
from flaskehals.specification import (
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    SpecificationError,
    validate_feedback,
    validate_task_input,
)
from flaskehals.task_numbers import format_task_number
from flaskehals.task_search import MAX_QUERY_LENGTH, search_tasks, validate_query
from flaskehals.tasks import DataStoreError, NewTask, Task

TITLE_KEY = "task_title"
DESCRIPTION_KEY = "task_description"
DRAFT_KEY = "task_draft"
SPEC_KEY = "task_spec"
FEEDBACK_KEY = "task_feedback"
DEVELOPER_KEY = "task_developer"
ERROR_KEY = "task_error"
NOTICE_KEY = "task_notice"
REASSIGN_TASK_KEY = "reassign_task_id"
REASSIGN_DEVELOPER_KEY = "reassign_developer"
REASSIGN_RESULT_KEY = "reassign_result"
REASSIGN_ERROR_KEY = "reassign_error"
REASSIGN_NOTICE_KEY = "reassign_notice"
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
NO_TASKS_MESSAGE = "No approved tasks yet."
NO_MATCH_MESSAGE = "No task found."
SEARCH_KEY = "task_search"
REASSIGNED_MESSAGE = "Task '{title}' re-assigned from {old} to {new}."


@dataclass(frozen=True)
class TaskServices:
    generate: Callable[[str, str, str | None, str | None], str] | None
    load_profiles: Callable[[], list[DeveloperProfile]]
    save_task: Callable[[NewTask], str]
    load_tasks: Callable[[], list[Task]]
    # (task id, new developer, assignee the caller saw)
    reassign_task: Callable[[str, str, str], None]
    load_recommendations: Callable[[], list[ReviewerRecommendation]]


@dataclass(frozen=True)
class TaskDraft:
    title: str
    description: str
    result: AssignmentResult


def keep_draft_state() -> None:
    """Streamlit drops widget state on pages not drawn; re-assign it to keep it."""
    for key in PERSISTED_KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]


def _evaluate(
    services: TaskServices,
    title: str,
    specification: str,
    exclude: str | None = None,
) -> AssignmentResult:
    try:
        profiles = services.load_profiles()
    except DataStoreError as exc:
        return AssignmentResult(scores=(), recommended=None, notice=str(exc))
    return recommend_developer(profiles, title, specification, exclude)


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
    problem = validate_task_input(title, description)
    if problem or services.generate is None:
        st.session_state[ERROR_KEY] = problem or OPENROUTER_CONFIG_ERROR
        return
    try:
        specification = services.generate(title, description, None, None)
    except SpecificationError as exc:
        st.session_state[ERROR_KEY] = str(exc)
        return
    result = _evaluate(services, title, specification)
    draft = TaskDraft(title.strip(), description, result)
    st.session_state[DRAFT_KEY] = draft
    st.session_state[SPEC_KEY] = specification
    st.session_state[FEEDBACK_KEY] = ""
    st.session_state[DEVELOPER_KEY] = result.recommended


def _regenerate(services: TaskServices) -> None:
    st.session_state.pop(ERROR_KEY, None)
    draft: TaskDraft = st.session_state[DRAFT_KEY]
    current = st.session_state.get(SPEC_KEY, "")
    feedback = st.session_state.get(FEEDBACK_KEY, "")
    problem = validate_feedback(feedback)
    if problem or services.generate is None:
        st.session_state[ERROR_KEY] = problem or OPENROUTER_CONFIG_ERROR
        return
    try:
        specification = services.generate(
            draft.title, draft.description, current, feedback
        )
    except SpecificationError as exc:
        st.session_state[ERROR_KEY] = str(exc)
        return
    result = _evaluate(services, draft.title, specification)
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
    _render_recommendation(draft)
    names = [score.name for score in draft.result.scores]
    st.selectbox(
        "Assign to",
        options=names,
        index=None,
        placeholder="Select a developer",
        key=DEVELOPER_KEY,
        disabled=not names,
    )
    approve, reject = st.columns(2)
    approve.button(
        "Approve and save task",
        type="primary",
        on_click=_approve,
        args=(services,),
        disabled=not names,
    )
    reject.button("Reject task", on_click=_reject)


def _render_recommendation(draft: TaskDraft) -> None:
    result = draft.result
    _render_scores(result.scores, result.recommended, result.notice, "developer")


def _render_scores(
    scores: Sequence[DeveloperScore],
    recommended: str | None,
    notice: str | None,
    role: str,
) -> None:
    """Show a recommendation and the reasoning behind every candidate's score.

    Shared by developer and reviewer recommendations, which use the same
    scoring, so both are explained the same way.
    """
    if notice:
        st.warning(notice)
    if recommended:
        st.info(f"Recommended {role}: **{recommended}**")
    if scores:
        with st.expander(f"How the {role} recommendation was scored"):
            for score in scores:
                st.markdown(f"**{score.name}** - {score.total:.1f}/100")
                for line in score.explanation:
                    st.markdown(f"- {line}")


def _render_reviews(recommendations: Sequence[ReviewerRecommendation]) -> None:
    for rec in recommendations:
        pr = f"[#{rec.pr_number}]({rec.pr_url})" if rec.pr_url else f"#{rec.pr_number}"
        st.markdown(f"**Pull request {pr}** - recommended {_date(rec.created_at)}")
        if not rec.labelled:
            st.caption("The labels have not been added to GitHub yet.")
        _render_scores(rec.candidates, rec.reviewer, rec.notice, "reviewer")


def _open_reassignment(services: TaskServices, task: Task) -> None:
    _close_reassignment()
    result = _evaluate(
        services, task.title, task.specification, task.assigned_developer
    )
    st.session_state[REASSIGN_TASK_KEY] = task.id
    st.session_state[REASSIGN_RESULT_KEY] = result
    st.session_state[REASSIGN_DEVELOPER_KEY] = result.recommended


def _close_reassignment() -> None:
    for key in (
        REASSIGN_TASK_KEY,
        REASSIGN_DEVELOPER_KEY,
        REASSIGN_RESULT_KEY,
        REASSIGN_ERROR_KEY,
        REASSIGN_NOTICE_KEY,
    ):
        st.session_state.pop(key, None)


def _confirm_reassignment(services: TaskServices, task: Task) -> None:
    st.session_state.pop(REASSIGN_ERROR_KEY, None)
    selected = st.session_state.get(REASSIGN_DEVELOPER_KEY)
    if not selected:
        st.session_state[REASSIGN_ERROR_KEY] = "Select a developer to re-assign to."
        return
    if selected == task.assigned_developer:
        st.session_state[REASSIGN_ERROR_KEY] = f"{selected} is already assigned."
        return
    try:
        services.reassign_task(task.id, selected, task.assigned_developer or "")
    except DataStoreError as exc:
        st.session_state[REASSIGN_ERROR_KEY] = f"The task was not re-assigned. {exc}"
        return
    _close_reassignment()
    st.session_state[REASSIGN_NOTICE_KEY] = REASSIGNED_MESSAGE.format(
        title=task.title, old=task.assigned_developer, new=selected
    )


def _render_reassignment(services: TaskServices, task: Task) -> None:
    result: AssignmentResult = st.session_state[REASSIGN_RESULT_KEY]
    st.markdown(f"**Task:** {_label(task)}")
    st.markdown(f"**Currently assigned to:** {task.assigned_developer}")
    if error := st.session_state.get(REASSIGN_ERROR_KEY):
        st.error(error)
    _render_recommendation(TaskDraft(task.title, task.description, result))
    names = [score.name for score in result.scores]
    st.selectbox(
        "Re-assign to",
        options=names,
        index=None,
        placeholder="Select a developer",
        key=REASSIGN_DEVELOPER_KEY,
        format_func=lambda name: (
            f"{name} (current)" if name == task.assigned_developer else name
        ),
        disabled=not names,
    )
    confirm, cancel = st.columns(2)
    confirm.button(
        "Confirm re-assignment",
        type="primary",
        key=f"confirm_{task.id}",
        on_click=_confirm_reassignment,
        args=(services, task),
        disabled=not names,
    )
    cancel.button("Cancel", key=f"cancel_{task.id}", on_click=_close_reassignment)


def _label(task: Task) -> str:
    """Display name: the task number (if any) followed by the title."""
    if task.number is None:
        return task.title
    return f"{format_task_number(task.number)} - {task.title}"


def _date(timestamp: str) -> str:
    """The date part of an ISO timestamp (the time is not shown)."""
    return timestamp[:10]


def render_task_overview(services: TaskServices) -> None:
    st.title("Tasks")
    try:
        tasks = services.load_tasks()
    except DataStoreError as exc:
        st.error(str(exc))
        return
    try:
        recommendations = services.load_recommendations()
    except DataStoreError:
        recommendations = []  # the tasks themselves are still worth showing
    # Shown once: consumed here so it is gone when the page is left and revisited.
    if notice := st.session_state.pop(REASSIGN_NOTICE_KEY, None):
        st.success(notice)
    if not tasks:
        st.info(NO_TASKS_MESSAGE)
        return
    query = st.text_input(
        "Search tasks",
        key=SEARCH_KEY,
        max_chars=MAX_QUERY_LENGTH,
        placeholder="Task number, title or developer",
    )
    if problem := validate_query(query):
        st.error(problem)
        return
    tasks = search_tasks(tasks, query)
    if not tasks:
        st.info(NO_MATCH_MESSAGE)
        return
    reassigning = st.session_state.get(REASSIGN_TASK_KEY)
    for task in tasks:
        assignee = task.assigned_developer or "unassigned"
        with st.expander(f"{_label(task)} - {assignee}"):
            st.markdown(f"**Assigned to:** {assignee}")
            if task.recommended_developer:
                st.markdown(f"**Originally recommended:** {task.recommended_developer}")
            st.markdown("**Description**")
            st.text(task.description)
            st.markdown("**Technical specification**")
            st.markdown(task.specification)
            if task.previous_assignments:
                st.markdown("**Assignment history**")
                for item in task.previous_assignments:
                    st.markdown(
                        f"- {item.developer}: {_date(item.assigned_at)} to "
                        f"{_date(item.unassigned_at)}"
                    )
            reviews = [r for r in recommendations if r.task_id == task.id]
            if reviews:
                st.markdown("**Reviewer recommendation**")
                _render_reviews(reviews)
            if not task.assigned_developer:
                continue
            if reassigning == task.id:
                _render_reassignment(services, task)
            else:
                st.button(
                    "Re-assign",
                    key=f"reassign_{task.id}",
                    on_click=_open_reassignment,
                    args=(services, task),
                )
