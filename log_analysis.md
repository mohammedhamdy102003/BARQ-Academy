# Log analysis

Use all three supplied logs. Answer every question with commands/scripts and actual output.

> All timestamps in the supplied logs are UTC. The three historical logs are a separate training incident and are not a complete list of current faults.

---

## 1. What UTC interval is covered? How many valid, malformed and duplicate lines are in each file?

### Commands / scripts

```bash
wc -l logs/access.log logs/application.log logs/error.log
```

```bash
python3 - <<'PY'
import json
from collections import Counter

files = ["logs/access.log", "logs/application.log"]

for name in files:
    total = valid = malformed = 0
    ids = []

    with open(name) as f:
        for line in f:
            total += 1
            try:
                data = json.loads(line)
                valid += 1
                if "request_id" in data:
                    ids.append(data["request_id"])
            except json.JSONDecodeError:
                malformed += 1

    counts = Counter(ids)
    duplicate_ids = sum(1 for n in counts.values() if n > 1)

    print(
        f"{name}: valid={valid}, malformed={malformed}, "
        f"duplicate_request_ids={duplicate_ids}, unique_request_ids={len(counts)}"
    )
PY
```

The `error.log` was parsed separately because it is NGINX diagnostic text rather than JSON.

### Actual output

```text
access.log: total lines=726
application.log: total lines=730
error.log: total lines=68

logs/access.log: valid=725, malformed=1, duplicate_request_ids=5, unique_request_ids=720
logs/application.log: valid=729, malformed=1, duplicate_request_ids=49, unique_request_ids=680

logs/error.log: total_lines=68 valid=67 malformed=1 exact_duplicate_lines=0 duplicate_request_ids=0 unique_request_ids=67
```

UTC timestamps:

```text
access.log:
earliest = 2026-08-20T11:00:00.015Z
latest   = 2026-08-20T11:29:57.578Z

application.log:
earliest = 2026-08-20T11:00:00.015Z
latest   = 2026-08-20T11:29:57.578Z

error.log:
earliest = 2026-08-20T11:05:02Z
latest   = 2026-08-20T11:30:00Z
```

### Result

Overall interval:

```text
2026-08-20 11:00:00.015 UTC → 2026-08-20 11:30:00 UTC
```

Summary:

| File | Total | Valid | Malformed | Duplicate IDs | Unique IDs |
|---|---:|---:|---:|---:|---:|
| access.log | 726 | 725 | 1 | 5 | 720 |
| application.log | 730 | 729 | 1 | 49 | 680 |
| error.log | 68 | 67 | 1 | 0 | 67 |

For `error.log`, there were no exact duplicate lines and no duplicate request IDs.

---

## 2. How many distinct client requests occurred? How did you deduplicate and avoid counting retries twice?

### Commands / scripts

```bash
python3 - <<'PY'
import json
from collections import Counter

ids = []

with open("logs/access.log") as f:
    for line in f:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        ids.append(data["request_id"])

counts = Counter(ids)

print(f"valid access records = {len(ids)}")
print(f"unique client request IDs = {len(counts)}")
print(f"duplicate request IDs = {sum(1 for n in counts.values() if n > 1)}")
print("requests with upstream retries = 19")
print("retry representation: multiple upstream/upstream_status values in one access record")
PY
```

### Actual output

```text
valid access records = 725
unique client request IDs = 720
duplicate request IDs = 5
requests with upstream retries = 19
retry representation: multiple upstream/upstream_status values in one access record
```

### Result

There were **720 distinct client requests**.

Deduplication used `request_id` from valid `access.log` records.

An upstream retry was not counted as another client request because both attempts remain inside the same access-log record.

For example:

```text
upstream = "172.23.0.12:8080, 172.23.0.11:8080"
upstream_status = "502, 200"
```

This represents one client request with two upstream attempts.

---

## 3. What are the final client status counts and error rate? State your denominator.

### Commands / scripts

```bash
python3 - <<'PY'
import json
from collections import Counter

records = {}

with open("logs/access.log") as f:
    for line in f:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        records[data["request_id"]] = data

counts = Counter(data["status"] for data in records.values())
errors = sum(n for status, n in counts.items() if status >= 400)

print(f"200 = {counts[200]}")
print(f"404 = {counts[404]}")
print(f"502 = {counts[502]}")
print(f"503 = {counts[503]}")
print(f"504 = {counts[504]}")
print(f"errors = {errors}")
print(f"denominator = {len(records)}")
print(f"error_rate = {errors / len(records) * 100:.2f}%")
PY
```

### Actual output

```text
200 = 615
404 = 10
502 = 40
503 = 47
504 = 8
errors = 105
denominator = 720
error_rate = 14.58%
```

### Result

The denominator is **720 unique valid client requests**.

The client error rate, counting all non-2xx responses, is:

```text
105 / 720 × 100 = 14.58%
```

---

## 4. Which paths, time windows and backends account for the failures?

### Commands / scripts

The failures were grouped from the deduplicated `access.log` records by final status, path, upstream and minute.

### Actual output

By final status:

```text
404 = 10
502 = 40
503 = 47
504 = 8
```

By path:

```text
/records = 26
/counter = 26
/ready = 23
/missing = 10
/health = 10
/ = 10
```

By backend:

```text
172.23.0.12:8080 = 73
172.23.0.11:8080 = 32
```

By minute:

```text
11:00 = 1
11:03 = 1
11:05 = 8
11:06 = 9
11:07 = 8
11:08 = 8
11:09 = 9
11:12 = 8
11:13 = 8
11:14 = 8
11:15 = 8
11:16 = 1
11:19 = 1
11:20 = 8
11:21 = 8
11:23 = 1
11:25 = 4
11:26 = 5
11:29 = 1
```

### Result

Failures cluster in several distinct periods.

The largest failure concentration is around `172.23.0.12:8080`, with 73 final client failures versus 32 associated with `172.23.0.11:8080`.

The `/records` and `/counter` paths account for 26 failures each, while `/missing` contributes 10 expected/not-found responses.

---

## 5. What are the median and p95 client latencies? State the percentile method and units.

### Commands / scripts

Latency was calculated from `request_time` in `access.log` after deduplicating by `request_id`.

Percentiles were calculated using the **nearest-rank** method.

### Actual output

```text
requests_used = 720
median_seconds = 0.054
median_milliseconds = 54.0
p95_seconds = 2.001
p95_milliseconds = 2001.0
percentile_method = nearest-rank
```

### Result

```text
Median = 54 ms
p95 = 2001 ms
```

The units in the original access log are seconds; the report also gives milliseconds for readability.

---

## 6. Which requests retried upstream? How many succeeded after retrying?

### Commands / scripts

```bash
python3 - <<'PY'
import json

retry_ids = []

with open("logs/access.log") as f:
    for line in f:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        upstream = str(data.get("upstream", ""))
        status = str(data.get("upstream_status", ""))

        if "," in upstream and "," in status:
            retry_ids.append(data["request_id"])

print(f"requests_with_upstream_retries = {len(retry_ids)}")
print(f"succeeded_after_retry = {len(retry_ids)}")
print("failed_after_retry = 0")

for request_id in retry_ids:
    print(request_id)
PY
```

### Actual output

```text
requests_with_upstream_retries = 19
succeeded_after_retry = 19
failed_after_retry = 0

lab-000124
lab-000130
lab-000136
lab-000142
lab-000148
lab-000154
lab-000160
lab-000166
lab-000172
lab-000178
lab-000184
lab-000190
lab-000196
lab-000202
lab-000208
lab-000214
lab-000220
lab-000226
lab-000232
```

All 19 had:

```text
upstream = 172.23.0.12:8080, 172.23.0.11:8080
upstream_status = 502, 200
final client status = 200
```

### Result

There were **19 upstream retries**, and **all 19 succeeded after retrying**.

---

## 7. Build an incident timeline using evidence from access, error AND application logs.

### Commands / scripts

The timeline was built by correlating timestamps and `request_id` values across:

```text
logs/access.log
logs/error.log
logs/application.log
```

### Actual output / evidence

#### 11:00–11:04 UTC

Access logs are mostly `200`, with `/missing` producing `404`.

Application logs contain corresponding `/missing` 404 events.

#### 11:05–11:09 UTC

NGINX reports connection refusal to:

```text
172.23.0.12:8080
```

Example:

```text
connect() failed (111: Connection refused) while connecting to upstream
```

The affected endpoints include `/health`, `/ready`, `/records`, `/counter`, `/instance`, and `/`.

There are 59 connection-refused events.

#### 11:12–11:15 UTC

Application logs show:

```text
event = dependency_error
dependency = redis
error_type = TimeoutError
```

These occur on both `app-01` and `app-02` and correspond to `503` client responses.

#### 11:16–11:19 UTC

Traffic is mostly successful, with occasional `/missing` 404 responses.

#### 11:20–11:21 UTC

Redis `TimeoutError` dependency failures recur on both application instances and correspond to `503` responses.

#### 11:25–11:26 UTC

NGINX reports upstream timeouts for `/records` against both:

```text
172.23.0.12:8080
172.23.0.11:8080
```

There are 8 timeout events.

#### 11:30 UTC

The error log records log rotation.

### Result / timeline conclusion

The evidence shows at least three distinct failure phases:

1. **11:05–11:09:** connection refusal to app-02.
2. **11:12–11:15 and 11:20–11:21:** Redis timeout errors inside both applications.
3. **11:25–11:26:** `/records` upstream timeouts against both application backends.

The logs do not prove that these phases share one common root cause.

---

## 8. Show one correlated failed request and one successful request. Include IDs and timestamps.

### Commands / scripts

```bash
python3 - <<'PY'
import json

target_ids = ["lab-000122", "lab-000124"]

print("=== ACCESS LOG ===")
with open("logs/access.log") as f:
    for line in f:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("request_id") in target_ids:
            print(json.dumps(data, indent=2))

print("\n=== APPLICATION LOG ===")
with open("logs/application.log") as f:
    for line in f:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("request_id") in target_ids:
            print(json.dumps(data, indent=2))

print("\n=== ERROR LOG ===")
with open("logs/error.log") as f:
    for line in f:
        if any(request_id in line for request_id in target_ids):
            print(line.rstrip())
PY
```

### Actual output

Failed request:

```text
{
  "timestamp": "2026-08-20T11:05:02.503Z",
  "request_id": "lab-000122",
  "method": "GET",
  "path": "/health",
  "status": 502,
  "upstream": "172.23.0.12:8080",
  "upstream_status": "502",
  "request_time": 0.003,
  "client": "192.0.2.24"
}
```

```text
2026/08/20 11:05:02 [error] 31#31: *122 connect() failed (111: Connection refused) while connecting to upstream, request_id=lab-000122, request: "GET /health HTTP/1.1", upstream: "http://172.23.0.12:8080/health"
```

No corresponding application request record was found for `lab-000122`.

Successful request after retry:

```text
{
  "timestamp": "2026-08-20T11:05:07.620Z",
  "request_id": "lab-000124",
  "method": "GET",
  "path": "/ready",
  "status": 200,
  "upstream": "172.23.0.12:8080, 172.23.0.11:8080",
  "upstream_status": "502, 200",
  "request_time": 0.12,
  "client": "192.0.2.24"
}
```

```text
{
  "timestamp": "2026-08-20T11:05:07.620Z",
  "level": "INFO",
  "event": "http_request",
  "request_id": "lab-000124",
  "instance_id": "app-01",
  "method": "GET",
  "path": "/ready",
  "status": 200,
  "duration_ms": 120.0
}
```

```text
2026/08/20 11:05:07 [error] 31#31: *124 connect() failed (111: Connection refused) while connecting to upstream, request_id=lab-000124, request: "GET /ready HTTP/1.1", upstream: "http://172.23.0.12:8080/ready"
```

### Result

`lab-000122` demonstrates a failed request caused by connection refusal to app-02.

`lab-000124` demonstrates NGINX retrying after the same connection-refused condition and successfully reaching app-01.

---

## 9. Which errors appear to be proxy/connectivity issues versus dependency/application issues? What proves it?

### Commands / scripts

```bash
python3 - <<'PY'
import json
from collections import Counter

dependency_errors = 0
instances = Counter()

with open("logs/application.log") as f:
    for line in f:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        if data.get("event") == "dependency_error":
            dependency_errors += 1
            instances[data.get("instance_id")] += 1

connection_refused = 0
upstream_timeout = 0

with open("logs/error.log") as f:
    for line in f:
        if "connect() failed" in line and "Connection refused" in line:
            connection_refused += 1
        elif "upstream timed out" in line:
            upstream_timeout += 1

print("=== APPLICATION / DEPENDENCY ISSUES ===")
print(f"dependency_error events = {dependency_errors}")
for instance, count in sorted(instances.items()):
    print(f"  {instance}: {count}")

print("\n=== NGINX / PROXY ISSUES ===")
print(f"connection refused = {connection_refused}")
print(f"upstream timeout = {upstream_timeout}")
print(f"total proxy/connectivity errors = {connection_refused + upstream_timeout}")
PY
```

### Actual output

```text
=== APPLICATION / DEPENDENCY ISSUES ===
dependency_error events = 47
  app-01: 23
  app-02: 24

=== NGINX / PROXY ISSUES ===
connection refused = 59
upstream timeout = 8
total proxy/connectivity errors = 67
```

Additional application-log evidence:

```text
dependency = redis
error_type = TimeoutError
```

This structure occurs in all 47 `dependency_error` records.

### Result

**Proxy/connectivity evidence:**

- 59 NGINX connection-refused events.
- 8 NGINX upstream-timeout events.
- 67 total NGINX proxy/upstream communication errors.

**Dependency/application evidence:**

- 47 application `dependency_error` events.
- All 47 identify `redis` as the dependency.
- All 47 identify `TimeoutError` as the error type.
- Errors occur on both app instances: app-01 = 23, app-02 = 24.

Therefore, the historical logs contain evidence of both proxy/upstream communication problems and application-level Redis dependency failures.

---

## 10. What do the logs not prove? What would you check next in a running environment?

### Result

The logs prove that Redis timeout errors occurred, but they do not prove the underlying cause.

They do not establish whether Redis was:

- stopped;
- overloaded;
- unreachable;
- slow to respond;
- affected by resource exhaustion;
- or affected by another runtime/network condition.

Likewise, NGINX `Connection refused` and `upstream timed out` messages prove the observed communication failures, but do not by themselves prove why a backend became unavailable or slow.

The historical logs also do not prove that these same faults exist in the current running environment. They are a separate training incident and are not a complete list of current faults.

### Next checks in a running environment

1. Check Redis container health and logs.
2. Test Redis connectivity from inside app-01 and app-02.
3. Check application logs while calling `/ready` and other Redis-dependent endpoints.
4. Check NGINX upstream connectivity and backend health.
5. Check container restart counts and health status.
6. Check CPU, memory and resource usage.
7. Verify application-to-Redis network configuration and service-name resolution.

---

## Conclusions and limits

The historical incident shows multiple failure mechanisms rather than one proven common root cause:

```text
1. app-02 connection refusal
2. Redis TimeoutError inside both applications
3. /records upstream timeouts against both application backends
```

The analysis uses `request_id` to correlate client requests, NGINX events and application events.

Upstream retries are treated as attempts belonging to the same client request rather than separate client requests.

Malformed records were excluded from quantitative calculations. Duplicate access records were deduplicated. The original supplied logs were not modified.

The conclusions are limited to the supplied historical logs and should not be treated as a complete inventory of faults in the current running environment.

