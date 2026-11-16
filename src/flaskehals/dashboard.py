"""Streamlit presentation of the developer overview."""

import streamlit as st

from flaskehals.developers import DeveloperOverview, resolve_picture

EMPTY_MESSAGE = "No developers found. Run the GitHub sync to import them."
TASKS_NOTE = "Approved tasks assigned to this developer."


def render_developer_overview(developers: list[DeveloperOverview]) -> None:
    st.subheader("Developers")
    if not developers:
        st.info(EMPTY_MESSAGE)
        return
    for developer in developers:
        with st.container(border=True):
            picture, name, open_prs, reviews, tasks = st.columns([1, 3, 2, 2, 2])
            picture.image(str(resolve_picture(developer.picture)), width=64)
            name.markdown(f"**{developer.name}**")
            open_prs.metric("Open PRs", developer.open_pull_requests)
            reviews.metric("Assigned for review", developer.review_assignments)
            tasks.metric("Assigned tasks", developer.assigned_tasks, help=TASKS_NOTE)
