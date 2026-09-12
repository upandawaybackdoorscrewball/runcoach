# Strava Direct API Fallback (urllib)

When `strava_fetch.py` hits rate limits (429), use this direct API approach. The Docker container does NOT have `requests` — use `urllib.request`.

## Full working script

Save to `${COACH_VAULT}/strava_pull.py` and run with `python3 ${COACH_VAULT}/strava_pull.py`.

```python
import json, urllib.request, urllib.parse

# Credentials from env (forwarded by docker_forward_env)
import os
CLIENT_ID = os.environ.get('STRAVA_CLIENT_ID')
CLIENT_SECRET = os.environ.get('STRAVA_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('STRAVA_REFRESH_TOKEN')

# Step 1: Refresh access token
data = urllib.parse.urlencode({
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'refresh_token': REFRESH_TOKEN,
    'grant_type': 'refresh_token'
}).encode()
req = urllib.request.Request('https://www.strava.com/oauth/token', data=data)
resp = urllib.request.urlopen(req)
token_data = json.loads(resp.read())
access_token = token_data['access_token']

# Step 2: Fetch summary activities
# 'after' takes a Unix timestamp (seconds since epoch); see the reference at the bottom
AFTER_TS = 0  # replace with int(datetime(year, month, day).timestamp())
params = urllib.parse.urlencode({'per_page': 100, 'after': AFTER_TS})
req2 = urllib.request.Request(
    f'https://www.strava.com/api/v3/athlete/activities?{params}',
    headers={'Authorization': f'Bearer {access_token}'}
)
resp2 = urllib.request.urlopen(req2)
activities = json.loads(resp2.read())

# Step 3: Fetch detail for each activity (for lap-level data)
detailed = []
for a in activities:
    if a['type'] != 'Run':
        continue
    req3 = urllib.request.Request(
        f"https://www.strava.com/api/v3/activities/{a['id']}?include_all_efforts=false",
        headers={'Authorization': f'Bearer {access_token}'}
    )
    resp3 = urllib.request.urlopen(req3)
    detailed.append(json.loads(resp3.read()))

# Save
with open('${COACH_VAULT}/strava_detailed.json', 'w') as f:
    json.dump(detailed, f, indent=2)
```

## Key details

- **One API call per invocation** of the summary endpoint, plus one per detail fetch
- **Rate limit:** 100 requests per 15 minutes, 1000 per day
- **Credentials** are available via `env | grep STRAVA` in the container
- **The refresh token rotates** on each refresh — the new one is in the response. But the old one still works for a while. Don't overwrite env vars mid-session.
- **`average_cadence`** in Strava is half-cadence from Garmin (multiply by 2 for true SPM)
- **`average_speed`** is in meters per second
- **`splits_metric`** has per-km splits with HR, pace, elevation
- **`laps`** in the detail response has per-lap HR, cadence, watts, speed, distance

## Unix timestamp reference

```python
from datetime import datetime
# midnight local time on the chosen day
ts = int(datetime(year, month, day).timestamp())
```

Or use `--since YYYY-MM-DD` with the strava_fetch.py script (which handles this internally).
