from __future__ import annotations

import base64

import streamlit as st


def render_html_iframe(html: str, *, height: int, scrolling: bool = False) -> None:
    """Render arbitrary HTML in an iframe without using deprecated components.v1.html."""
    encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
    src = f"data:text/html;base64,{encoded}"
    st.iframe(src, height=height, scrolling=scrolling)
