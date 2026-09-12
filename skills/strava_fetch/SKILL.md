---
name: strava_fetch
description: "Fetch activity data from {{ATHLETE_NAME}}'s Strava account. Use whenever {{ATHLETE_NAME}} mentions a run, asks about workout stats, references pace/HR/splits/cadence, or when post-workout review is needed. Returns full activity detail including pace per km, HR, cadence, elevation, splits, and laps. Can fetch most recent activity (default, no args), a specific date, a date range, or the last N activities."
version: 1.0.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [fitness, strava, activity, workout, run, training, coach]
    related_skills: []
---

# strava_fetch: Fetch {{ATHLETE_NAME}}'s Strava activity data

## When to invoke

Invoke this skill whenever {{ATHLETE_NAME}}:
- Mentions a run, ride, swim, or other workout they just did
- Asks about pace, splits, HR, cadence, or elevation
- Wants post-workout review or analysis
- Asks "how did my run go" / "what were my splits" / "pull up today's workout"
- References a past session by date ("last Tuesday's run")

## Usage

```bash
python3 /root/.hermes/skills/strava_fetch/strava_fetch.py                        # most recent activity
python3 /root/.hermes/skills/strava_fetch/strava_fetch.py --last 5               # last 5 activities
python3 /root/.hermes/skills/strava_fetch/strava_fetch.py --date YYYY-MM-DD      # activities on a date
python3 /root/.hermes/skills/strava_fetch/strava_fetch.py --since YYYY-MM-DD     # since a date
python3 /root/.hermes/skills/strava_fetch/strava_fetch.py --since YYYY-MM-DD --until YYYY-MM-DD   # date range
```

## Output

JSON to stdout with structure:

```json
{
  "activities": [
    {
      "id": ..., "name": ..., "start_date_local": ...,
      "type": "Run", "distance_km": 8.42,
      "moving_time_seconds": ..., "elapsed_time_seconds": ...,
      "average_pace_min_per_km": "4:31",
      "average_heart_rate": ..., "max_heart_rate": ...,
      "average_cadence": ..., "total_elevation_gain": ...,
      "splits_metric": [...], "laps": [...],
      "device_name": ..., "gear_name": ...,
      "perceived_exertion": ..., "suffer_score": ...
    }
  ],
  "count": N
}
```

Errors emit `{"error": "...", "details": "..."}` to stderr and exit non-zero.

## Required env

- `STRAVA_CLIENT_ID`
- `STRAVA_CLIENT_SECRET`
- `STRAVA_REFRESH_TOKEN`

Loaded by Hermes from `${HERMES_PROFILE_DIR}/.env`.

### Pitfall: credentials not available in container

If the skill runs in a Docker sandbox and `.env` is not mounted, the env vars will be empty. Check with `env | grep STRAVA` before invoking. If missing, either:

1. Source a `.env` from the mounted vault directory (`${COACH_VAULT}/.env`), or
2. Have {{ATHLETE_NAME}} provide the values inline for the session.

The script itself handles missing env vars gracefully, but detecting upstream avoids a wasted API call.

## Cache

Access tokens are cached at `${COACH_VAULT}/.strava_token_cache.json` (the vault is host-mounted, so the same file is visible on the host; chmod 600), and refreshed only when expired. A 401 from any API call forces one retry with a fresh token.

## Pitfalls

### Rate limit (429) — direct API fallback

Strava's API rate limit is 100 requests per 15 minutes and 1000 per day. The `strava_fetch.py` script makes one request per invocation, but repeated calls (e.g., fetching multiple date ranges, retrying after errors) can exhaust the 15-min window quickly. When the script returns `{"error": "Strava rate limit (429)"}`, do NOT keep retrying — each attempt burns another request against the limit.

**Fallback: direct Strava API call via urllib.** The Docker container does NOT have the `requests` module. Use `urllib.request` instead. This bypasses the script entirely and makes one clean API call.

```python
import json, urllib.request, urllib.parse

# Step 1: Refresh access token
data = urllib.parse.urlencode({
    'client_id': '<from env>',
    'client_secret': '<from env>',
    'refresh_token': '<from env>',
    'grant_type': 'refresh_token'
}).encode()
req = urllib.request.Request('https://www.strava.com/oauth/token', data=data)
resp = urllib.request.urlopen(req)
token_data = json.loads(resp.read())
access_token = token_data['access_token']

# Step 2: Fetch activities
params = urllib.parse.urlencode({'per_page': 100, 'after': <unix_timestamp>})
req2 = urllib.request.Request(
    f'https://www.strava.com/api/v3/athlete/activities?{params}',
    headers={'Authorization': f'Bearer {access_token}'}
)
resp2 = urllib.request.urlopen(req2)
activities = json.loads(resp2.read())  # list of activity dicts
```

**Key details:**
- Credentials are available via `env | grep STRAVA` in the container (forwarded by `docker_forward_env`)
- The `after` parameter takes a Unix timestamp (seconds since epoch, e.g. `int(datetime(year, month, day).timestamp())`)
- The summary endpoint returns `average_cadence` (half-cadence from Garmin), `average_heartrate`, `average_speed` (m/s), but NOT detailed laps
- For lap-level data, see "Detail fetch for lap-level data" below
- Save the refresh token from env each time — it rotates on refresh

See `references/strava-direct-api-fallback.md` for the full working script.

### Detail fetch for lap-level data

The summary activity endpoint (`/api/v3/athlete/activities`) returns overall metrics and `splits_metric` (per-km splits), but the `laps` array in the summary is INCOMPLETE — it often truncates or omits lap-level detail. For lap-level analysis (work interval HR, cadence, watts per block), fetch each activity individually:

```python
# For each activity ID:
req3 = urllib.request.Request(
    f'https://www.strava.com/api/v3/activities/{activity_id}?include_all_efforts=false',
    headers={'Authorization': f'Bearer {access_token}'}
)
resp3 = urllib.request.urlopen(req3)
detail = json.loads(resp3.read())
# detail['laps'] now has full lap data with average_heartrate, average_cadence,
# average_watts, max_heartrate, average_speed, distance per lap
```

**Rate limit caution:** Each detail fetch is one API call. For a 24-run analysis window, that's 24 + 1 (summary) = 25 calls. Budget accordingly. If already rate-limited, wait for the 15-min window to reset before fetching details.

### Cron jobs: Docker backend unavailable

When this skill is invoked from a scheduled cron job, the Docker terminal backend may be unreachable. `execute_code` and `terminal` will fail immediately with:

```
RuntimeError: Docker command is available but 'docker version' failed.
```

**Do not retry the same tool.** It will fail identically.  
**Do not fall back to `delegate_task`.** Subagents inherit the same broken backend.  
**Do not attempt to fix Docker from inside the container.** You lack privilege.

The only correct response is `[SILENT]` (or a one-line failure note) and let the next cron tick retry. See `references/docker-backend-failure.md` for host-side recovery steps.

### Container `/tmp` is tmpfs (RAM-only)

Inside the Docker sandbox, `/tmp` is a `tmpfs` mount. Files written there vanish when the container exits. Always write skill output (reports, docs, cache) to `${COACH_VAULT}` or a persistent path that is host-mounted. Never rely on `/tmp` for anything that must survive the current turn.

### Container env vars: `docker_forward_env` required

The sandbox does not automatically inherit host env vars. Hermes must be configured with `docker_forward_env` in `config.yaml` to forward `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, and `STRAVA_REFRESH_TOKEN` into the container. If these are missing, verify the gateway config before assuming credentials are absent.

### PITFALL: Cron prompt claims activity data but none exists

When the poll script fails (wrong path, missing env vars, API error), the cron prompt template still fires with its "a new activity is below" preamble — but delivers no actual data. The agent must detect this before attempting any review. Check for structured JSON in the prompt. If absent, report the failure and what needs fixing. Never fabricate a review of missing data. See `references/cron-missing-activity-data.md` for the full response protocol.

### Auto-polling for new activities

To detect new uploads without manual trigger, set up a cron job that runs the fetch script on a cadence, plus a deduplication file (`${COACH_VAULT}/.strava_reviewed.json`) that stores reviewed activity IDs. When a new ID appears, run the review and append the ID. Keep last 50 IDs to prevent bloat.

See `references/auto-polling-setup.md` for the full cron schedule and wrapper script pattern.

See `references/cron-agent-integration.md` for how the poll script fits into the agent-side review workflow (the script is a detector; the agent writes the deep-dive review).

### Cron deduplication: use `no_agent: true` (PITFALL)

**Agent-based cron jobs do NOT work for deduplication.** Even with explicit "output NOTHING if already reviewed" instructions, the agent will produce some response (a confirmation, an explanation, a "[SILENT]" token that still gets delivered). The cron delivery system sends whatever the agent outputs.

**The correct approach is `no_agent: true` with the poll script directly.** The `strava_poll.py` script has built-in deduplication — it checks `${COACH_VAULT}/.strava_reviewed.json`, and if the activity ID is already in the list, it exits with empty stdout. The cron system suppresses delivery when stdout is empty. No agent, no LLM, no chance of a rogue message.

**Setup:**
```
cronjob update:
  no_agent: true
  script: strava_poll.py   # relative to ${HERMES_PROFILE_DIR}/scripts/ (copy or symlink skills/strava_fetch/scripts/strava_poll.py there)
  prompt: (ignored when no_agent=true, but set it for documentation)
```

**State file types:** Activity IDs in `${COACH_VAULT}/.strava_reviewed.json` MUST be strings, not integers. The script compares `str(activity_id)` against the list. If the state file was written with integer IDs (e.g., from a manual agent write), the comparison fails silently and the activity gets re-reviewed. Always ensure IDs are stored as strings.

**When the script finds a new activity**, it prints a formatted quick review to stdout, which the cron system delivers. For a deeper agent-driven review, use a separate workflow (manual trigger or a chained cron job that only fires when the state file changes).

### PITFALL: Cron jobs MUST use deduplication

Agent-driven cron polls that fetch from Strava without checking `${COACH_VAULT}/.strava_reviewed.json` will re-review the same activity every 15 minutes and spam {{ATHLETE_NAME}}.

Every cron prompt that polls Strava MUST:
1. Read `${COACH_VAULT}/.strava_reviewed.json` and check the activity ID against `reviewed_ids`
2. If already reviewed, output `[SILENT]` and stop (the cron system suppresses delivery on [SILENT])
3. If new, proceed with review then save the ID to the state file

The `strava_poll.py` script has this logic built in. Use it, or replicate the pattern in the agent prompt. Do not run a bare "fetch and review" cron without dedup.

### PITFALL: Schedule changes require poller updates

When the weekly schedule deviates from normal split (rehearsal week, deload, etc.), the strava-poll cron job prompts MUST be updated with the modified schedule. They default to grading against the normal split and will produce incorrect reviews.

## Accessing linked files in this skill

To view linked reference files, call:
```
skill_view(name="strava_fetch", file_path="references/<filename>")
```

### Available references

- `references/auto-polling-setup.md` — cron schedule and wrapper script for auto-detecting new activities
- `references/cron-agent-integration.md` — how the poll script fits into agent-side review workflow
- `references/cron-missing-activity-data.md` — what to do when the cron prompt claims activity data exists but delivers none
- `references/container_env_troubleshooting.md` — env var and credential issues in Docker
- `references/docker-backend-failure.md` — host-side recovery when Docker backend is unreachable
- `references/strava-direct-api-fallback.md` — full working script for direct Strava API calls via urllib when the fetch script hits rate limits
- `references/vo2max-estimation.md` — Daniels VDOT method, Garmin race predictor interpretation, concurrent training adjustments

## Cadence correction (Garmin → Strava → true SPM)

{{DEVICE}} reports **half-cadence** to Strava. The `average_cadence` field in Strava data is steps per minute divided by 2. To get true SPM:

```
true_spm = strava_average_cadence × 2
```

**{{ATHLETE_NAME}}'s verified quality cadence window:** {{QUALITY_CADENCE}} SPM (true). On Strava this appears halved. When analyzing multi-session data, always double the cadence before comparing to the window.

**Stride length** can be estimated from pace and cadence:
```
stride_m = speed_mps × 60 / true_spm
```
Where `speed_mps = average_speed` from Strava (meters per second). Example: 3.5 m/s at 180 SPM = 1.17m stride.

## Multi-session analysis patterns

When {{ATHLETE_NAME}} asks for trends across multiple sessions (cadence, HR, pace, weekly volume), use this workflow:

1. **Fetch summary activities** for the date range (one API call)
2. **Classify runs** by name and HR/pace profile:
   - `easy`: names containing "z2", "zone 2", "easy", "shakeout", "lr", OR pace >6:00/km with avg HR <160
   - `threshold`: names containing "threshold", "@ tp", or the athlete's threshold pace string ({{THRESHOLD_PACE}})
   - `vo2`: names containing "repeats", "1k", "800m", "@gp", "intervals"
3. **Fetch detail** for each run if lap-level analysis is needed (24 detail calls for a 5-week window)
4. **Calculate per-category averages** for cadence, stride length, HR
5. **Calculate weekly volume** by grouping activities by ISO week (Monday start)

**Weekly volume calculation:**
```python
from collections import defaultdict
from datetime import datetime, timedelta
weekly = defaultdict(float)
for r in runs:
    d = datetime.strptime(r['start_date_local'][:10], '%Y-%m-%d')
    week_start = d - timedelta(days=d.weekday())
    weekly[week_start.strftime('%Y-%m-%d')] += r['distance'] / 1000
```

**Fastest continuous km splits** — pull from `splits_metric` array (per-km splits) across all activities, filter for 950-1050m distance, sort by `moving_time`. This gives the best 1km efforts without relying on Strava's sliding-window PRs.

## Best Efforts / PR extraction

When {{ATHLETE_NAME}} asks what PRs Strava awarded in an activity, fetch the individual activity detail with `include_all_efforts=true` and read `best_efforts`. Use entries where `pr_rank == 1` as the PR list, and report them as Strava's awards, not as the athlete's official PRs; Garmin lap data is the grading source (see "Data source hierarchy" below). Do **not** rely only on top-level `achievement_count` or `pr_count`; those summary fields can undercount or split achievements oddly while `best_efforts` contains the actual ranked efforts.

For each PR, report:
- `name` (400m, 1K, 1 mile, etc.)
- `moving_time`
- pace from `moving_time / distance`
- optional context from `start_index` / `end_index` when explaining whether it came during a late-race close

Example detail endpoint:
```python
req = urllib.request.Request(
    f'https://www.strava.com/api/v3/activities/{activity_id}?include_all_efforts=true',
    headers={'Authorization': f'Bearer {access_token}'}
)
detail = json.loads(urllib.request.urlopen(req).read())
prs = [e for e in detail.get('best_efforts', []) if e.get('pr_rank') == 1]
```

## Data source hierarchy for {{ATHLETE_NAME}}

Garmin is the **primary data source** for all workout analysis, read through the Garmin MCP (see `config.yaml` and AGENTS.md). Garmin intervals and lap splits are run truth. Strava is **secondary**: {{ATHLETE_NAME}}'s Garmin auto-syncs to Strava, so this skill is the cheap, scriptable path for detecting a new upload (the pollers), pulling a quick summary, and running multi-session queries when the MCP is unavailable or a Strava-only field is needed.

### When to use Strava (this skill)
- New-activity detection via the `no_agent` pollers (Garmin has no equivalent push)
- Quick summaries, weekly volume, and cross-session comparisons from `splits_metric` and `laps`
- Activity names, suffer score, gear name, perceived exertion as logged on Strava
- Any time the Garmin MCP is down; say so in the review and cite Strava as the source

### When to prefer Garmin
- Grading intervals and laps against the prescription (Garmin lap data is primary; if Strava and Garmin disagree, Garmin wins)
- Training effect, load, execution score, and any pre-digested Garmin signal
- Sleep, HRV, RHR, Body Battery, VO2 max trend, race predictions, weigh-ins (Garmin-only, via MCP; Strava never has them)

### Never from Strava
- PRs. Strava sliding-window times are unreliable and are never quoted as PRs. If {{ATHLETE_NAME}} asks what Strava awarded, report it as "Strava awarded" and grade the effort from Garmin laps.

### Garmin metrics with standing caveats
- **Training Readiness**: ignored.
- **VO2 max**: biased low, directional only.
- **Body Battery**: context, never a veto; felt sense leads.

## Common failure modes

### Memory tool unavailable in Docker cron containers

The `memory` tool may not work inside the Docker sandbox during cron runs. The cron prompt instructs "write memory entry FIRST," but if memory() returns an error, skip it silently and proceed. The session-recap `.md` file persisted to `${COACH_VAULT}/session-recap/` serves as the durable record. Do not block the review on a failed memory write.

### State file location

The deduplication state file must live on the persistent mount (`${COACH_VAULT}/...`) so reviewed IDs survive container restarts. Do not use `/tmp` or in-container paths.
