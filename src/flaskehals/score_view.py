"""Streamlit display of a recommendation and the reasoning behind it."""

from collections.abc import Sequence

import streamlit as st

from flaskehals.developer_scoring import AssignmentResult, DeveloperScore


def render_scores(
    scores: Sequence[DeveloperScore],
    recommended: str | None,
    notice: str | None,
    role: str,
) -> None:
    """Show a recommendation and the reasoning behind every candidate's score.

    Developer and reviewer recommendations use the same scoring, so both are
    explained the same way. ``role`` is only used in the wording.
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


def render_developer_result(result: AssignmentResult) -> None:
    render_scores(result.scores, result.recommended, result.notice, "developer")
