# Auto-polling setup for Strava activity review

Used when {{ATHLETE_NAME}} wants "I see it when it lands" without manual screenshots.

## What it does

Polls Strava on a schedule during {{ATHLETE_NAME}}'s known workout windows. When a new activity appears that hasn't been reviewed yet, fetches full data, generates a brief review, and sends it to Telegram.

## Deduplication

State lives in `${COACH_VAULT}/.strava_reviewed.json` (persistent host mount, survives container restarts).

```json
{
  "last_id": "0000000000",
  "last_reviewed_at": "YYYY-MM-DDTHH:MM:SS+00:00",
  "reviewed_ids": [
    "0000000000",
    "0000000000"
  ]
}
```

Keep last 50 IDs. On overflow, drop oldest.

## Cron schedule

{{ATHLETE_NAME}} trains in the {{WORKOUT_WINDOW}} ({{TIMEZONE}}). The windows below are an example for an afternoon/evening runner with Sunday off; convert the athlete's local window to UTC and adjust the cron expressions.

| Window | Days | Times (UTC) | Cron |
|--------|------|-------------|------|
| Weekday afternoon/evening | Mon-Fri | 19:00-01:59 | `*/15 19-23,0-1 * * 1-5` |
| Saturday all-day | Sat | 00:00-23:59 | `*/15 * * * 6` |
| Sunday | Off | — | No job |

The weekday expression above covers a local afternoon/evening window when {{TIMEZONE}} is UTC-4/UTC-5; shift the hour ranges for other zones.

## Two cron jobs (no_agent: true — REQUIRED)

Create two separate cron jobs (one per window). Both use the wrapper script (`scripts/strava_poll.py`) with `no_agent: true`. This is critical — agent-based cron jobs cannot deduplicate because the agent always produces output. With `no_agent: true`, empty stdout = no delivery.

```bash
# Weekdays
hermes cron create \
  --name "strava-poll-weekdays" \
  --schedule "*/15 19-23,0-1 * * 1-5" \
  --no-agent \
  --script "strava_poll.py" \
  --deliver origin

# Saturday
hermes cron create \
  --name "strava-poll-saturday" \
  --schedule "*/15 * * * 6" \
  --no-agent \
  --script "strava_poll.py" \
  --deliver origin
```

Script path is relative to `${HERMES_PROFILE_DIR}/scripts/`. The script must be placed there (or symlinked). If using an agent-based approach, the prompt MUST NOT produce output on duplicate activities — but this is unreliable. Use `no_agent: true`.

### State file type consistency

Activity IDs in `${COACH_VAULT}/.strava_reviewed.json` must be **strings**, not integers. The script compares `str(activity_id)` against the list. If an agent writes the state file with integer IDs, the comparison fails silently and duplicates get re-reviewed.

## Review format

The wrapper script generates Telegram-compatible markdown:

```
**Run Name — YYYY-MM-DD**
Session type: VO2 / Interval
Distance: X.XX km
Avg pace: X:XX/km
Avg HR: XXX bpm
...
**Splits:**
  K1: X:XX/km HR XXX
...
**Quick take:**
High intensity session. HR in VO2 zone. Good stimulus.

Reply for full deep-dive review.
```

When {{ATHLETE_NAME}} replies for deep-dive, pull the same activity via the skill manually and do the full read.

## Memory entries on review

When a new activity is detected and reviewed, save a one-line memory entry:

```
Reviewed Strava activity [name] on [date] at [time] UTC. Activity ID: [id].
```

This prevents session resets from making Coach think a run was missed.