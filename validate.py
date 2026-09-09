#!/usr/bin/env python3

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:8080"
TIMEOUT = 3
READY_WAIT = 30


passed = 0
failed = 0


def run_command(command):
    result = subprocess.run(
        command,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def check(name, condition, details=""):
    global passed, failed

    if condition:
        print(f"PASS: {name}" + (f" - {details}" if details else ""))
        passed += 1
    else:
        print(f"FAIL: {name}" + (f" - {details}" if details else ""))
        failed += 1


def wait_for_url(url, timeout=READY_WAIT):
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
                return response.status
        except Exception:
            time.sleep(1)

    return None


def http_get(path):
    try:
        with urllib.request.urlopen(BASE_URL + path, timeout=TIMEOUT) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body
    except Exception as exc:
        return None, str(exc)


def compose_container_running(name):
    rc, output, _ = run_command(
        f"docker inspect -f '{{{{.State.Status}}}}' {name}"
    )
    return rc == 0 and output == "running"


def container_healthy(name):
    rc, output, _ = run_command(
        f"docker inspect -f '{{{{if .State.Health}}}}{{{{.State.Health.Status}}}}{{{{else}}}}no-healthcheck{{{{end}}}}' {name}"
    )
    return rc == 0 and output in ("healthy", "no-healthcheck")


def get_networks(container):
    rc, output, _ = run_command(
        f"docker inspect -f '{{{{json .NetworkSettings.Networks}}}}' {container}"
    )

    if rc != 0:
        return {}

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {}


def get_published_ports(container):
    rc, output, _ = run_command(
        f"docker port {container}"
    )

    if rc != 0:
        return ""

    return output


def main():
    print("=== BARQ Systems Environment Validation ===")
    print()

    # ------------------------------------------------------------
    # 1. Compose configuration
    # ------------------------------------------------------------
    rc, _, _ = run_command("docker compose config -q")
    check(
        "Docker Compose configuration",
        rc == 0,
        "docker compose config -q",
    )

    # ------------------------------------------------------------
    # 2. Required containers
    # ------------------------------------------------------------
    containers = ["app-01", "app-02", "nginx", "postgres", "redis"]

    for container in containers:
        check(
            f"{container} is running",
            compose_container_running(container),
        )

    # ------------------------------------------------------------
    # 3. Container health
    # ------------------------------------------------------------
    for container in ["app-01", "app-02", "postgres", "redis"]:
        check(
            f"{container} is healthy",
            container_healthy(container),
        )

    # ------------------------------------------------------------
    # 4. Public access
    # ------------------------------------------------------------
    status = wait_for_url(BASE_URL + "/")
    check(
        "Public application access",
        status == 200,
        f"HTTP {status}" if status else "no response",
    )

    # ------------------------------------------------------------
    # 5. All required endpoints
    # ------------------------------------------------------------
    endpoints = [
        ("/", 200),
        ("/health", 200),
        ("/ready", 200),
        ("/instance", 200),
        ("/records", 200),
        ("/counter", 200),
    ]

    endpoint_results = {}

    for path, expected_status in endpoints:
        status, body = http_get(path)
        endpoint_results[path] = body

        check(
            f"Endpoint {path}",
            status == expected_status,
            f"HTTP {status}" if status is not None else "no response",
        )

    # ------------------------------------------------------------
    # 6. Readiness must report both dependencies
    # ------------------------------------------------------------
    ready_status, ready_body = http_get("/ready")

    ready_has_postgres = False
    ready_has_redis = False

    if ready_body:
        try:
            ready_json = json.loads(ready_body)
            ready_text = json.dumps(ready_json).lower()
            ready_has_postgres = "postgres" in ready_text
            ready_has_redis = "redis" in ready_text
        except json.JSONDecodeError:
            ready_text = ready_body.lower()
            ready_has_postgres = "postgres" in ready_text
            ready_has_redis = "redis" in ready_text

    check(
        "PostgreSQL readiness is reported",
        ready_status == 200 and ready_has_postgres,
    )

    check(
        "Redis readiness is reported",
        ready_status == 200 and ready_has_redis,
    )

    # ------------------------------------------------------------
    # 7. Both application backends must respond
    # ------------------------------------------------------------
    instances_seen = set()

    for _ in range(12):
        status, body = http_get("/instance")

        if status == 200:
            value = body.strip()

            if "app-01" in value:
                instances_seen.add("app-01")

            if "app-02" in value:
                instances_seen.add("app-02")

    check(
        "Both backend instances serve traffic",
        {"app-01", "app-02"}.issubset(instances_seen),
        f"observed: {', '.join(sorted(instances_seen)) or 'none'}",
    )

    # ------------------------------------------------------------
    # 8. PostgreSQL and Redis must not expose host ports
    # ------------------------------------------------------------
    postgres_ports = get_published_ports("postgres")
    redis_ports = get_published_ports("redis")

    check(
        "PostgreSQL has no published host port",
        postgres_ports == "",
        postgres_ports or "no host port",
    )

    check(
        "Redis has no published host port",
        redis_ports == "",
        redis_ports or "no host port",
    )

    # ------------------------------------------------------------
    # 9. NGINX should be frontend-only
    # ------------------------------------------------------------
    nginx_networks = set(get_networks("nginx").keys())
    app01_networks = set(get_networks("app-01").keys())
    app02_networks = set(get_networks("app-02").keys())
    postgres_networks = set(get_networks("postgres").keys())
    redis_networks = set(get_networks("redis").keys())

    check(
        "NGINX is connected to frontend network",
        any("frontend" in network for network in nginx_networks),
        f"networks: {', '.join(sorted(nginx_networks))}",
    )

    check(
        "NGINX is isolated from backend network",
        not any("backend" in network for network in nginx_networks),
        f"networks: {', '.join(sorted(nginx_networks))}",
    )

    check(
        "Application instances are connected to backend",
        any("backend" in network for network in app01_networks)
        and any("backend" in network for network in app02_networks),
    )

    check(
        "PostgreSQL is backend-only",
        any("backend" in network for network in postgres_networks)
        and not any("frontend" in network for network in postgres_networks),
        f"networks: {', '.join(sorted(postgres_networks))}",
    )

    check(
        "Redis is backend-only",
        any("backend" in network for network in redis_networks)
        and not any("frontend" in network for network in redis_networks),
        f"networks: {', '.join(sorted(redis_networks))}",
    )

    # ------------------------------------------------------------
    # 10. Final result
    # ------------------------------------------------------------
    print()
    print("=== Validation Summary ===")
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")

    if failed:
        print("VALIDATION RESULT: FAIL")
        return 1

    print("VALIDATION RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
