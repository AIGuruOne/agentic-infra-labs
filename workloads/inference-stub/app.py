"""Inference stub — stands in for a model server.

Deliberately small. Everything the labs need to break is controlled by an env
var, because a fault you inject by editing a Deployment's env is reproducible
by a script, and a fault you inject by hand is not.

    LATENCY_MS         artificial per-request sleep
    CPU_BURN_MS        per-request BUSY work, not sleep      (scenario 04)
    FAIL_ON_BOOT       exit non-zero N seconds after start   (crashloop)
    MODEL_CONFIG_PATH  must exist at boot, else legible fail (scenario 01)
    ERROR_RATE         fraction of /predict returning 500    (0.0 - 1.0)

Endpoints: /predict, /healthz, /metrics
"""

import os
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_NAME = os.environ.get("MODEL_NAME", "sentiment-v2")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "unknown")
LATENCY_MS = int(os.environ.get("LATENCY_MS", "15"))
# Sleeping does not consume CPU, so a sleep-based delay can never be throttled
# by a CPU limit. Scenario 04 claims the agent will find throttling, so the
# work it finds has to be real: CPU_BURN_MS spins.
CPU_BURN_MS = int(os.environ.get("CPU_BURN_MS", "0"))
ERROR_RATE = float(os.environ.get("ERROR_RATE", "0.0"))
FAIL_ON_BOOT = os.environ.get("FAIL_ON_BOOT", "")
MODEL_CONFIG_PATH = os.environ.get("MODEL_CONFIG_PATH", "")

# Histogram buckets in seconds. Chosen so a 1200ms latency injection lands in a
# visibly different bucket from the ~15ms baseline — the p95 has to move enough
# to be obvious on a shared screen, not just statistically.
BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]

_lock = threading.Lock()
_counts = {"total": 0, "errors": 0}
_bucket_counts = [0] * len(BUCKETS)
_sum_seconds = 0.0


def boot_checks() -> None:
    """Fail loudly and legibly, or not at all.

    An agent reading container logs can only diagnose what the container
    actually says. 'FileNotFoundError' with the path in it is diagnosable;
    a bare non-zero exit is not.
    """
    if MODEL_CONFIG_PATH:
        if not os.path.exists(MODEL_CONFIG_PATH):
            print(
                f"FATAL: model config not found at {MODEL_CONFIG_PATH!r}\n"
                f"FATAL: {MODEL_NAME} cannot start without its config file.\n"
                f"FATAL: check the MODEL_CONFIG_PATH env var on this deployment.",
                file=sys.stderr,
                flush=True,
            )
            sys.exit(1)
        print(f"loaded model config from {MODEL_CONFIG_PATH}", flush=True)

    if FAIL_ON_BOOT:
        delay = int(FAIL_ON_BOOT)

        def _die() -> None:
            time.sleep(delay)
            print(f"FATAL: FAIL_ON_BOOT set — exiting after {delay}s", file=sys.stderr, flush=True)
            os._exit(1)

        threading.Thread(target=_die, daemon=True).start()


def observe(seconds: float, is_error: bool) -> None:
    global _sum_seconds
    with _lock:
        _counts["total"] += 1
        if is_error:
            _counts["errors"] += 1
        _sum_seconds += seconds
        # Store non-cumulatively — exactly one bucket per observation. The
        # cumulative form Prometheus expects is built at render time. Storing
        # cumulatively here and cumulating again there is the classic way to
        # get a p95 that reports the top bucket for every request.
        for i, edge in enumerate(BUCKETS):
            if seconds <= edge:
                _bucket_counts[i] += 1
                break


def render_metrics() -> str:
    with _lock:
        total, errors, ssum = _counts["total"], _counts["errors"], _sum_seconds
        buckets = list(_bucket_counts)

    labels = f'model="{MODEL_NAME}",environment="{ENVIRONMENT}"'
    out = [
        "# HELP inference_requests_total Total inference requests handled.",
        "# TYPE inference_requests_total counter",
        f'inference_requests_total{{{labels},status="ok"}} {total - errors}',
        f'inference_requests_total{{{labels},status="error"}} {errors}',
        "# HELP inference_request_duration_seconds Inference request latency.",
        "# TYPE inference_request_duration_seconds histogram",
    ]
    cumulative = 0
    for edge, count in zip(BUCKETS, buckets):
        cumulative += count
        out.append(f'inference_request_duration_seconds_bucket{{{labels},le="{edge}"}} {cumulative}')
    out.append(f'inference_request_duration_seconds_bucket{{{labels},le="+Inf"}} {total}')
    out.append(f"inference_request_duration_seconds_sum{{{labels}}} {ssum:.6f}")
    out.append(f"inference_request_duration_seconds_count{{{labels}}} {total}")
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _respond(self, code: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:
        payload = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]
        if path == "/healthz":
            self._respond(200, '{"status":"ok"}\n', "application/json")
        elif path == "/metrics":
            self._respond(200, render_metrics())
        elif path == "/predict":
            self.handle_predict()
        else:
            self._respond(404, "not found\n")

    do_POST = do_GET

    def handle_predict(self) -> None:
        start = time.perf_counter()
        if LATENCY_MS:
            time.sleep(LATENCY_MS / 1000.0)
        if CPU_BURN_MS:
            deadline = time.perf_counter() + CPU_BURN_MS / 1000.0
            x = 0
            while time.perf_counter() < deadline:
                x += 1  # noqa: F841  — the point is the cycles, not the value
        is_error = ERROR_RATE > 0 and random.random() < ERROR_RATE
        elapsed = time.perf_counter() - start
        observe(elapsed, is_error)
        if is_error:
            self._respond(500, '{"error":"inference backend unavailable"}\n', "application/json")
        else:
            self._respond(
                200,
                f'{{"model":"{MODEL_NAME}","environment":"{ENVIRONMENT}","label":"positive","score":0.94}}\n',
                "application/json",
            )

    def log_message(self, *args) -> None:  # keep pod logs about faults, not traffic
        pass


if __name__ == "__main__":
    boot_checks()
    print(f"{MODEL_NAME} serving on :8080 (env={ENVIRONMENT}, latency={LATENCY_MS}ms, cpu_burn={CPU_BURN_MS}ms, error_rate={ERROR_RATE})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
