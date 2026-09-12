#!/usr/bin/env python3
"""
strava_poll.py — Poll Strava for new {{ATHLETE_NAME}} activities, review and report.

Runs every 15 min during workout windows. Fetches latest activity, checks
against reviewed state in ${COACH_VAULT}/.strava_reviewed.json. If new, runs review
and prints formatted output to stdout (delivered as Telegram message by caller).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# Resolve persistent state and fetch paths correctly in both execution modes.
# Inside the sandbox the vault is mounted at COACH_VAULT (default /wiki) and the
# skill tree is at /root/.hermes/skills. On the host (no-agent cron jobs run
# there) the state file lives in COACH_VAULT_HOST if set, otherwise next to the
# profile, and the fetch script is resolved relative to this file.
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_ROOT = os.path.dirname(os.path.dirname(SKILL_DIR))
VAULT = os.environ.get("COACH_VAULT", "/wiki")
if os.path.isfile(os.path.join(VAULT, "athlete-profile.md")):
    STATE_PATH = os.path.join(VAULT, ".strava_reviewed.json")
    FETCH_SCRIPT = "/root/.hermes/skills/strava_fetch/strava_fetch.py"
else:
    host_vault = os.path.expanduser(os.environ.get("COACH_VAULT_HOST", ""))
    STATE_PATH = os.path.join(host_vault or PROFILE_ROOT, ".strava_reviewed.json")
    FETCH_SCRIPT = os.path.join(SKILL_DIR, "strava_fetch.py")

def load_state():
    if not os.path.exists(STATE_PATH):
        return {"last_id": None, "last_reviewed_at": None, "reviewed_ids": []}
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"last_id": None, "last_reviewed_at": None, "reviewed_ids": []}

def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)

def fmt_pace(mps):
    if not mps or mps <= 0:
        return "—"
    sec_per_km = 1000.0 / mps
    m, s = divmod(int(round(sec_per_km)), 60)
    return f"{m}:{s:02d}"

def review_run(activity):
    name = activity.get("name", "Unnamed")
    date_str = activity.get("start_date_local", "")[:10]
    dist_km = activity.get("distance_km", 0)
    avg_pace = activity.get("average_pace_min_per_km", "—")
    avg_hr = activity.get("average_heart_rate")
    max_hr = activity.get("max_heart_rate")
    cadence_half = activity.get("average_cadence")
    cadence = round(cadence_half * 2, 1) if cadence_half else None
    splits = activity.get("splits_metric", [])
    laps = activity.get("laps", [])
    suffer = activity.get("suffer_score")

    name_lower = name.lower()
    if "vo2" in name_lower or "interval" in name_lower or "repeat" in name_lower:
        session_type = "VO2 / Interval"
    elif "threshold" in name_lower or "tempo" in name_lower:
        session_type = "Threshold"
    elif "long" in name_lower or "wednesday" in name_lower or dist_km >= 10:
        session_type = "Long Run"
    elif "shakeout" in name_lower or "easy" in name_lower or "z2" in name_lower:
        session_type = "Easy / Z2"
    elif "5k" in name_lower or "race" in name_lower:
        session_type = "5K Effort"
    else:
        session_type = "General Run"

    lines = []
    lines.append(f"**{name} — {date_str}**")
    lines.append(f"Session type: {session_type}")
    lines.append("")
    lines.append(f"Distance: {dist_km:.2f} km")
    lines.append(f"Avg pace: {avg_pace}/km")
    if avg_hr:
        lines.append(f"Avg HR: {avg_hr:.0f} bpm")
    if max_hr:
        lines.append(f"Max HR: {max_hr:.0f} bpm")
    if cadence:
        lines.append(f"Cadence: {cadence:.0f} spm")
    if suffer:
        lines.append(f"Suffer score: {suffer:.0f}")
    lines.append("")

    if splits:
        lines.append("**Splits:**")
        for s in splits:
            split_num = s.get("split", "?")
            pace = fmt_pace(s.get("average_speed"))
            hr = s.get("average_heartrate")
            hr_str = f" HR {hr:.0f}" if hr else ""
            lines.append(f"  K{split_num}: {pace}/km{hr_str}")
        lines.append("")

    if laps and len(laps) > 4:
        lines.append("**Work intervals:**")
        work_count = 0
        for lap in laps:
            lap_name = lap.get("name", "")
            dist = lap.get("distance", 0)
            if dist >= 500 and ("lap " in lap_name.lower() or "rep" in lap_name.lower()):
                lap_pace = fmt_pace(lap.get("average_speed"))
                lap_hr = lap.get("average_heartrate")
                lap_max = lap.get("max_heartrate")
                lap_cad = lap.get("average_cadence")
                lap_cad_full = round(lap_cad * 2) if lap_cad else None
                work_count += 1
                hr_str = f" | HR {lap_hr:.0f} (max {lap_max:.0f})" if lap_hr else ""
                cad_str = f" | Cad {lap_cad_full}" if lap_cad_full else ""
                lines.append(f"  {lap_name}: {lap_pace}/km{hr_str}{cad_str}")
        if work_count > 0:
            lines.append("")
        else:
            lines.pop()

    lines.append("**Quick take:**")
    if avg_hr and avg_hr > 175:
        lines.append("High intensity session. HR in VO2 zone. Good stimulus.")
    elif avg_hr and avg_hr > 160:
        lines.append("Threshold-quality work. Solid session.")
    elif avg_hr and avg_hr > 145:
        lines.append("Moderate effort. Good aerobic day.")
    else:
        lines.append("Easy day. Recovery work.")

    return "\n".join(lines)

def main():
    state = load_state()

    try:
        result = subprocess.run(
            [sys.executable, FETCH_SCRIPT],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            print(f"Strava fetch failed: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        data = json.loads(result.stdout)
    except Exception as e:
        print(f"Error fetching: {e}", file=sys.stderr)
        sys.exit(1)

    activities = data.get("activities", [])
    if not activities:
        sys.exit(0)

    latest = activities[0]
    latest_id = str(latest.get("id", ""))

    if not latest_id:
        sys.exit(0)

    reviewed_ids = state.get("reviewed_ids", [])
    if latest_id in reviewed_ids:
        sys.exit(0)

    review_text = review_run(latest)
    print(review_text)

    state["last_id"] = latest_id
    state["last_reviewed_at"] = datetime.now(timezone.utc).isoformat()
    if latest_id not in reviewed_ids:
        reviewed_ids.append(latest_id)
        state["reviewed_ids"] = reviewed_ids[-50:]
    save_state(state)

if __name__ == "__main__":
    main()
