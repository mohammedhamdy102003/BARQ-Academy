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
- Related commit: Pending.
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
- Related commit: Pending.
- Remaining uncertainty: None for NGINX upstream connectivity and load balancing.
