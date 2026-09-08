# Troubleshooting journal

Keep chronological entries. Copy this block for each meaningful investigation.

## Entry / date / time
- Symptom:
- Hypothesis:
- Command or test:
- Actual output:
- Failed attempt and what changed your thinking:
- Root cause:
- Fix:
- Retest evidence:
- Related commit:
- Remaining uncertainty:

Do not fabricate a failed attempt just to fill the template. Record actual attempts.
## Entry 1 / 2026-09-08 / ~3:00 PM
- Symptom: app-01 and app-02 show "Up (unhealthy)" status. Logs show repeated 404 on GET /healthz.
- Hypothesis: Healthcheck is probing a path the app doesn't implement.
- Command or test: docker logs app-01
- Actual output: {"path": "/healthz", "status": 404} repeated every ~5s
- Root cause: docker-compose.yml healthcheck hits /healthz, but per assessment/APPLICATION.md the real endpoint is /health.
- Fix: Changed docker-compose.yml healthcheck test path from /healthz to /health (x-app anchor, applies to both app-01 and app-02).
- Retest evidence: docker compose -p barq-assessment ps -a shows app-01 as "Up (healthy)" after docker compose up -d.
- Related commit: (pending - will fill after commit below)
- Remaining uncertainty: none

## Entry 2 / 2026-09-08 / ~3:20 PM
- Symptom: /instance endpoint on app-02 (or via NGINX round-robin) may return the same instance_id as app-01.
- Hypothesis: app-02's INSTANCE_ID environment variable is misconfigured, duplicating app-01's value.
- Command or test: grep -A3 "app-02:" docker-compose.yml
- Actual output: INSTANCE_ID: "app-01" under the app-02 service block.
- Root cause: Copy-paste error in docker-compose.yml — app-02 service was given app-01's INSTANCE_ID instead of its own.
- Fix: Changed app-02's INSTANCE_ID to "app-02".
- Retest evidence: `docker exec app-01 ... /instance` returns {"instance_id":"app-01",...}; `docker exec app-02 ... /instance` returns {"instance_id":"app-02",...} — confirmed distinct.
- Related commit: (pending - filled after commit below)
- Remaining uncertainty: none
