"""Gradient page background.

Streamlit's native theme (.streamlit/config.toml) only supports flat colors, so
the gradient is a single CSS rule. The flat theme background remains the
fallback if the CSS is not applied.
"""

import streamlit as st

GRADIENT_ANGLE_DEG = 135
GRADIENT_STOPS: tuple[str, ...] = ("#FFFFFF", "#EAF3FF", "#D6E8FF")
APP_SELECTOR = '[data-testid="stApp"]'


def build_background_css() -> str:
    stops = ", ".join(GRADIENT_STOPS)
    return (
        f"<style>{APP_SELECTOR} {{"
        f" background: linear-gradient({GRADIENT_ANGLE_DEG}deg, {stops});"
        " background-attachment: fixed; }</style>"
    )


def apply_background() -> None:
    st.markdown(build_background_css(), unsafe_allow_html=True)
