# runcoach

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) profile for a running coach that reads your Garmin and Strava data.

This is the free skeleton: the coach's personality and operating manual, the Garmin MCP wiring, a Strava fetch/poll skill, a daily morning check-in cron, and blank memory templates. You bring a Hermes install, a model provider, a Garmin Connect login, and a Strava API app. Everything in here is a template; nothing runs until you fill in the placeholders.

## What it does

- **Morning check-in.** A daily cron sends a short felt-sense question (sleep, energy, soreness, morning weight). After you reply, the coach gives a recovery read and today's training call.
- **Post-workout review.** A no-agent poller checks Strava every 15 minutes in your training window. When a new activity appears it prints a quick summary; the coach then pulls full detail and writes a prose review to your vault.
- **Garmin as run truth.** The [Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp) server exposes activities, lap splits, sleep, HRV, RHR, training load, VO2max trend, race predictions, weigh-ins and workout scheduling as tools the coach can call. Garmin intervals and laps are primary; Strava is secondary.
- **A coach, not a chatbot.** `SOUL.md` sets the voice (crisp, direct, no hype, no emoji), the posture (felt sense leads, data corroborates), the review format (conclusion first, prose, graded against the prescription), and the hard rules (never invent stats, never trust Strava sliding-window PRs, never walking recovery between intervals).
- **A vault.** The coach reads and writes a plain-Markdown vault mounted into its sandbox: `athlete-profile.md` (canonical facts about you), `sessions/`, `coach-notes/`, `session-recap/`, `nutrition/`.

## What is in the box

```
runcoach/
├── SOUL.md                       coach persona and operating rules (system prompt)
├── AGENTS.md                     profile manual: scope, directories, tools, workflows, data authority
├── config.yaml                   Hermes profile config with the Garmin MCP block and sandbox mount
├── cron/jobs.template.json       three cron jobs: morning check-in + two Strava pollers
├── memories/MEMORY.template.md   operational-state memory, structure only
├── memories/USER.template.md     athlete-preference memory, structure only
└── skills/strava_fetch/
    ├── SKILL.md                  when and how the coach uses Strava data
    ├── strava_fetch.py           Strava OAuth refresh + activity fetch CLI (stdlib only)
    ├── scripts/strava_poll.py    dedup poller run by the cron jobs
    └── references/               polling setup, cron integration, direct-API fallback, VDOT table, troubleshooting
```

## Prerequisites

1. **Hermes Agent** installed and working (`hermes --version`). Docker is needed for the sandboxed terminal the config uses (`terminal.backend: docker`).
2. **A model provider.** An OpenRouter key, an OpenAI Codex OAuth login via `hermes auth`, or any provider Hermes supports. See the comment block at the top of `config.yaml`.
3. **Garmin Connect login** for the Garmin MCP. `uvx` (from [uv](https://github.com/astral-sh/uv)) must be on your PATH; the config installs the server on first start with `uvx --from git+https://github.com/Taxuspt/garmin_mcp garmin-mcp`. Follow that project's README to log in once; it stores OAuth tokens under `~/.garminconnect`. This package does not include any of its code.
4. **A Strava API application** (Settings → My API Application on strava.com). You need the client ID, client secret, and a refresh token with `activity:read_all` scope. The [Strava OAuth docs](https://developers.strava.com/docs/authentication/) walk through obtaining the refresh token once.
5. **A Telegram bot token** if you want the coach on Telegram (the cron jobs deliver there). Any Hermes-supported platform works; adjust `origin.platform` in the cron template.

## Install

```bash
# 1. Create a new Hermes profile (pick any name; "runcoach" is used below)
hermes profile create runcoach
export HERMES_PROFILE_DIR=~/.hermes/profiles/runcoach

# 2. Copy the template files into the profile at the same relative paths
cp SOUL.md AGENTS.md config.yaml "$HERMES_PROFILE_DIR/"
mkdir -p "$HERMES_PROFILE_DIR/skills" "$HERMES_PROFILE_DIR/scripts" "$HERMES_PROFILE_DIR/memories"
cp -R skills/strava_fetch "$HERMES_PROFILE_DIR/skills/"

# 3. The cron scheduler looks for no-agent scripts under <profile>/scripts/
ln -s "$HERMES_PROFILE_DIR/skills/strava_fetch/scripts/strava_poll.py" "$HERMES_PROFILE_DIR/scripts/strava_poll.py"

# 4. Memory files: start from the templates
cp memories/MEMORY.template.md "$HERMES_PROFILE_DIR/memories/MEMORY.md"
cp memories/USER.template.md   "$HERMES_PROFILE_DIR/memories/USER.md"

# 5. Create the vault the coach will read and write, and put your athlete profile in it
mkdir -p ~/coach-vault/{sessions,coach-notes,session-recap,nutrition}
touch ~/coach-vault/athlete-profile.md

# 6. Secrets go in the profile .env (never commit this file)
cat > "$HERMES_PROFILE_DIR/.env" <<'ENV'
OPENROUTER_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_ALLOWED_USERS=
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_REFRESH_TOKEN=
COACH_VAULT=/wiki
COACH_VAULT_HOST=/absolute/path/to/coach-vault
ENV
```

Then fill in every placeholder (next section), start the gateway with `hermes gateway run`, and register the cron jobs. The template is the on-disk shape Hermes uses for `cron/jobs.json`; either create each job with `hermes cron create` using the name, schedule, prompt and `--no-agent --script strava_poll.py` flags shown in the template, or copy the template to `$HERMES_PROFILE_DIR/cron/jobs.json` after replacing the placeholders inside it.

## Filling in placeholders

Grep for `{{` and `${` across the copied files. Every placeholder is listed here.

### Environment-style (`${...}`)

| Placeholder | Meaning | Where |
|---|---|---|
| `${HERMES_PROFILE_DIR}` | Absolute path of the Hermes profile you created, e.g. `~/.hermes/profiles/runcoach` | `AGENTS.md`, `skills/strava_fetch/**` |
| `${COACH_VAULT}` | In-container path of the vault. The scripts default to `/wiki`; keep that unless you change the mount | `SOUL.md`, `AGENTS.md`, `config.yaml`, `skills/strava_fetch/**` |
| `${COACH_VAULT_HOST}` | Host directory that is bind-mounted to `${COACH_VAULT}` | `config.yaml` (`terminal.docker_volumes`), `.env` |

The two Python files read `COACH_VAULT` and `COACH_VAULT_HOST` from the environment at runtime, so for them it is enough to set the variables in `.env`. In the Markdown and YAML files, replace the literal `${...}` text.

### Athlete and program (`{{...}}`)

| Placeholder | Fill with |
|---|---|
| `{{ATHLETE_NAME}}` | The athlete's first name |
| `{{GOAL_RACE}}` | The current target, e.g. "10K" or "half marathon" |
| `{{GOAL_TIME}}` | The target time for that race, if there is one (used inside `{{GOAL_RACE}}` phrasing, e.g. "sub-45 10K") |
| `{{GOAL_RACE_DATE}}` | Provisional race window, e.g. "late spring" |
| `{{PREVIOUS_RACE}}`, `{{PREVIOUS_TIME}}`, `{{PREVIOUS_RACE_DATE}}` | The last benchmark the athlete banked. If there is none, delete those sentences |
| `{{LONG_TERM_GOAL}}` | The multi-year north star, e.g. "a first marathon" |
| `{{PROGRAM_START}}` | Month the coach started holding the program |
| `{{DATE}}` | Appears once in a voice example in `SOUL.md`; any past date works |
| `{{INJURY_HISTORY}}`, `{{INJURY_WATCH_AREA}}` | Past injury and the body area to watch, e.g. "Achilles tendinopathy" / "the calves and Achilles". If none, replace the paragraph with a general load-management rule |
| `{{EQUIPMENT_LIST}}` | What is in the gym |
| `{{ATHLETE_HEADLINE}}` | One or two sentences summarizing how the athlete trains and relates to data |

### Physiology (`{{...}}`)

| Placeholder | Fill with |
|---|---|
| `{{MAX_HR}}` | Confirmed max heart rate |
| `{{LTHR}}` | Lactate-threshold HR, tested or best estimate |
| `{{EASY_CADENCE}}`, `{{QUALITY_CADENCE}}`, `{{WALK_CADENCE}}` | Steps-per-minute windows for easy runs, quality runs, and walks |
| `{{RECOVERY_JOG_PACE}}` | Default jog-recovery pace between intervals, e.g. "6:30-7:30/km" |
| `{{THRESHOLD_PACE}}` | Threshold pace string the athlete uses in activity names, e.g. "4:45" |
| `{{DEVICE}}` | The watch model, e.g. "Garmin Forerunner 265" |
| `{{RHR_BASELINE}}`, `{{HRV_BASELINE}}`, `{{HR_SOURCE}}` | Memory template only |

### Schedule and location

| Placeholder | Fill with |
|---|---|
| `{{TIMEZONE}}` | IANA zone or abbreviation the athlete lives in, e.g. `America/Chicago` |
| `{{CHECKIN_TIME}}` | Local time of the morning check-in, e.g. "7:00 AM". The cron expression `0 8 * * *` in the template is server-local; change it to match |
| `{{WORKOUT_WINDOW}}` | When the athlete usually trains, used to set the Strava poll windows (see `references/auto-polling-setup.md`) |
| `{{CITY}}` | Not used in this skeleton; reserved for weather and venue skills in the full pack |

### Provider (`config.yaml`)

| Placeholder | Fill with |
|---|---|
| `{{MODEL}}`, `{{MODEL_PROVIDER}}`, `{{MODEL_BASE_URL}}` | Primary model. Examples are in the comment above the block |
| `{{FALLBACK_PROVIDER}}`, `{{FALLBACK_MODEL}}`, `{{FALLBACK_BASE_URL}}` | Optional failover; delete the `fallback_providers` list to disable |
| `{{TTS_EDGE_VOICE}}`, `{{TTS_ELEVENLABS_VOICE_ID}}`, `{{TTS_MISTRAL_VOICE_ID}}` | Only if you use voice output; otherwise leave `tts.provider: edge` and pick any Edge voice |
| `{{X_SEARCH_MODEL}}` | Only if you use the `x_search` tool |

### Memory templates

`memories/*.template.md` keep the section structure of a working coach's memory with every value blanked. Each `§`-separated block is one memory entry. Fill the ones you know, delete the ones you don't; the coach will add its own as it goes.

## The vault

`athlete-profile.md` is the canonical knowledge file: schedule, lifting structure, running prescription, zones, fueling, doc format, history, philosophy. `AGENTS.md` tells the coach to read it whenever it needs detail and to treat memory as top-of-mind state only. Write it in whatever shape you like; a good starting outline is the placeholder list above, expanded into prose.

## What is not included

This skeleton stops at reading data and talking to you. The paid full pack adds:

- **Nutrition.** FatSecret diary integration (MCP server + OAuth 1.0 setup), the daily nutrition ledger, adjusted-balance accounting, diary analysis, cut/maintenance-phase reviews and the cut-phase review cron.
- **Workout push rules.** The skill layer that turns a prescription into a Garmin Connect structured workout (targets, alerts, warm-up gates, when to leave a run unstructured) and schedules it through the Garmin MCP.
- **Session-sheet PDFs.** The ReportLab builders and the `training-session-documentation` skill that produce the one-page printable lift/run sheet plus its Markdown twin, with the verification checklist.
- **The full skill set.** Concurrent-training operations (split design, progressive-overload ledger, weekly reviews), adaptive same-day changes, Garmin health-trend analysis, pre-run weather gates, race-day playbooks, performance attempts and long-arc race progression, with the reference notes each skill draws on.

## Links

- Hermes Agent: https://github.com/NousResearch/hermes-agent
- Garmin MCP server (not bundled; installed by `uvx` from the config): https://github.com/Taxuspt/garmin_mcp
- Strava API: https://developers.strava.com/

## License

Templates in this repository are provided as-is. The Garmin MCP server and Hermes Agent are separate projects under their own licenses.
