"""Streamlit app: get attendee names either by uploading meeting-attendance
screenshots (extracted with a Groq vision model) or by pasting a plain-text
list, dedupe (code prefilter + Groq LLM), review/edit the list, then match
against the standard member roster with the user's matching prompt and
display the results.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.branding import FAVICON_PATH, inject_theme, render_header
from core.dedupe import dedupe_names
from core.extraction import extract_names_from_images
from core.groq_client import GroqCallError
from core.matching import run_matching
from core.members import MembersLoadError, load_standard_members
from core.parsing import MarkdownTableParseError, parse_markdown_table, to_display_rows
from core.pasted_names import parse_pasted_names

st.set_page_config(
    page_title="JCI-BEC Attendance Matcher",
    page_icon=str(FAVICON_PATH),
    layout="wide",
)
inject_theme()
render_header(
    "JCI-BEC Attendance Matcher",
    "Upload meeting-attendance screenshots, or paste a list of names, "
    "then match them against the standard member roster.",
)

for key, default in [
    ("raw_names", []),
    ("extraction_errors", []),
    ("deduped_names", None),
    ("dedupe_warning", None),
    ("match_rows", None),
    ("match_error", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _reset_downstream_state() -> None:
    """Called whenever the raw name list changes (new upload, new paste),
    since dedup/review/match all depend on it and would otherwise show
    stale results from a previous source."""
    st.session_state.deduped_names = None
    st.session_state.dedupe_warning = None
    st.session_state.match_rows = None
    st.session_state.match_error = None


# --- Step 1: get attendee names ------------------------------------------
st.header("1. Provide attendee names")
upload_tab, paste_tab = st.tabs(["📷 Upload Screenshots", "📝 Paste Names"])

with upload_tab:
    uploaded_files = st.file_uploader(
        "Screenshots of the meeting participant list",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
    )
    if st.button("Extract Names", disabled=not uploaded_files, type="primary"):
        files = [(f.getvalue(), f.name) for f in uploaded_files]
        with st.spinner(f"Extracting names from {len(files)} image(s)..."):
            raw_names, errors = extract_names_from_images(files)
        st.session_state.raw_names = raw_names
        st.session_state.extraction_errors = errors
        _reset_downstream_state()

    if st.session_state.extraction_errors:
        with st.expander(
            f"{len(st.session_state.extraction_errors)} file(s) had issues", expanded=False
        ):
            for filename, error in st.session_state.extraction_errors:
                st.warning(error)

with paste_tab:
    pasted_text = st.text_area(
        "Attendee names — one per line, or separated by commas",
        height=180,
        placeholder="G. Raji\nanifat raji\nBob Nobody",
    )
    pasted_names = parse_pasted_names(pasted_text)
    if st.button("Use These Names", disabled=not pasted_names, type="primary"):
        st.session_state.raw_names = pasted_names
        st.session_state.extraction_errors = []
        _reset_downstream_state()

if st.session_state.raw_names:
    st.write(f"{len(st.session_state.raw_names)} raw name(s) ready for deduplication.")
    with st.expander("Show raw names"):
        st.write(st.session_state.raw_names)


# --- Step 2: dedupe + review -------------------------------------------
if st.session_state.raw_names:
    st.header("2. Review deduplicated names")

    if st.session_state.deduped_names is None:
        with st.spinner("Deduplicating..."):
            deduped, warning = dedupe_names(st.session_state.raw_names)
        st.session_state.deduped_names = deduped
        st.session_state.dedupe_warning = warning

    if st.session_state.dedupe_warning:
        st.warning(st.session_state.dedupe_warning)

    st.write(
        f"Found {len(st.session_state.raw_names)} raw name(s) → "
        f"{len(st.session_state.deduped_names)} unique."
    )
    st.caption("Fix any obvious misread before running the match. Add/remove rows as needed.")

    edited_df = st.data_editor(
        pd.DataFrame({"name": st.session_state.deduped_names}),
        num_rows="dynamic",
        use_container_width=True,
        key="deduped_editor",
    )
    confirmed_names = [n.strip() for n in edited_df["name"].tolist() if str(n).strip()]


# --- Step 3: match against standard roster ------------------------------
if st.session_state.raw_names:
    st.header("3. Match against standard member list")

    try:
        standard_list = load_standard_members()
    except MembersLoadError as exc:
        st.error(f"Could not load the standard member list: {exc}")
        st.stop()

    st.caption(f"Loaded {len(standard_list)} standard member name(s).")

    if st.button("Run Matching", disabled=not confirmed_names, type="primary"):
        try:
            with st.spinner("Matching names..."):
                raw_response = run_matching(standard_list, confirmed_names)
            if raw_response is None:
                st.session_state.match_rows = []
                st.session_state.match_error = "No names to match."
            else:
                parsed_rows = parse_markdown_table(raw_response)
                if len(parsed_rows) != len(confirmed_names):
                    st.warning(
                        f"Model returned {len(parsed_rows)} row(s) but "
                        f"{len(confirmed_names)} name(s) were sent — please "
                        "double-check the results below."
                    )
                st.session_state.match_rows = to_display_rows(parsed_rows)
                st.session_state.match_error = None
        except GroqCallError as exc:
            st.session_state.match_rows = None
            st.session_state.match_error = str(exc)
        except MarkdownTableParseError as exc:
            st.session_state.match_rows = None
            st.session_state.match_error = str(exc)
            with st.expander("Raw model response"):
                st.text(raw_response)


# --- Step 4: results ------------------------------------------------------
if st.session_state.match_error:
    st.error(st.session_state.match_error)

if st.session_state.match_rows:
    st.header("4. Results")
    st.caption(
        "Edit any cell to correct a wrong match. A [NO MATCH] in Matched "
        "Standard Name means no roster name fit; Notes explains ambiguous picks."
    )
    results_df = pd.DataFrame(st.session_state.match_rows).drop(columns=["Match"])

    edited_results_df = st.data_editor(
        results_df,
        num_rows="dynamic",
        use_container_width=True,
        key="results_editor",
    )

    st.download_button(
        "Download results as CSV",
        data=edited_results_df.to_csv(index=False).encode("utf-8"),
        file_name="attendance_match_results.csv",
        mime="text/csv",
    )
