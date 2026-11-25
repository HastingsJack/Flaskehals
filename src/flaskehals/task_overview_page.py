"""Streamlit page listing the approved tasks, with search and re-assignment.

Presentation only: database access and recommendations come in through
``TaskServices``.
"""

from collections.abc import Sequence

import streamlit as st

from flaskehals.db import DataStoreError
from flaskehals.developer_scoring import AssignmentResult
from flaskehals.models import Task
from flaskehals.reviewer_recommendations import ReviewerRecommendation
from flaskehals.score_view import render_developer_result, render_scores
from flaskehals.task_numbers import format_task_number
from flaskehals.task_search import MAX_QUERY_LENGTH, search_tasks, validate_query
from flaskehals.task_services import TaskServices, evaluate

SEARCH_KEY = "task_search"
REASSIGN_TASK_KEY = "reassign_task_id"
REASSIGN_DEVELOPER_KEY = "reassign_developer"
REASSIGN_RESULT_KEY = "reassign_result"
REASSIGN_ERROR_KEY = "reassign_error"
REASSIGN_NOTICE_KEY = "reassign_notice"

NO_TASKS_MESSAGE = "No approved tasks yet."
NO_MATCH_MESSAGE = "No task found."
REASSIGNED_MESSAGE = "Task '{title}' re-assigned from {old} to {new}."


def _label(task: Task) -> str:
    """Display name: the task number (if any) followed by the title."""
    if task.number is None:
        return task.title
    return f"{format_task_number(task.number)} - {task.title}"


def _date(timestamp: str) -> str:
    """The date part of an ISO timestamp (the time is not shown)."""
    return timestamp[:10]


# --- Re-assignment ------------------------------------------------------------


def _open_reassignment(services: TaskServices, task: Task) -> None:
    _close_reassignment()
    result = evaluate(services, task.title, task.specification, task.assigned_developer)
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
    render_developer_result(result)
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


# --- Task list ----------------------------------------------------------------


def _render_reviews(recommendations: Sequence[ReviewerRecommendation]) -> None:
    for rec in recommendations:
        pr = f"[#{rec.pr_number}]({rec.pr_url})" if rec.pr_url else f"#{rec.pr_number}"
        st.markdown(f"**Pull request {pr}** - recommended {_date(rec.created_at)}")
        if not rec.labelled:
            st.caption("The labels have not been added to GitHub yet.")
        render_scores(rec.candidates, rec.reviewer, rec.notice, "reviewer")


def _render_task(
    services: TaskServices,
    task: Task,
    reviews: Sequence[ReviewerRecommendation],
) -> None:
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
        if reviews:
            st.markdown("**Reviewer recommendation**")
            _render_reviews(reviews)
        if not task.assigned_developer:
            return
        if st.session_state.get(REASSIGN_TASK_KEY) == task.id:
            _render_reassignment(services, task)
        else:
            st.button(
                "Re-assign",
                key=f"reassign_{task.id}",
                on_click=_open_reassignment,
                args=(services, task),
            )


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
    for task in tasks:
        reviews = [r for r in recommendations if r.task_id == task.id]
        _render_task(services, task, reviews)
