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

## Entry 3 / 2026-09-08 / ~4:00 PM
- Symptom: Requests through NGINX failed with "Connection reset by peer".
- Hypothesis: The Flask applications may be bound only to the container loopback interface, preventing NGINX from reaching them over the Docker network.
- Command or test: docker exec app-01 env | grep APP_HOST
- Actual output: APP_HOST=0.0.0.0 after changing the x-app configuration from 127.0.0.1 to 0.0.0.0.
- Failed attempt and what changed your thinking: The initial configuration used APP_HOST=127.0.0.1. We changed it to 0.0.0.0 and recreated the application containers. This removed the loopback binding as a possible connectivity issue, but the NGINX request still failed, so further investigation was required.
- Root cause: APP_HOST=127.0.0.1 was an incorrect configuration because the applications need to accept connections from NGINX over the Docker network. However, this was not the only cause of the observed NGINX failure.
- Fix: Changed APP_HOST from 127.0.0.1 to 0.0.0.0 in the x-app environment configuration.
- Retest evidence: Application containers reported healthy, but the request through NGINX still returned "Connection reset by peer", leading to further investigation of the NGINX ports and upstream configuration.
- Related commit: a578321
- Remaining uncertainty: NGINX upstream and port mapping still required investigation.

## Entry 4 / 2026-09-08 / ~4:15 PM
- Symptom: Requests through NGINX failed with "Connection reset by peer".
- Hypothesis: NGINX may be forwarding requests to an incorrect application port.
- Command or test:
  docker exec app-01 python -c "import socket; s=socket.socket(); print(s.connect_ex(('127.0.0.1',8080))); s.close()"
  docker exec app-01 python -c "import socket; s=socket.socket(); print(s.connect_ex(('127.0.0.1',8081))); s.close()"
  docker exec app-02 python -c "import socket; s=socket.socket(); print(s.connect_ex(('127.0.0.1',8080))); s.close()"
  docker exec app-02 python -c "import socket; s=socket.socket(); print(s.connect_ex(('127.0.0.1',8081))); s.close()"
- Actual output:
  app-01: port 8080 = 0 (open), port 8081 = 111 (connection refused)
  app-02: port 8080 = 0 (open), port 8081 = 111 (connection refused)
- Failed attempt and what changed your thinking: The initial port test stopped after the first refused connection, so each port was tested separately to obtain reliable results.
- Root cause: Two configuration mismatches caused the NGINX request failure. First, the NGINX upstream configured app-01 on port 8081 while app-01 listens on port 8080. Second, Docker published host port 8080 to NGINX container port 81 while NGINX listens on port 80.
- Fix: Changed app-01 upstream from port 8081 to 8080 in nginx/nginx.conf. Changed the NGINX Docker port mapping from 127.0.0.1:${PUBLIC_PORT:-8080}:81 to 127.0.0.1:${PUBLIC_PORT:-8080}:80 in docker-compose.yml.
- Retest evidence: docker port nginx shows 80/tcp -> 127.0.0.1:8080. curl -i http://127.0.0.1:8080/ returns HTTP/1.1 200 OK and X-Instance-ID: app-01. Ten repeated requests to /instance alternated between app-01 and app-02, confirming that NGINX can reach and load-balance both backend instances.
- Related commit: a578321
- Remaining uncertainty: None for NGINX upstream connectivity and load balancing.

## Entry 5 / 2026-09-08 / ~4:50 PM
- Symptom: GET /ready returns 503 with {"postgres":"unavailable","redis":"unavailable"}.
- Hypothesis: config/app.env has incorrect connection details (wrong port and/or password) for postgres/redis.
- Command or test: docker exec postgres printenv | grep POSTGRES_PASSWORD; docker exec redis redis-cli CONFIG GET port; docker exec postgres cat /var/lib/postgresql/data/postgresql.conf | grep -i "^port"
- Actual output: Actual postgres port=5432 (default), password ends in "...8c". Actual redis port=6379 (default). But config/app.env had DATABASE_URL with port 5433 and password ending "...8d", and REDIS_URL with port 6380.
- Failed attempt and what changed your thinking: N/A - verified actual container config directly before editing, rather than assuming which side (env file or container) was correct.
- Root cause: config/app.env contained stale/incorrect DATABASE_URL and REDIS_URL values — wrong ports (5433/6380 instead of the actual 5432/6379) and a wrong postgres password (differed by one character: "d" vs "c").
- Fix: Corrected config/app.env DATABASE_URL port to 5432 and password to match POSTGRES_PASSWORD ("...8c"); corrected REDIS_URL port to 6379.
- Retest evidence: GET /ready via NGINX returned HTTP/1.1 200 OK with {"dependencies":{"postgres":"ready","redis":"ready"},"status":"ready",...} after recreating app-01/app-02.
- Related commit:9b3489a
- Remaining uncertainty: none


## Entry 6 / 2026-09-08 / ~6:10 PM
- Symptom: (to verify) Records created via /records may not survive container recreation.
- Hypothesis: docker-compose.yml mounts the named volume postgres-data at /var/lib/postgresql/backup (wrong path), while the actual Postgres data directory /var/lib/postgresql/data is on tmpfs, which is wiped on container removal.
- Command or test: grep -A4 "postgres:" docker-compose.yml | grep -E "volumes|tmpfs"
- Actual output: volumes: postgres-data:/var/lib/postgresql/backup ; tmpfs: [/var/lib/postgresql/data]
- Root cause: The named volume is mounted at the wrong path (backup instead of data), so PGDATA (/var/lib/postgresql/data) falls back to the tmpfs mount, which is ephemeral (RAM-backed, wiped on container recreation).
- Fix: Changed volume mount to postgres-data:/var/lib/postgresql/data and removed the tmpfs line entirely.
- Retest evidence: Created record id=3 ("Persistence proof") via POST /records. Ran `docker compose up -d --force-recreate postgres app-01 app-02`. GET /records afterward still shows id=3 alongside pre-existing records — confirmed the volume now persists data correctly across container recreation.
- Related commit: (pending - filled after commit below)
- Remaining uncertainty: none


## Entry 7 / 2026-09-08 / ~7:05 PM
- Symptom: PostgreSQL and Redis ports were published on the host (127.0.0.1:15432 and 127.0.0.1:16379), although only NGINX should be publicly reachable.
- Hypothesis: Removing these host port mappings should not break app connectivity since apps reach postgres/redis via the internal backend network using service names.
- Command or test: grep -n -A12 '^  postgres:' docker-compose.yml ; grep -n -A12 '^  redis:' docker-compose.yml
- Actual output: postgres had `ports: ["127.0.0.1:15432:5432"]`; redis had `ports: ["127.0.0.1:16379:6379"]`.
- Root cause: Backend services unnecessarily exposed host ports, violating the requirement that only NGINX be published.
- Fix: Removed the `ports` entries from both postgres and redis services.
- Retest evidence: `docker port postgres` and `docker port redis` return no output (no published ports). `docker compose ps -a` still shows both healthy; app connectivity via /ready remains 200.
- Related commit: 7e3592a
- Remaining uncertainty: none

## Entry 8 / 2026-09-08 / ~7:10 PM
- Symptom: NGINX was attached to both frontend and backend networks, giving it direct network-level reach to postgres/redis.
- Hypothesis: NGINX only needs frontend (to reach app-01/app-02); backend access is unnecessary and violates the isolation requirement.
- Command or test: grep -n -A6 '^  nginx:' docker-compose.yml
- Actual output: `networks: [frontend, backend]` under the nginx service.
- Root cause: NGINX was over-privileged on the network layer.
- Fix: Changed NGINX's networks to `[frontend]` only.
- Retest evidence: `docker compose ps -a` shows nginx running; `curl -i http://127.0.0.1:8080/` still returns 200 OK, confirming NGINX→app connectivity still works over frontend alone.
- Related commit: 8bf24f6
- Remaining uncertainty: none

## Entry 9 / 2026-09-08 / ~7:20 PM
- Symptom: Dockerfile created a dedicated non-root user (app, uid 10001) but the final `USER root` line overrode it, so the container ran as root.
- Hypothesis: Changing the final USER directive to `app` should make the container run unprivileged without breaking functionality.
- Command or test: grep -n -B5 -A2 'USER root' Dockerfile
- Actual output: `USER root` was the last USER directive before CMD.
- Root cause: The image defined a least-privilege user but never switched to it at runtime.
- Fix: Changed `USER root` to `USER app` in the Dockerfile.
- Retest evidence: `docker exec app-01 id` and `docker exec app-02 id` both return `uid=10001(app) gid=10001(app) groups=10001(app)`.
- Related commit: 2801eae
- Remaining uncertainty: none

## Entry 10 / 2026-09-08 / ~7:30 PM
- Symptom: Application services had `restart: "no"`, and postgres/redis had no explicit restart policy.
- Hypothesis: Services should restart automatically after failure or Docker daemon restart, per assessment requirements.
- Command or test: grep -n 'restart:' docker-compose.yml
- Actual output: `restart: "no"` under x-app; no restart key under postgres/redis.
- Root cause: Restart behavior was not configured, so a crashed container would stay down.
- Fix: Set `restart: unless-stopped` on the x-app anchor and added the same to postgres and redis.
- Retest evidence: `docker compose ps -a` shows all five services Up and healthy after recreation with the new policy in place.
- Related commit: 2451e5c
- Remaining uncertainty: none
