# JCI-BEC Attendance Matcher — Product

## What it is

A Streamlit web app that turns a meeting's attendance into rows on the
chapter's Google Sheets attendance log. A user uploads screenshots of a
video call's participant list (Zoom, Teams) or pastes a list of names; the
app reads the names, removes duplicates, matches each one to the official
member roster, and appends the matched attendance to the sheet.

**Problem it solves:** matching meeting display names ("G. Raji", "anifat
raji", "iPhone") to official member names by hand is slow and error-prone,
especially for a 150+ member roster.

**Who it's for:** the JCI-BEC officer who records attendance and points
after each meeting.

## Features

### 1. Provide attendee names
- **Upload screenshots:** one or more PNG/JPG/WEBP images. Each image is
  downsized (longest side ≤ 2000px), re-encoded as JPEG and sent to a vision
  LLM that returns the visible names as JSON. UI labels ("Participants (24)",
  "Mute All") and suffixes like "(Host)" are dropped. A progress bar shows
  "N of M done". An unreadable image or a failed call skips that file and is
  listed under "file(s) had issues"; the rest of the batch continues.
- **Paste names:** one per line or comma-separated.
- Both actions *add* to one combined list. **Clear All** resets everything.

### 2. Review deduplicated names
Two-stage dedup runs automatically:
1. Code-level: exact, case and whitespace duplicates (first-seen casing wins).
2. LLM (`prompts/dedupe_prompt.txt`): near-duplicate spellings such as OCR
   noise. It never merges nicknames or initials; that is left to matching.

If the LLM step fails, the stage-1 list is shown with a warning instead of
stopping. The user edits the list (add/remove/fix rows) before matching.

### 3. Match against the standard member list
The roster loads from the Google Sheet's Member Directory tab, or from
Streamlit secrets / a local CSV when Sheets isn't configured. **Run
Matching** sends the roster and the confirmed names to the LLM with
`prompts/matching_prompt.txt`, which returns a markdown table: one row per
matched person with every meeting-name variant consolidated, a Match
Certainty tier and Notes, or `[NO MATCH]`. If the table accounts for a
different number of names than were sent, a warning appears.

### 4. Results
Editable table (Extracted Name(s) / Matched Standard Name / Match Certainty
/ Notes) with CSV download.

### 5. Post attendance to Google Sheets
Shown only when Sheets is configured. Pick an Activity (from the Activity
Catalog tab) and a Month → **Preview** builds the rows → **Publish to
Sheet** appends them to the Raw Data tab. `[NO MATCH]` rows are always
skipped. Changing Activity/Month or editing Results after previewing
disables Publish until the user previews again.

### AI provider fallback
Every LLM call (extraction, dedup, matching) goes to Gemini first. If
Gemini fails, the same request is sent to OpenRouter, and the user sees a
toast: "Gemini is unavailable — using the backup model. This step may take
1–2 minutes." The fallback is enabled only when `OPENROUTER_API_KEY` is set.

## Flows

### User journey

```
Upload screenshots ─┐
                    ├─► combined raw names ─► dedup ─► user review/edit
Paste names ────────┘                                       │
                                                            ▼
             Google Sheet ◄─ Publish ◄─ Preview ◄─ results ◄─ Run Matching
             (Raw Data tab)                        (editable, CSV)
```

### LLM call flow (every AI step)

```
caller (extraction / dedupe / matching)
   │  LLMRequest(task, prompt, system_prompt?, image?, json_schema?, token limits)
   ▼
llm_client.generate
   │
   ├─► Gemini (timeout 120s, retries 429 twice: 2s, 4s)
   │      ok + non-empty text ──────────────────────────────► return result
   │      error / timeout / missing key / empty text
   │           │
   │           ├─ OPENROUTER_API_KEY not set ──► raise LLMCallError (Gemini's error)
   │           ▼
   ├─► toast + warning log, then OpenRouter (timeout 240s,
   │   one retry on 429/5xx/network error, models tried in order)
   │      ok + non-empty text ──────────────────────────────► return result
   │      error / empty text ──► raise LLMCallError("Both AI providers failed. …")
   ▼
caller turns LLMCallError into its own behavior:
  extraction → skips that file, lists the error
  dedupe     → shows the stage-1 list with a warning
  matching   → shows the error in place of results
```

Decision rules:
- **Any** Gemini failure triggers the fallback, including 400s, because
  Gemini reports some account problems (such as an invalid key) as 400.
  The cost is extra latency on a request that would fail anyway.
- An empty response counts as a failure, because thinking models can spend
  the whole token budget reasoning and return no answer.
- For JSON steps, the OpenRouter request adds the JSON Schema to the system
  prompt and requests JSON mode; code fences in the reply are stripped.

## Integrations

| Service | Used for | Required |
|---|---|---|
| Google Gemini API | Vision extraction, dedup, matching (primary) | Yes |
| OpenRouter | Same three steps when Gemini fails | No |
| Google Sheets API (service account) | Roster, Activity Catalog, appending attendance | No (CSV fallback; Step 5 hidden) |
| Streamlit Community Cloud | Hosting and secrets | Deployment only |

## Limitations and known gaps

- Vision accuracy on dense or scrolled screenshots isn't validated at scale;
  upload several images and review the list before matching.
- LLM dedup can over- or under-merge; review it.
- The default fallback model is a free preview model: 10s–2min per call
  measured, and it can be withdrawn without notice.
- Free OpenRouter models may log prompts; this app sends member names and
  screenshots. Keep "allow training" off in OpenRouter's privacy settings.
- The UI shows only a toast when the fallback is used; results aren't
  labeled with the provider that produced them.
- Gemini's 429 retry waits at most ~6s, so a longer rate-limit window goes
  straight to the fallback.
- Appending to Raw Data relies on the tab having no blank rows mixed into
  existing data.
