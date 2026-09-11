# Technical Decisions

This document records the main technical decisions made while repairing and
hardening the BARQ Systems assessment environment. Decisions are based on the
observed starter configuration, the assignment requirements, and verification
performed during troubleshooting.

## Decision 1 — Use a pinned Python base image

- Choice: Keep the application on `python:3.12-slim-bookworm` and pin the image
  by digest.
- Why: The application requires Python 3.12, while the slim Debian-based image
  keeps the runtime relatively small. Pinning the digest makes the image
  selection reproducible instead of depending on a mutable tag.
- Alternative: Use an unpinned `python:3.12` tag or a different Python base image.
- Trade-off: Digest pinning improves reproducibility but requires deliberate
  updates when the base image needs security patches.
- Evidence / commit: The pinned digest is present in the Dockerfile and was retained during the
  container hardening work; `2801eae` also records the related non-root container hardening.
- Production improvement: Automate base-image update review and vulnerability
  scanning before approving new digests.

## Decision 2 — Use application health checks

- Choice: Probe the Flask `/health` endpoint from the application container
  and use service health checks for PostgreSQL and Redis.
- Why: A running container is not necessarily a ready service. Health checks
  allow Compose and the validation scripts to distinguish a live process from
  a usable dependency.
- Alternative: Check only whether containers are running.
- Trade-off: Health checks add small periodic overhead and require sensible
  intervals, timeouts and retries.
- Evidence / commit: `f0046b4` fixed the application health probe to use the
  actual `/health` endpoint; subsequent validation passed.
- Production improvement: Add dependency-aware readiness and expose health
  metrics to the monitoring system.

## Decision 3 — Isolate frontend and backend networks

- Choice: Use separate `frontend` and `backend` Docker networks. NGINX is on
  the frontend network, PostgreSQL and Redis are backend-only, and application
  instances connect to both networks.
- Why: This limits unnecessary network reachability and follows the required
  frontend/backend separation.
- Alternative: Put every service on one shared Docker network.
- Trade-off: Network separation is more secure but makes connectivity
  configuration more deliberate.
- Evidence / commit: `7e3592a` removed backend host ports and `8bf24f6`
  isolated NGINX from the backend network. Validation verified the final
  network layout.
- Production improvement: Apply stricter network policies and separate
  management/observability traffic where required.

## Decision 4 — Use service names instead of container IP addresses

- Choice: Application connections use Compose service names such as `postgres`
  and `redis`, and NGINX uses application service names.
- Why: Container IP addresses are dynamic and should not be hardcoded into
  service configuration.
- Alternative: Configure fixed container IP addresses.
- Trade-off: Service-name based discovery depends on correct Compose networking
  and service configuration.
- Evidence / commit: `a578321` corrected the application/NGINX connectivity
  configuration, and `9b08964` corrected PostgreSQL and Redis connection
  settings.
- Production improvement: Use platform-native service discovery and explicit
  DNS/service health monitoring.

## Decision 5 — Use timeouts, retries and readiness checks

- Choice: Keep explicit HTTP timeouts in the validation/failure tests and use
  bounded health-check retries and readiness checks instead of waiting
  indefinitely.
- Why: Dependency failures and unavailable backends should fail predictably
  and allow recovery testing.
- Alternative: Use unlimited retries or very long timeouts.
- Trade-off: Short timeouts improve failure detection but can be too aggressive
  for a slow production dependency.
- Evidence / commit: `6195c50` added the backend failure recovery test and the
  validation suite verifies health/readiness behavior.
- Production improvement: Tune retry budgets using measured latency and use
  exponential backoff where appropriate.

## Decision 6 — Add restart policies and resource limits

- Choice: Use `restart: unless-stopped` for the long-running services and set
  explicit CPU/memory limits.
- Why: Restart policies improve recovery from unexpected process/container
  failures, while resource limits reduce the risk of one service consuming
  disproportionate host resources.
- Alternative: Run without restart policies or resource limits.
- Trade-off: Limits can cause a service to fail if configured too low, so they
  must be validated against actual workload requirements.
- Evidence / commit: `2451e5c` added restart policies and `fbb4fb1` added
  resource limits.
- Production improvement: Establish limits from observed resource usage and
  use orchestration-level autoscaling where appropriate.

## Decision 7 — Persist state and provide database backup/restore

- Choice: Use named Docker volumes for PostgreSQL and Redis persistence, with
  PostgreSQL backup and restore scripts using `pg_dump` and `pg_restore`.
- Why: Application container recreation must not destroy persistent database
  state, and backups provide an additional recovery mechanism.
- Alternative: Store state only inside containers or rely only on application
  recreation.
- Trade-off: Persistent storage and backups require capacity management,
  retention and recovery testing.
- Evidence / commit: `1b051de` and `3e7e9a` corrected PostgreSQL persistence;
  `6e19f2a` added and verified PostgreSQL backup/restore. Redis persistence was
  added in `fbb4fb1` and verified across Redis recreation.
- Production improvement: Store backups in durable external storage, encrypt
  them, define retention policies and perform scheduled restore tests.

## Decision 8 — Run the application as a non-root user

- Choice: Create a dedicated application user and run the Flask container as
  that non-root user.
- Why: A compromised application process should not automatically have root
  privileges inside its container.
- Alternative: Run the application as the image default/root user.
- Trade-off: File ownership and write permissions must be configured correctly.
- Evidence / commit: `2801eae` changed the application container to run as a
  dedicated non-root user.
- Production improvement: Use a read-only root filesystem where practical,
  drop unnecessary Linux capabilities and apply additional runtime security
  controls.

## Assumptions and Limits

- This is a disposable assessment environment, not a production deployment.
- Resource limits were selected for the available lab environment and should
  be re-evaluated using production workload measurements.
- Docker Compose provides the required networking and persistence behavior for
  this assessment; a production platform may require different mechanisms.
- The historical logs are synthetic training data and describe a separate
  incident from the current runtime faults.
