#!/usr/bin/env python3
"""
strava_fetch.py — Fetch {{ATHLETE_NAME}}'s Strava activities for Coach.

OAuth flow (Strava: short-lived access_token + long-lived refresh_token):
  1. Credentials come from env: STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET,
     STRAVA_REFRESH_TOKEN (Hermes injects them from .env).
  2. Cache the current access_token + expires_at at
     .strava_token_cache.json in the vault directory (${COACH_VAULT},
     host-visible through the bind mount, so it survives container cycles)
     so subsequent invocations skip the token endpoint entirely.
  3. On cache miss or expiry, POST grant_type=refresh_token to /oauth/token
     to mint a new access_token. Strava sometimes rotates the refresh_token
     on this exchange — when it does, persist the new one in cache so we
     keep working even if .env wasn't updated.
  4. On any API 401, force one refresh + retry. If the refresh itself 401s,
     the refresh_token is dead and needs re-authorization (surfaced clearly).

Stdlib only — no `requests` dependency, runs anywhere with python3.10+.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

# Token cache must persist across container cycles. Inside the sandbox the
# profile directory is throwaway overlay, so a refresh_token rotated by Strava
# would be lost with the container. Resolve the vault path from the
# environment: COACH_VAULT is the in-container mount (default /wiki),
# COACH_VAULT_HOST is the same directory as seen from the host. Falls back to
# the skill directory when neither exists.
def _resolve_cache_path():
    vault = os.environ.get("COACH_VAULT", "/wiki")
    if os.path.isdir(vault):
        return os.path.join(vault, ".strava_token_cache.json")
    host_vault = os.environ.get("COACH_VAULT_HOST")
    if host_vault and os.path.isdir(os.path.expanduser(host_vault)):
        return os.path.join(os.path.expanduser(host_vault), ".strava_token_cache.json")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".strava_token_cache.json")


CACHE_PATH = _resolve_cache_path()
TOKEN_URL = "https://www.strava.com/oauth/token"
ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
ACTIVITY_DETAIL_URL = "https://www.strava.com/api/v3/activities/{id}"
EXPIRY_SKEW_SECONDS = 60  # refresh slightly ahead of true expiry


def die(msg, details="", code=1):
    sys.stderr.write(json.dumps({"error": msg, "details": details}) + "\n")
    sys.exit(code)


def http_request(method, url, *, form=None, headers=None, timeout=30):
    """Returns (status, parsed_body_or_dict, response_headers)."""
    body = None
    h = dict(headers or {})
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        h.setdefault("Content-Type", "application/x-www-form-urlencoded")
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {}), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"raw": raw}
        return e.code, parsed, dict(e.headers or {})
    except urllib.error.URLError as e:
        die("Network error contacting Strava", str(e))


def load_cache():
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)
    os.chmod(CACHE_PATH, 0o600)


def refresh_access_token(client_id, client_secret, refresh_token, prior_cache=None):
    """POST /oauth/token with grant_type=refresh_token. Returns updated cache dict."""
    status, payload, _ = http_request(
        "POST",
        TOKEN_URL,
        form={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )
    if status == 401:
        die(
            "Strava refresh_token rejected (401)",
            "The STRAVA_REFRESH_TOKEN is invalid or revoked. Re-authorize the app and update .env.",
        )
    if status != 200:
        die(f"Token endpoint returned {status}", json.dumps(payload))
    # Strava may rotate refresh_token on this exchange; persist the new one.
    cache = {
        "access_token": payload["access_token"],
        "expires_at": payload["expires_at"],
        "refresh_token": payload.get("refresh_token", refresh_token),
    }
    # Preserve athlete_id across refreshes; initial auth includes it, refresh
    # usually does not.
    athlete = payload.get("athlete")
    if isinstance(athlete, dict) and athlete.get("id"):
        cache["athlete_id"] = athlete["id"]
    elif prior_cache and prior_cache.get("athlete_id"):
        cache["athlete_id"] = prior_cache["athlete_id"]
    save_cache(cache)
    return cache


def get_access_token(force_refresh=False):
    client_id = os.environ.get("STRAVA_CLIENT_ID")
    client_secret = os.environ.get("STRAVA_CLIENT_SECRET")
    env_refresh = os.environ.get("STRAVA_REFRESH_TOKEN")
    missing = [k for k, v in {
        "STRAVA_CLIENT_ID": client_id,
        "STRAVA_CLIENT_SECRET": client_secret,
        "STRAVA_REFRESH_TOKEN": env_refresh,
    }.items() if not v]
    if missing:
        die("Missing required env vars", ", ".join(missing))

    cache = None if force_refresh else load_cache()
    if cache and cache.get("access_token") \
            and cache.get("expires_at", 0) > time.time() + EXPIRY_SKEW_SECONDS:
        return cache["access_token"]

    # Prefer the cached (possibly rotated) refresh_token over .env. Falls
    # back to env on first run when no cache exists yet.
    rt = (cache or {}).get("refresh_token") or env_refresh
    new_cache = refresh_access_token(client_id, client_secret, rt, prior_cache=cache)
    return new_cache["access_token"]


def api_get(url, params=None, *, _retried=False):
    """Authenticated GET. Auto-refreshes once on 401."""
    token = get_access_token(force_refresh=_retried)
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    status, payload, headers = http_request(
        "GET", full, headers={"Authorization": f"Bearer {token}"}
    )
    if status == 401 and not _retried:
        return api_get(url, params, _retried=True)
    if status == 429:
        die(
            "Strava rate limit (429)",
            f"Retry-After: {headers.get('Retry-After', 'unknown')}; limits are 100/15min, 1000/day",
        )
    if status != 200:
        die(f"Strava API {status}", json.dumps(payload))
    return payload


def fmt_pace(meters_per_second):
    if not meters_per_second or meters_per_second <= 0:
        return None
    sec_per_km = 1000.0 / meters_per_second
    m, s = divmod(int(round(sec_per_km)), 60)
    return f"{m}:{s:02d}"


def date_to_epoch(date_str, end_of_day=False):
    # Naive datetime — Python treats as local tz when calling .timestamp(),
    # which matches how {{ATHLETE_NAME}} thinks about "the day I ran."
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as e:
        die("Invalid date format", f"Expected YYYY-MM-DD, got '{date_str}': {e}")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return int(dt.timestamp())


def normalize_activity(detail):
    gear = detail.get("gear")
    return {
        "id": detail.get("id"),
        "name": detail.get("name"),
        "start_date_local": detail.get("start_date_local"),
        "type": detail.get("type"),
        "sport_type": detail.get("sport_type"),
        "distance_km": round((detail.get("distance") or 0) / 1000.0, 3),
        "distance_meters_raw": detail.get("distance"),
        "moving_time_seconds": detail.get("moving_time"),
        "elapsed_time_seconds": detail.get("elapsed_time"),
        "average_pace_min_per_km": fmt_pace(detail.get("average_speed")),
        "average_speed_mps_raw": detail.get("average_speed"),
        "max_speed_mps_raw": detail.get("max_speed"),
        "average_heart_rate": detail.get("average_heartrate"),
        "max_heart_rate": detail.get("max_heartrate"),
        "average_cadence": detail.get("average_cadence"),
        "total_elevation_gain": detail.get("total_elevation_gain"),
        "splits_metric": detail.get("splits_metric", []),
        "laps": detail.get("laps", []),
        "device_name": detail.get("device_name"),
        "gear_name": gear.get("name") if isinstance(gear, dict) else None,
        "perceived_exertion": detail.get("perceived_exertion"),
        "suffer_score": detail.get("suffer_score"),
    }


def fetch_activities(args):
    params = {}
    if args.last:
        params["per_page"] = args.last
    elif args.date:
        params["after"] = date_to_epoch(args.date) - 1
        params["before"] = date_to_epoch(args.date, end_of_day=True)
        params["per_page"] = 30
    elif args.since:
        params["after"] = date_to_epoch(args.since) - 1
        if args.until:
            params["before"] = date_to_epoch(args.until, end_of_day=True)
        params["per_page"] = 100
    else:
        params["per_page"] = 1

    listing = api_get(ACTIVITIES_URL, params)
    if not isinstance(listing, list):
        die("Unexpected list endpoint response", json.dumps(listing))

    # List endpoint omits splits/laps — fetch detail for each to get them.
    activities = []
    for item in listing:
        detail = api_get(ACTIVITY_DETAIL_URL.format(id=item["id"]))
        activities.append(normalize_activity(detail))
    return activities


def parse_args():
    p = argparse.ArgumentParser(description="Fetch Strava activity data for Coach.")
    p.add_argument("--date", help="Single date YYYY-MM-DD")
    p.add_argument("--since", help="Range start YYYY-MM-DD")
    p.add_argument("--until", help="Range end YYYY-MM-DD (with --since)")
    p.add_argument("--last", type=int, help="Last N activities")
    args = p.parse_args()
    if args.until and not args.since:
        die("Bad args", "--until requires --since")
    return args


def main():
    args = parse_args()
    activities = fetch_activities(args)
    sys.stdout.write(json.dumps(
        {"activities": activities, "count": len(activities)}, indent=2
    ) + "\n")


if __name__ == "__main__":
    main()
