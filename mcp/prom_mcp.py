#!/usr/bin/env python3
"""prom-mcp — read-only Prometheus tools for the infrastructure agent.

Three tools, because three is enough: an instant query, a range query, and a way
to find out what metrics exist. Everything the agent needs to reason about
latency, throttling, and error rates is a PromQL expression away, and giving the
model PromQL directly is far more useful than wrapping ten pre-baked questions
it cannot vary.

Reaches Prometheus by port-forwarding the monitoring/prometheus Service, so it
works against a kind cluster with nothing exposed on the host.
"""

from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from mcp.server import MCPServer

server = MCPServer(
    name="prom-mcp",
    instructions=(
        "Read-only PromQL access to the cluster's Prometheus. Use this for "
        "anything time-shaped: latency percentiles, error rates, CPU "
        "throttling, and whether a change is recent or long-standing. Use "
        "list_metrics first if you are unsure what is actually being collected."
    ),
)

_PORT_FORWARD: subprocess.Popen | None = None
_BASE: str | None = None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _base_url() -> str:
    """Return a reachable Prometheus base URL, starting a port-forward if needed.

    PROMETHEUS_URL short-circuits this entirely, which is what CI uses.
    """
    global _PORT_FORWARD, _BASE
    if os.environ.get("PROMETHEUS_URL"):
        return os.environ["PROMETHEUS_URL"].rstrip("/")
    if _BASE and _PORT_FORWARD and _PORT_FORWARD.poll() is None:
        return _BASE

    port = _free_port()
    kubectl = shutil.which("kubectl") or "kubectl"
    _PORT_FORWARD = subprocess.Popen(
        [kubectl, "--context", "kind-agentic-infra-labs", "-n", "monitoring",
         "port-forward", "svc/prometheus", f"{port}:9090"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    atexit.register(lambda: _PORT_FORWARD and _PORT_FORWARD.terminate())
    _BASE = f"http://127.0.0.1:{port}"

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{_BASE}/-/ready", timeout=1).read()
            return _BASE
        except Exception:
            time.sleep(0.3)
    raise RuntimeError("could not reach Prometheus — is the cluster running?")


def _get(path: str, params: dict) -> dict:
    url = f"{_base_url()}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def _format_vector(result: list) -> str:
    if not result:
        return "no data — the query returned an empty result set"
    lines = []
    for series in result:
        labels = {k: v for k, v in series["metric"].items() if k != "__name__"}
        value = series["value"][1]
        lines.append(f"{labels or '{}'}  =  {value}")
    return "\n".join(lines)


@server.tool()
def query(promql: str) -> str:
    """Run an instant PromQL query and return the current value of each series.

    Returns one line per series: its labels and its value. An empty result is
    reported as such rather than as an error — "no data" is a real answer and
    usually means the metric name or a label matcher is wrong.

    Useful expressions for this cluster:
      histogram_quantile(0.95, sum(rate(inference_request_duration_seconds_bucket[5m])) by (le, namespace))
      sum(rate(inference_requests_total[5m])) by (namespace, status)
      sum(rate(container_cpu_cfs_throttled_seconds_total{namespace="ml-prod"}[5m]))
      sum(rate(container_cpu_usage_seconds_total{namespace="ml-prod"}[5m])) by (pod)

    Cheap, and the cost is independent of the time range. Prefer this over
    query_range when you only need the current value.
    """
    try:
        data = _get("/api/v1/query", {"query": promql})
    except Exception as e:
        return f"ERROR querying Prometheus: {e}"
    if data.get("status") != "success":
        return f"ERROR: {data.get('error', 'query failed')}"
    result = data["data"]["result"]
    if data["data"]["resultType"] == "scalar":
        return str(result[1])
    return _format_vector(result)


@server.tool()
def query_range(promql: str, minutes: int = 30, step_seconds: int = 60) -> str:
    """Run a PromQL query over a time window and return the series as a small
    table of timestamped values.

    Use this — not `query` — when the question is *when did this change*. A p95
    of 480ms tells you the service is slow. The same p95 over the last 30
    minutes tells you it stepped up eight minutes ago, which is what lets you
    line it up against a rollout and turn a symptom into a cause.

    Costs tokens proportional to minutes/step_seconds. The default is 30 points.
    Do not ask for a 6-hour window at 15-second resolution.
    """
    try:
        end = time.time()
        data = _get("/api/v1/query_range", {
            "query": promql, "start": end - minutes * 60, "end": end, "step": step_seconds,
        })
    except Exception as e:
        return f"ERROR querying Prometheus: {e}"
    if data.get("status") != "success":
        return f"ERROR: {data.get('error', 'query failed')}"
    result = data["data"]["result"]
    if not result:
        return "no data — the query returned an empty result set"

    out = []
    for series in result:
        labels = {k: v for k, v in series["metric"].items() if k != "__name__"}
        out.append(f"series {labels or '{}'}")
        for ts, val in series["values"]:
            out.append(f"  {time.strftime('%H:%M:%S', time.localtime(ts))}  {val}")
    return "\n".join(out)


@server.tool()
def list_metrics(match: str = "") -> str:
    """List metric names currently present in Prometheus, optionally filtered by
    a substring.

    Use this when a query returns no data and you need to know whether the
    metric is named something else, or is not being collected at all. Those are
    different problems with different fixes, and guessing at metric names burns
    more turns than one call here.

    Cheap. Pass a substring such as "inference" or "throttl" to keep the output
    short.
    """
    try:
        data = _get("/api/v1/label/__name__/values", {})
    except Exception as e:
        return f"ERROR querying Prometheus: {e}"
    names = data.get("data", [])
    if match:
        names = [n for n in names if match.lower() in n.lower()]
    if not names:
        return f"no metric names matching {match!r}"
    return "\n".join(sorted(names)[:200])


if __name__ == "__main__":
    server.run(transport="stdio")
