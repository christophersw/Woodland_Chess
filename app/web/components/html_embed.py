from __future__ import annotations

import base64

import streamlit as st
import streamlit.components.v1 as components


def render_html_iframe(html: str, *, height: int, scrolling: bool = False) -> None:
    """Render arbitrary HTML with backward compatibility across Streamlit versions."""
    # Newer Streamlit versions expose st.iframe; older versions require components.v1.html.
    if hasattr(st, "iframe"):
        encoded = base64.b64encode(html.encode("utf-8")).decode("ascii")
        src = f"data:text/html;charset=utf-8;base64,{encoded}"
        # Streamlit's st.iframe does not support a `scrolling` kwarg.
        _ = scrolling
        st.iframe(src, height=height)
        return

    components.html(html, height=height, scrolling=scrolling)
