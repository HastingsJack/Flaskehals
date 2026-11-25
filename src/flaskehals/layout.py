"""Shared layout helpers."""

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

BUTTON_WIDTH = 2  # relative width of one button column
ROW_WIDTH = 8  # relative width of the whole row


def button_row(count: int) -> list[DeltaGenerator]:
    """Return ``count`` narrow columns so buttons sit close together.

    A trailing spacer column takes the rest of the row; it is not returned.
    """
    spacer = max(1, ROW_WIDTH - BUTTON_WIDTH * count)
    return st.columns([BUTTON_WIDTH] * count + [spacer], gap="small")[:count]
