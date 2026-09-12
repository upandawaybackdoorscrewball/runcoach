# Docker backend failure in cron context

## Symptom

`execute_code` and `terminal` fail with:

```
RuntimeError: Docker command is available but 'docker version' failed. Check your Docker installation.
```

## When it happens

Only in cron-triggered sessions when the Docker daemon is not reachable from the sandbox process. The host may still have a working Docker, but the cron job container cannot talk to it.

## Resolution

There is no in-session workaround. The agent cannot run scripts or access the filesystem while the backend is down.

**Correct response:** `[SILENT]` (or a one-line failure note). Let the next cron tick attempt the run.

Do NOT:
- Retry the same tool repeatedly (it'll fail identically)
- Try to fix Docker from inside the container (no privilege)
- Use `delegate_task` hoping a subagent has access (it won't)

**After the run:**
- Verify the gateway's `terminal.backend` config is still `docker`
- Check host Docker daemon status (`systemctl status docker` on the host)
- Ensure the cron job has `docker_forward_env` set in config if it needs host env vars
