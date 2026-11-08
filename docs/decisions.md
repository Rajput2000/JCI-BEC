# Decisions

Newest first.

## 2026-11-08 — Default Gemini model changed to `gemini-3.8-flash`

**Decision:** `GEMINI_VISION_MODEL` and `GEMINI_TEXT_MODEL` now default to
`gemini-3.8-flash`.

**Why:** Gemini started rejecting `gemini-2.5-flash` with `404 NOT_FOUND:
no longer available to new users`, so every call fell back to OpenRouter.
`gemini-3.8-flash` is the replacement Google's error names, and it is listed
for this key. Tested with synthetic data and the app's real request settings
(including `thinking_budget=0`): vision 12/12 names exact (5.6s), dedup 30/30
(3.7s), matching 62/62 names (6.3s).

**Alternatives considered:** `gemini-flash-latest` (an alias that would
change model without notice; rejected for predictable output), or
`gemini-3.5-flash` / `gemini-3.7-flash` (older; not tested).

**Consequences:** any deployment whose secrets still set
`GEMINI_*_MODEL = "gemini-2.5-flash"` must update them, or it keeps falling back.

## 2026-11-08 — Add OpenRouter as the fallback LLM provider

**Decision:** Every LLM call goes to Gemini first. On any failure (API error,
timeout, missing key, or empty response), the same request goes to
OpenRouter, using `dots-studio/dots-3-note-preview:free` by default. The
fallback is off unless `OPENROUTER_API_KEY` is set.

**Why:** Gemini is a single point of failure for all three AI steps. On the
day this was built, the Gemini project returned `402 RESOURCE_EXHAUSTED`
(prepaid credits depleted), and every AI step failed.

**Alternatives considered:**
- *Groq:* rejected. Its free tier's 8,000 tokens/minute cap is why the app
  moved off Groq; the matching call alone used ~2.2k tokens in and ~11k out
  in testing.
- *Gemma models on OpenRouter* (`google/gemma-4-*:free`): rejected. They are
  hosted on Google AI Studio, so they fail with Gemini (they returned 429 in
  testing).
- *NVIDIA Nemotron vision models on OpenRouter:* rejected. They are only
  available to accounts that allow providers to train on prompts, which is
  wrong for member data.
- *Cerebras, GitHub Models, Cloudflare Workers AI, Mistral:* not tested.
  Cerebras has no vision model and a small free-tier context.

**Test results** (synthetic names, `dots-3-note-preview:free`): vision 12/12
names exact; dedup 40 → 30 (ideal); matching 160-name roster × 62 names
complete, with finish reason `stop`. Calls took 10s–112s.

**Design choices:**
- A provider-neutral `LLMRequest`/`generate()` replaces callers building
  Gemini config directly, so providers can be swapped or added without
  touching callers.
- The fallback runs on *any* Gemini error, not only retryable ones, because
  Gemini reports some account problems as 400. Trade-off: a truly bad
  request waits for the fallback before failing (reliability over latency).
- Gemini got a 120s timeout; without one, a hung call never reaches the
  fallback.
- Used `httpx` (already installed by `google-genai`) instead of the `openai`
  SDK: a single POST doesn't justify a new dependency.

**Consequences / follow-ups:**
- Free preview models can be withdrawn without notice. Keep
  `OPENROUTER_MODELS` current, and list more than one model.
- Free tiers may log prompts that include member names. Keep OpenRouter's
  training opt-out on; use a paid model if the data must stay private.
- Results aren't labeled with the provider that produced them; only a
  toast is shown.

## Earlier — Gemini as the primary LLM (replacing Groq)

**Decision:** Moved all LLM calls from Groq to Gemini (`gemini-2.5-flash`).

**Why:** Groq's free tier (8,000 tokens/minute) was too tight for a 150+ name
roster plus the full matching table, and it caused real failures
(token-budget exhaustion and request-too-large errors). Thinking is capped
or disabled per step to avoid empty responses.

**Alternatives considered:** reason not recorded beyond staying on Groq.
