"""Streamlit display of a recommendation and the AI's reasoning.

features/tasks/task-ai-only-recommendation-display.feature: only the
recommendation, the notice and the model's reasoning are shown. The rule-based
scores are still computed, stored and sent to the model, but not displayed.
"""

import streamlit as st

from flaskehals.developer_scoring import AssignmentResult


def render_recommendation(
    recommended: str | None,
    notice: str | None,
    role: str,
    reasoning: str | None = None,
) -> None:
    """Show a recommended developer or reviewer. ``role`` is only wording.

    ``reasoning`` is the language model's explanation of its pick; it is None
    when the rule-based fallback was used, and the notice then says so.
    """
    if notice:
        st.warning(notice)
    if recommended:
        st.info(f"Recommended {role}: **{recommended}**")
    if reasoning:
        st.markdown(f"**Why (AI):** {reasoning}")


def render_developer_result(result: AssignmentResult) -> None:
    render_recommendation(
        result.recommended, result.notice, "developer", result.reasoning
    )


def render_reviewer_result(result: AssignmentResult) -> None:
    render_recommendation(
        result.recommended, result.notice, "reviewer", result.reasoning
    )
