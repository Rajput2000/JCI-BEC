"""Streamlit app: get attendee names either by uploading meeting-attendance
screenshots (extracted with a Gemini vision model) or by pasting a plain-text
list, dedupe (code prefilter + Gemini LLM), review/edit the list, then match
against the standard member roster with the user's matching prompt and
display the results.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.branding import FAVICON_PATH, inject_theme, render_header
from core.dedupe import dedupe_names
from core.extraction import extract_names_from_images
from core.gemini_client import GeminiCallError
from core.matching import run_matching
from core.members import MembersLoadError, load_standard_members
from core.parsing import (
    MarkdownTableParseError,
    count_meeting_names,
    parse_markdown_table,
    to_display_rows,
)
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
    ("input_reset_counter", 0),
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


def _clear_all() -> None:
    """Full reset: wipes the accumulated name list and all downstream state,
    and bumps input_reset_counter so the uploader/paste-box widgets — which
    are keyed off it — get recreated empty instead of keeping stale content."""
    st.session_state.raw_names = []
    st.session_state.extraction_errors = []
    st.session_state.input_reset_counter += 1
    _reset_downstream_state()


# --- Step 1: get attendee names ------------------------------------------
st.header("1. Provide attendee names")
st.caption(
    "Upload screenshots and/or paste names — each action ADDS to the "
    "combined list below rather than replacing it, so you can mix both. "
    "Use Clear All to start over."
)
upload_tab, paste_tab = st.tabs(["📷 Upload Screenshots", "📝 Paste Names"])

with upload_tab:
    uploaded_files = st.file_uploader(
        "Screenshots of the meeting participant list",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=f"uploader_{st.session_state.input_reset_counter}",
    )
    if st.button("Extract Names", disabled=not uploaded_files, type="primary"):
        files = [(f.getvalue(), f.name) for f in uploaded_files]
        total = len(files)
        progress_bar = st.progress(0.0, text=f"Extracting names — 0 of {total} done...")

        def _update_progress(completed: int, completed_total: int, filename: str) -> None:
            left = completed_total - completed
            progress_bar.progress(
                completed / completed_total,
                text=(
                    f"Extracting names — {completed} of {completed_total} done "
                    f"({left} left) — just finished {filename}"
                ),
            )

        new_names, errors = extract_names_from_images(files, on_progress=_update_progress)
        progress_bar.empty()
        st.session_state.raw_names += new_names
        st.session_state.extraction_errors += errors
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
        key=f"paste_area_{st.session_state.input_reset_counter}",
    )
    pasted_names = parse_pasted_names(pasted_text)
    if st.button("Add These Names", disabled=not pasted_names, type="primary"):
        st.session_state.raw_names += pasted_names
        _reset_downstream_state()

if st.session_state.raw_names:
    names_col, clear_col = st.columns([5, 1])
    with names_col:
        st.write(f"{len(st.session_state.raw_names)} raw name(s) ready for deduplication.")
    with clear_col:
        # on_click, not the usual "if st.button(...)" pattern used elsewhere
        # in this file: the callback runs *before* the script re-executes
        # top-to-bottom, so the counter bump is already in effect by the
        # time the (earlier-in-the-script) uploader/paste-box widgets are
        # rendered — an inline "if st.button(...): _clear_all()" here would
        # clear state too late for that same run to show it.
        st.button("Clear All", width="stretch", on_click=_clear_all)
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
                # Rows are expected to come back fewer than names sent — the
                # prompt consolidates every meeting-name variant that maps to
                # the same person into one row. So the real sanity check is
                # against the total *names* across all rows, not row count.
                returned_name_count = count_meeting_names(parsed_rows)
                if returned_name_count != len(confirmed_names):
                    st.warning(
                        f"Model's table accounts for {returned_name_count} "
                        f"name(s) but {len(confirmed_names)} were sent — "
                        "please double-check the results below."
                    )
                st.session_state.match_rows = to_display_rows(parsed_rows)
                st.session_state.match_error = None
        except GeminiCallError as exc:
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
        "One row per matched person — Extracted Name(s) lists every meeting-list "
        "variant that matched them (pipe-separated). A [NO MATCH] in Matched "
        "Standard Name means no roster name fit; each unmatched name keeps its "
        "own row. Match Certainty and Notes come straight from the model — "
        "edit any cell to correct a wrong match."
    )
    results_df = pd.DataFrame(st.session_state.match_rows)

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
