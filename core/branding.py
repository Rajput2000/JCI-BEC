"""JCI brand styling for the Streamlit UI.

Colours and the logo come straight from JCI's own 2026 Brand Guidelines
(jci.cc) — JCI Blue #0097D7, JCI Black #130F2D, JCI White, with JCI Navy /
Teal / Yellow as sparing secondary accents. The base theme colours live in
.streamlit/config.toml (Streamlit's native theming); this module handles the
things config.toml can't do: the brand typeface, the logo header, and a
faint logo watermark in the background.
"""

from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

ASSETS_DIR = Path(__file__).parent.parent / "assets"
LOGO_PATH = ASSETS_DIR / "jci_logo.png"
FAVICON_PATH = ASSETS_DIR / "jci_favicon.png"
WATERMARK_PATH = ASSETS_DIR / "jci_watermark.png"

JCI_BLUE = "#0097D7"
JCI_BLACK = "#130F2D"
JCI_NAVY = "#1F4789"
JCI_TEAL = "#57BCBC"
JCI_YELLOW = "#EFC40F"


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def inject_theme() -> None:
    """Loads the JCI brand typeface and a faint logo watermark behind the
    page content. Base colours are set separately in .streamlit/config.toml."""
    watermark_b64 = _b64(WATERMARK_PATH)
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Plus Jakarta Sans', sans-serif;
        }}

        [data-testid="stAppViewContainer"] {{
            background-image: url("data:image/png;base64,{watermark_b64}");
            background-repeat: no-repeat;
            background-position: right -120px bottom -120px;
            background-size: 640px auto;
        }}

        h1, h2, h3 {{
            color: {JCI_BLACK};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header(title: str, caption: str) -> None:
    logo_col, title_col = st.columns([1, 5], vertical_alignment="center")
    with logo_col:
        st.image(str(LOGO_PATH), use_container_width=True)
    with title_col:
        st.title(title)
        st.caption(caption)
