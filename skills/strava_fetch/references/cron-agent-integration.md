# Cron Agent Integration Notes

## Invocation

The poll script lives at the skill's own path, **not** at `${COACH_VAULT}/scripts/`:

```bash
python3 /root/.hermes/skills/strava_fetch/scripts/strava_poll.py
```

Cron prompts should reference this path directly. `${COACH_VAULT}/scripts/strava_poll.py` does not exist and will error. If you hit a path mismatch (e.g. cron prompt says `${COACH_VAULT}/scripts/strava_poll.py`), load the skill first and use the actual path above.

## Role of `strava_poll.py` in automated reviews

`strava_poll.py` is a **detector**, not a review generator. Its job is to:

1. Fetch the latest Strava activity via `strava_fetch.py`.
2. Check it against `${COACH_VAULT}/.strava_reviewed.json` deduplication state.
3. If new, print a short structured summary to stdout and mark the ID reviewed.
4. If already reviewed or no activities exist, exit silently (no stdout).

The calling agent (cron job) uses non-empty stdout as a signal to proceed with the **full deep-dive review**. The agent must:

- Parse the activity ID from the state file or re-fetch directly using `strava_fetch.py --last N`.
- Load `${COACH_VAULT}/athlete-profile.md` for prescription context and {{ATHLETE_NAME}}'s actual zones.
- Read recent session recaps from `${COACH_VAULT}/session-recap/` for comparison context (same session type from prior weeks, and the most recent session for continuity).
- Write a memory entry before generating the review (if memory tool available; skip silently if not).
- Produce prose review in the coach voice (no "Reply for full deep-dive" — the deep dive IS the output).
- Persist the review to `${COACH_VAULT}/session-recap/YYYY-MM-DD-<type>.md`.
- Deliver the review prose as the final response.

## Context loading pattern

After the poll script detects a new activity, re-fetch with `strava_fetch.py --last 3` to get surrounding context (what came before and after the new activity). Then:

1. Read `${COACH_VAULT}/athlete-profile.md` for the weekly schedule, zones, and current goals.
2. Use `search_files` to list recent files in `${COACH_VAULT}/session-recap/`.
3. Read the most recent recap of the same session type (e.g. last week's shakeout for this week's shakeout) and the most recent recap overall (for continuity).
4. Cross-reference against the weekly schedule in athlete-profile.md to determine what was prescribed for this day.

## Output contract

The script prints a human-readable summary when a new activity is found. This is useful for debugging but is **not** the delivered review. The agent should not forward the script's raw output directly to {{ATHLETE_NAME}}. It should use the activity ID to pull full detail and write its own analysis.

## State file

`${COACH_VAULT}/.strava_reviewed.json` tracks reviewed IDs. The script maintains it automatically. Agents should not modify it directly except in recovery scenarios.

## Failure modes

- **Empty stdout** = no new activity or fetch error. Agent should respond `[SILENT]`.
- **Missing env vars** = `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REFRESH_TOKEN` not forwarded into container. Agent should report the failure and exit; do not loop or retry indefinitely.
- **Memory tool unavailable** = In Docker cron containers, the `memory` tool may return an error. This is not a review-blocking failure. Log the error and proceed with the review. The session-recap file on disk serves as the durable record instead.
- **Script path drift** = `FETCH_SCRIPT` inside `strava_poll.py` points to `/root/.hermes/skills/strava_fetch/strava_fetch.py`. If the skill is relocated, this hardcoded path breaks.
