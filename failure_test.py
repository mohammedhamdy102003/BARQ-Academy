#!/usr/bin/env python3

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import os


PUBLIC_PORT = os.getenv("PUBLIC_PORT", "8080")
BASE_URL = f"http://127.0.0.1:{PUBLIC_PORT}"
TARGET = os.getenv("TARGET", "app-02")
REQUEST_COUNT = 20
REQUEST_TIMEOUT = 3
RECOVERY_TIMEOUT = 30


def run(command):
    result = subprocess.run(
        command,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def http_get(path="/instance"):
    try:
        with urllib.request.urlopen(
            BASE_URL + path,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception:
        return None, ""


def measure_traffic(count):
    success = 0
    errors = 0
    instances = {}

    for _ in range(count):
        status, body = http_get("/instance")

        if status == 200:
            success += 1

            if "app-01" in body:
                instances["app-01"] = instances.get("app-01", 0) + 1

            if "app-02" in body:
                instances["app-02"] = instances.get("app-02", 0) + 1
        else:
            errors += 1

    return success, errors, instances


def wait_for_container_running(container, timeout=RECOVERY_TIMEOUT):
    deadline = time.time() + timeout

    while time.time() < deadline:
        rc, output, _ = run(
            f"docker inspect -f '{{{{.State.Status}}}}' {container}"
        )

        if rc == 0 and output == "running":
            return True

        time.sleep(1)

    return False


def wait_for_healthy(container, timeout=RECOVERY_TIMEOUT):
    deadline = time.time() + timeout

    while time.time() < deadline:
        rc, output, _ = run(
            f"docker inspect -f '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}no-healthcheck{{{{end}}}}' {container}"
        )

        if rc == 0 and output in ("healthy", "no-healthcheck"):
            return True

        time.sleep(1)

    return False


def restore_target():
    print()
    print(f"Restoring {TARGET}...")

    rc, _, stderr = run(
        f"docker compose up -d {TARGET}"
    )

    if rc != 0:
        print(f"FAIL: unable to restore {TARGET}")
        if stderr:
            print(stderr)

        return False

    if not wait_for_container_running(TARGET):
        print(f"FAIL: {TARGET} did not return to running state")
        return False

    if not wait_for_healthy(TARGET):
        print(f"FAIL: {TARGET} did not become healthy")
        return False

    print(f"PASS: {TARGET} restored and healthy")
    return True


def main():
    print("=== BARQ Systems Failure / Recovery Test ===")
    print(f"Target backend: {TARGET}")
    print()

    # Make sure the target belongs to this Compose project.
    rc, project, _ = run(
        f"docker inspect -f '{{{{index .Config.Labels \"com.docker.compose.project\"}}}}' {TARGET}"
    )

    if rc != 0 or project != "barq-assessment":
        print("FAIL: target container is not part of barq-assessment")
        return 1

    print("PASS: target container belongs to barq-assessment")

    # ------------------------------------------------------------
    # Baseline
    # ------------------------------------------------------------
    baseline_success, baseline_errors, baseline_instances = measure_traffic(
        REQUEST_COUNT
    )

    print()
    print("Baseline traffic:")
    print(f"  successful requests: {baseline_success}")
    print(f"  errors: {baseline_errors}")
    print(
        f"  instances: "
        f"{json.dumps(baseline_instances, sort_keys=True)}"
    )

    if baseline_success == 0:
        print("FAIL: baseline traffic is unavailable")
        return 1

    print("PASS: baseline traffic is available")

    # ------------------------------------------------------------
    # Stop one backend
    # ------------------------------------------------------------
    print()
    print(f"Stopping {TARGET}...")

    rc, _, stderr = run(
        f"docker compose stop {TARGET}"
    )

    if rc != 0:
        print("FAIL: could not stop target backend")
        if stderr:
            print(stderr)

        return 1

    print(f"PASS: {TARGET} stopped")

    try:
        # --------------------------------------------------------
        # Traffic during failure
        # --------------------------------------------------------
        failure_success, failure_errors, failure_instances = measure_traffic(
            REQUEST_COUNT
        )

        print()
        print("Traffic during backend failure:")
        print(f"  successful requests: {failure_success}")
        print(f"  errors: {failure_errors}")
        print(
            f"  instances: "
            f"{json.dumps(failure_instances, sort_keys=True)}"
        )

        # With one backend stopped, the remaining backend must
        # continue serving requests.
        check_remaining_backend = failure_instances.get("app-01", 0) > 0

        if check_remaining_backend:
            print("PASS: remaining backend served traffic")
        else:
            print("FAIL: remaining backend did not serve traffic")

        if failure_success > 0:
            print("PASS: service remained available during backend failure")
        else:
            print("FAIL: service became completely unavailable")

        if failure_errors < REQUEST_COUNT:
            print(
                "PASS: not all requests failed during backend failure"
            )
        else:
            print(
                "FAIL: all requests failed during backend failure"
            )

    finally:
        # --------------------------------------------------------
        # Always restore the target backend.
        # --------------------------------------------------------
        recovered = restore_target()

    if not recovered:
        print()
        print("FAIL: recovery failed")
        return 1

    # ------------------------------------------------------------
    # Recovery verification
    # ------------------------------------------------------------
    recovery_success, recovery_errors, recovery_instances = measure_traffic(
        REQUEST_COUNT
    )

    print()
    print("Traffic after recovery:")
    print(f"  successful requests: {recovery_success}")
    print(f"  errors: {recovery_errors}")
    print(
        f"  instances: "
        f"{json.dumps(recovery_instances, sort_keys=True)}"
    )

    target_recovered = recovery_instances.get(TARGET, 0) > 0

    if target_recovered:
        print(f"PASS: recovered backend {TARGET} served requests")
    else:
        print(f"FAIL: recovered backend {TARGET} did not serve requests")

    if recovery_success > 0:
        print("PASS: service available after recovery")
    else:
        print("FAIL: service unavailable after recovery")

    print()
    print("=== Failure Test Summary ===")

    total_failures = 0

    if not check_remaining_backend:
        total_failures += 1

    if failure_success == 0:
        total_failures += 1

    if not recovered:
        total_failures += 1

    if not target_recovered:
        total_failures += 1

    if recovery_success == 0:
        total_failures += 1

    print(f"Checks failed: {total_failures}")

    if total_failures:
        print("FAILURE TEST RESULT: FAIL")
        return 1

    print("FAILURE TEST RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
