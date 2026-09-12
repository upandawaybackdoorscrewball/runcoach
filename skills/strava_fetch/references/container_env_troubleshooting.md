# Strava Container / Cron Troubleshooting

Quick reference for when the Strava fetch fails inside the Docker sandbox or during cron execution.

## Symptom: "Missing required env vars"

```
{"error": "Missing required env vars", "details": "STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN"}
```

### Diagnosis

1. Check env inside the container:
   ```bash
   env | grep STRAVA
   ```
2. If empty, the gateway's `docker_forward_env` is not forwarding the three Strava variables from the host profile `.env`.
3. Verify the host profile `.env` actually contains them:
   ```bash
   cat ${HERMES_PROFILE_DIR}/.env | grep STRAVA
   ```

### Fix

- Gateway `config.yaml` must list the three vars under `docker_forward_env`:
  ```yaml
  docker_forward_env:
    - STRAVA_CLIENT_ID
    - STRAVA_CLIENT_SECRET
    - STRAVA_REFRESH_TOKEN
  ```
- Restart the gateway after editing.
- Cron jobs spin fresh containers; they inherit env only via `docker_forward_env`. A manual session that sourced a `.env` file will not help the cron job.

## State file location

- Reviewed-activity dedup: `${COACH_VAULT}/.strava_reviewed.json`
- Token cache: `${COACH_VAULT}/.strava_token_cache.json`

Both must be on `${COACH_VAULT}` (host-mounted) to survive container restarts.
