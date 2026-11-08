# JCI-BEC Attendance Matcher — Technical overview

## Stack

- Python, Streamlit (UI and hosting on Streamlit Community Cloud)
- `google-genai` for Gemini (primary LLM)
- `httpx` for OpenRouter's OpenAI-compatible chat completions API (fallback LLM)
- `gspread` + `google-auth` for Google Sheets
- `pandas`, `pillow`, `python-dotenv`
- `pytest` for tests

## Setup and run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in GEMINI_API_KEY (and OPENROUTER_API_KEY for the fallback)
streamlit run app.py
pytest                      # all LLM and Sheets calls are mocked; no keys or network needed
```

Without Google Sheets configured, the roster comes from
`data/standard_members.csv` (copy `data/standard_members.example.csv`).

## Configuration

Read from environment variables (`.env` locally), with Streamlit secrets as
the source on Streamlit Cloud. See `.env.example` and
`.streamlit/secrets.toml.example`.

| Variable | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | — (required) | Gemini key |
| `GEMINI_VISION_MODEL` / `GEMINI_TEXT_MODEL` | `gemini-3.8-flash` | Model per task |
| `GEMINI_TIMEOUT_SECONDS` | `120` | Per-call timeout; a timeout triggers the fallback |
| `OPENROUTER_API_KEY` | unset (fallback off) | Enables the OpenRouter fallback |
| `OPENROUTER_MODELS` | `dots-studio/dots-3-note-preview:free` | Comma-separated, tried in order |
| `OPENROUTER_TIMEOUT_SECONDS` | `240` | Per-call timeout |
| `STANDARD_MEMBERS_CSV_PATH` | `data/standard_members.csv` | Local roster fallback |
| `GOOGLE_SHEET_ID` | — | Spreadsheet ID; enables Sheets |
| `GOOGLE_SERVICE_ACCOUNT_JSON_PATH` | `service_account.json` | Local service-account key |
| `SHEETS_*_TAB` | see `core/sheets_client.py` | Tab-name overrides |

Secrets (`.env`, `service_account.json`, `data/standard_members.csv`) are
gitignored.

## Code map

```
app.py                    Streamlit entry point: Steps 1–5 and session state
core/
  llm_client.py           generate(): Gemini first, OpenRouter fallback, empty-response check
  llm_types.py            LLMRequest / LLMResult / LLMCallError
  gemini_client.py        Gemini adapter (config, timeout, 429 retry)
  openrouter_client.py    OpenRouter adapter (messages, JSON mode, retry)
  settings.py             resolve_setting(): env first, then st.secrets
  extraction.py           image → names (vision task)
  dedupe.py               code prefilter + LLM dedup
  matching.py             matching prompt → markdown table
  parsing.py              markdown table → rows
  pasted_names.py         pasted text → names
  members.py              roster loading (Sheets → secrets → CSV)
  activity_catalog.py     Activity Catalog tab
  records.py              attendance row building
  sheets_client.py        Google Sheets client and retry
  branding.py             theme, logo and header
prompts/                  dedupe_prompt.txt, matching_prompt.txt
tests/                    one test file per core module
```

To add or swap an LLM provider, write an adapter with
`generate(LLMRequest) -> LLMResult` that raises `LLMCallError`, then wire it
into `core/llm_client.py`. Callers don't change.

## Operations

- Fallback events are logged: `llm_fallback_triggered` (warning, with the
  Gemini error), `llm_fallback_succeeded` (info) and `llm_fallback_failed`
  (error). On Streamlit Cloud they appear in the app's logs.
- If Gemini fails on every call, check the AI Studio project's quota and
  billing first. A `402 RESOURCE_EXHAUSTED` means prepaid credits ran out.
