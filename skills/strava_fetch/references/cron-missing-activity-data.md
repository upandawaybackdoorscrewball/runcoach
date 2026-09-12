# Cron prompt claims activity data exists but none was delivered

## Symptom

The cron job prompt includes a line like "A new Strava activity is below as structured data" followed by... nothing. No JSON, no activity object, no structured payload. The agent is being asked to write a review of data that isn't there.

## Root cause

The poll script (`strava_poll.py`) failed before it could inject activity data into the cron prompt. Common causes:
- Script path wrong in cron config (e.g., host macOS path vs. Docker container path)
- Strava env vars not forwarded via `docker_forward_env`
- Strava API returned an error (401 expired token, 429 rate limit, network timeout)

When the script fails, the cron prompt template still fires with its "a new activity is below" preamble, but the data payload is empty or missing.

## How to detect

Before writing any review, verify that actual structured activity data exists in the prompt. Look for:
- JSON object with `id`, `name`, `start_date_local`, `distance_km`, etc.
- If the prompt only has the preamble text and no data block, the data is missing.

Also check:
```bash
env | grep STRAVA  # empty = credentials not forwarded
python3 /root/.hermes/skills/strava_fetch/strava_fetch.py  # will fail if env vars missing
```

## Correct response

**Do NOT fabricate a review.** Do NOT write a review based on what you think the activity might have been.

1. Report the script failure clearly (which path failed, why)
2. Check `.strava_reviewed.json` to confirm no new activity ID was recorded
3. Describe what was prescribed for today (pull from session docs / rehearsal week plans)
4. Note what needs fixing (script path, env forwarding, cron prompt template)

## Do NOT

- Write a review of data you don't have
- Pull Strava data manually if credentials aren't available (will also fail silently)
- Assume the activity hasn't happened yet without checking (could be a sync delay or API issue)
- Duplicate the same failure report across consecutive cron ticks — if the previous tick already reported the same issue, keep the second report brief and note it's a repeat

## Related

- `references/docker-backend-failure.md` — broader Docker unavailability in cron context
- Skill pitfall: "Docker backend unavailable" covers the case where terminal/execute_code fail entirely; this reference covers the narrower case where tools work but the poll script produced no data
