# Security and Production-Readiness Review

This review covers concrete security, reliability and production-readiness
risks identified during the repair of the assessment environment. Completed
changes are separated from production follow-up recommendations.

## Finding 1 — Database credentials in repository history

- Risk and evidence: The starter configuration contained database credentials
  in a tracked configuration file. The original value remains in Git history
  because the assessment history was intentionally preserved.
- Impact: Anyone with access to the repository history could retrieve the
  historical credential.
- Implemented fix / commit: Removed the tracked application environment file,
  moved the password to the ignored `.env` file, and supplied `.env.example`
  without a real secret. Commit `d354b38`.
- Production follow-up: Revoke/rotate any credential that was ever exposed
  and use a dedicated secret manager such as AWS Secrets Manager, Azure Key
  Vault or an equivalent service.
- How to verify: Confirm `config/app.env` is absent from the working tree,
  `.env` is ignored, and the application image does not contain the old
  configuration file or password assignment.

## Finding 2 — Backend services should not expose host ports

- Risk and evidence: PostgreSQL and Redis did not need to be reachable from
  the host because applications communicate with them through the Docker
  backend network.
- Impact: Unnecessary host exposure increases the attack surface and could
  allow direct access to infrastructure services.
- Implemented fix / commit: Removed host port mappings from PostgreSQL and
  Redis in commit `7e3592a`.
- Production follow-up: Keep databases and caches on private networks or
  private subnets and restrict access with firewall/security-group rules.
- How to verify: Run `docker compose ps` and inspect the Compose
  configuration; only NGINX should publish the application entry point.

## Finding 3 — Application containers should not run as root

- Risk and evidence: Running an application process as root increases the
  potential impact of an application compromise.
- Impact: A successful application-level compromise could gain unnecessary
  privileges inside the container.
- Implemented fix / commit: Added a dedicated application user and configured
  the image to run as that user. Commit `2801eae`.
- Production follow-up: Use a read-only root filesystem where practical, drop
  unnecessary Linux capabilities and apply additional container runtime
  security controls.
- How to verify: Inspect the running application container with
  `docker exec app-01 id` and confirm it is not running as root.

## Finding 4 — Container image reproducibility

- Risk and evidence: Mutable image tags can change over time and make builds
  less reproducible.
- Impact: A rebuild could unexpectedly use a different image version.
- Implemented fix / commit: The pinned image digests were retained from the
  supplied baseline and verified during the review. No repair commit was
  required for this specific control.
- Production follow-up: Maintain a controlled image-update process, scan
  images for vulnerabilities and review digest changes before deployment.
- How to verify: Inspect the `FROM` line in `Dockerfile` and the image
  references in `docker-compose.yml`.

## Finding 5 — Frontend/backend network isolation

- Risk and evidence: NGINX should not have direct network access to
  PostgreSQL or Redis.
- Impact: Unnecessary connectivity increases lateral-movement opportunities
  if the frontend component is compromised.
- Implemented fix / commit: Removed NGINX from the backend network in
  `8bf24f6`; application instances remain connected to the backend network.
- Production follow-up: Apply explicit network policies/firewall rules and
  isolate management and observability traffic where appropriate.
- How to verify: Run the validation suite and inspect service network
  attachments. NGINX should be frontend-only, while PostgreSQL and Redis
  should be backend-only.

## Finding 6 — Persistent state and recovery

- Risk and evidence: Container recreation must not destroy application data.
  The original PostgreSQL storage configuration did not provide the required
  persistence behavior.
- Impact: Data loss could occur after container recreation or replacement.
- Implemented fix / commit: Corrected PostgreSQL volume mounting in
  `1b051de` and `3e7e9a`. Added PostgreSQL backup/restore in `6e19f2a`.
  Redis persistence was added and verified in `fbb4fb1`.
- Production follow-up: Store backups in durable external storage, encrypt
  them, define retention policies and perform scheduled restore tests.
- How to verify: Create a record, recreate the application/PostgreSQL
  containers and confirm the record remains. Run `backup.sh` and
  `restore.sh` and verify the database contents.

## Finding 7 — Logging should not expose secrets

- Risk and evidence: Connection strings or credentials can accidentally be
  exposed through application configuration or logs.
- Impact: Logs are commonly collected and retained outside the application
  host, increasing the impact of accidental credential disclosure.
- Implemented fix / commit: Application startup logging was changed to report
  only whether database and Redis configuration is present, rather than
  logging connection credentials. Commit `d354b38`.
- Production follow-up: Centralize logs, restrict log access, define retention
  policies and add secret-detection controls to CI/CD.
- How to verify: Inspect application startup logs and confirm credentials are
  not printed.

## Finding 8 — Service availability and automatic recovery

- Risk and evidence: Containers can stop because of process failures or
  transient runtime problems.
- Impact: A stopped service can interrupt requests and reduce availability.
- Implemented fix / commit: Added `restart: unless-stopped` policies in
  `2451e5c` and resource limits in `fbb4fb1`.
- Production follow-up: Use orchestration-level health-based replacement,
  autoscaling and multiple failure domains for production workloads.
- How to verify: Inspect `docker compose ps` and the Compose configuration for
  restart policies and configured CPU/memory limits.

## Finding 9 — Resource exhaustion

- Risk and evidence: Containers without resource boundaries can consume an
  excessive amount of host CPU or memory.
- Impact: One service can degrade or destabilize other services on the same
  host.
- Implemented fix / commit: Added explicit CPU and memory limits for the
  application, PostgreSQL, Redis and NGINX services in `fbb4fb1`.
- Production follow-up: Tune limits using observed workload metrics and use
  capacity planning and autoscaling in production.
- How to verify: Inspect the Compose configuration and Docker container
  resource settings.

## Finding 10 — Dependency health, timeouts and failure handling

- Risk and evidence: Application availability depends on PostgreSQL, Redis
  and backend connectivity. The historical logs also demonstrate connection
  failures, timeouts and dependency errors.
- Impact: Without bounded checks and failure handling, requests can hang or
  fail unpredictably during dependency or backend failures.
- Implemented fix / commit: Corrected the application health endpoint in
  `f0046b4`, added the environment validation suite in `732e4fc`, and added
  backend failure recovery testing in `6195c50`. The validation and failure
  checks also use bounded HTTP timeouts.
- Production follow-up: Tune timeout and retry budgets from measured
  production latency, use appropriate exponential backoff and add alerting
  for dependency failures.
- How to verify: Run `validate.py`, run `failure_test.py`, inspect container
  health status and confirm recovery after the failed backend is restored.

## Assessment Environment Limitations

- This is a disposable Docker Compose assessment environment, not a
  production deployment.
- The database credential that existed in the starter Git history must be
  treated as exposed and should be rotated in any real environment.
- The resource limits were selected for the lab and should not be copied to a
  production workload without measurement.
- Docker Compose provides the required network isolation and persistence model
  for this exercise; production infrastructure may require stronger
  isolation, external storage and managed secret services.
