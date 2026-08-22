# JCI-BEC Attendance Matcher

Upload meeting-attendance screenshots, extract attendee names with a Gemini
vision model, deduplicate them, then match them against the standard member
roster using a matching prompt — all reviewed in a Streamlit table.

## Pipeline

1. Upload one or more screenshots of the meeting's participant list.
2. A Gemini vision model (`GEMINI_VISION_MODEL`) extracts attendee names from each image.
3. Names are deduplicated in two stages: a cheap code-level pass for exact/
   case/whitespace duplicates, then a Gemini text-model call
   (`GEMINI_TEXT_MODEL`) that merges any remaining near-duplicate spellings
   (OCR noise, inconsistent spacing) — but never nickname/initials
   consolidation, which stays with the matching step.
4. You review/edit the deduplicated list before matching runs.
5. The standard member list is loaded from `data/standard_members.csv`.
6. The matching prompt (`prompts/matching_prompt.txt`, kept verbatim) is run
   against the Gemini text model, producing a markdown table — one row per
   matched person (every meeting-name variant that maps to them consolidated
   into that row), with a Match Certainty tier and Notes, or `[NO MATCH]`.
7. Results are displayed as Extracted Name(s) / Matched Standard Name /
   Match Certainty / Notes, editable, and can be downloaded as CSV.

## Project layout

```
app.py              # Streamlit entry point (run this with `streamlit run`)
core/                # supporting library code
├── gemini_client.py  # Gemini client, model config, retry/error handling
├── members.py         # loads data/standard_members.csv (CSV→Form seam)
├── extraction.py       # vision extraction from screenshots
├── dedupe.py            # prefilter + LLM-based dedup
├── matching.py           # matching prompt + Gemini call
└── parsing.py             # markdown table → structured rows
prompts/             # LLM prompt templates (matching_prompt.txt, dedupe_prompt.txt)
data/                # data/standard_members.csv
tests/               # pytest suite, mocks the Gemini client
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)
cp data/standard_members.example.csv data/standard_members.csv   # then fill in real names
```

**Privacy note:** `data/standard_members.csv` (the real roster) is gitignored and
must never be committed — it's personal data. Only
`data/standard_members.example.csv` (placeholder names) is tracked in git, so
the repo documents the expected format without exposing anyone's name. If
you'd rather the file not even live inside the project folder, point
`STANDARD_MEMBERS_CSV_PATH` (see Configuration below) at a path outside the
repo entirely, e.g. `~/jci-bec/standard_members.csv` — the app doesn't care
where the file lives, only that the env var points at it.

## Run

```bash
streamlit run app.py
```

## Deploying to Streamlit Community Cloud

Streamlit Cloud rebuilds the app from your GitHub repo on every deploy, so
there's no separate place to "upload" a file outside of git — instead, use
**Secrets** (Settings → Secrets in the app's dashboard on
[share.streamlit.io](https://share.streamlit.io)), which is made exactly for
config/data the deployed app needs that the repo itself shouldn't contain.

1. Push the repo as normal — `data/standard_members.csv` stays out of it
   (it's gitignored), so nothing private goes to GitHub.
2. In the Streamlit Cloud dashboard for the deployed app, open
   **Settings → Secrets** and paste in something shaped like
   `.streamlit/secrets.toml.example` — `GEMINI_API_KEY`, optionally
   `GEMINI_VISION_MODEL` / `GEMINI_TEXT_MODEL`, plus a `[data]` section with
   the real roster as a `standard_members_csv` multi-line string.
3. Save. `core.members.load_standard_members()` already checks
   `st.secrets` first and only falls back to the local file if secrets
   aren't set — no code changes needed, the same app runs either way.
   The model overrides work too: Streamlit Cloud auto-injects any
   top-level secret (everything above `[data]`) into `os.environ`, which
   is exactly what `core/gemini_client.py`'s `os.getenv(...)` calls read.
   Only nested keys like `standard_members_csv` need `st.secrets`
   specifically — which is why the roster sits under `[data]` and the
   rest doesn't.

The real roster's contents only ever exist in: your local machine, and the
Streamlit Cloud dashboard's secrets store (which itself never appears in
your git history, your repo, or any diff).

## Configuration

All of these are optional overrides — see `.env.example`:

- `GEMINI_API_KEY` — required. Get one at <https://aistudio.google.com/apikey>.
- `GEMINI_VISION_MODEL` / `GEMINI_TEXT_MODEL` — Google's hosted model lineup
  changes over time; if a default here is deprecated, set the env var
  instead of editing code. Check <https://ai.google.dev/gemini-api/docs/models>.
  Gemini models are natively multimodal, so both default to the same model —
  these only need to differ if you want a cheaper/faster model for one step.
- `STANDARD_MEMBERS_CSV_PATH` — defaults to `data/standard_members.csv`.
  Set this to an absolute path outside the repo if you'd rather the real
  roster not live in the project folder at all.

## Swapping the standard member list source

`core.members.load_standard_members()` is the single seam for this data. It
currently reads a CSV — from Streamlit secrets if set, else from a local
file — re-read fresh on every app run. When this needs to come from Google
Form responses instead, only the body of that function needs to change —
every caller (`app.py`) stays the same.

## Tests

```bash
pytest
```

Unit tests mock the Gemini client, so they don't require an API key or make
network calls.

## Known limitations

- Vision extraction accuracy on dense or scrolled participant-list
  screenshots hasn't been fully validated at scale — upload multiple images
  to cover a scrolled list, and use the review/edit step to fix any obvious
  misread before matching runs.
- The LLM dedup step can occasionally over- or under-merge names; review it
  before matching.
- Both the vision and text steps use Gemini "thinking" models, which can in
  principle spend their whole token budget reasoning and return an empty
  response on an unusually large/complex request (large roster, big meeting
  batch). Thinking is capped or disabled per-step specifically to avoid
  this, and any occurrence surfaces as a clear error naming the cause
  (`finish_reason`) rather than a silent empty result — but if you hit it,
  try again or split the batch smaller.
- If a matching run's row count doesn't account for the number of names
  sent, the app shows a warning — check the table carefully in that case.

## Why Gemini, not Groq

This app originally used Groq. It migrated to Gemini because Groq's
free-tier rate limit for the models in use (8,000 tokens/minute, shared
across prompt + output) was too tight for this workload — a 150+ name
roster plus a full matching-table response routinely got close to or over
that ceiling, and was the direct cause of a couple of real failures during
development (a token-budget-exhaustion bug and a request-too-large error).
Gemini's free tier has substantially more headroom for the same kind of
work. If Groq's limits or lineup change and its speed advantage (LPU
hardware) becomes worth it again, `core/gemini_client.py` is the single
place that would need swapping back.
