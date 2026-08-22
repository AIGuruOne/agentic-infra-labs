#!/usr/bin/env bash
# verify.sh — post-cluster health table. One row per check, PASS or FAIL.
#
# Exits non-zero if anything FAILs, so `make cluster` and CI can gate on it.
#
# Note the GPU row: it repairs rather than reports. Extended resources set on
# node status do not survive a kubelet restart, so a laptop that slept between
# `make cluster` and the session would otherwise wake up broken. Re-applying is
# the correct behaviour, not a workaround.

set -uo pipefail
cd "$(dirname "$0")/.."

CLUSTER="agentic-infra-labs"
KUBECTL=(kubectl --context "kind-${CLUSTER}")

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
GREEN=$'\033[32m'; RED=$'\033[31m'
FAILED=0

row() {
  local name="$1" status="$2" detail="${3:-}" color="$GREEN"
  [ "$status" = "FAIL" ] && { color="$RED"; FAILED=1; }
  printf "  %-38s ${color}%-6s${RESET} ${DIM}%s${RESET}\n" "$name" "$status" "$detail"
}

ready_count() { "${KUBECTL[@]}" -n "$1" get pods -l "app=$2" \
  -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' 2>/dev/null | grep -c True; }

echo
echo "${BOLD}agentic-infra-labs · cluster health${RESET}"
echo

# --- control plane ----------------------------------------------------------
if "${KUBECTL[@]}" cluster-info >/dev/null 2>&1; then
  row "API server reachable" PASS "kind-${CLUSTER}"
else
  row "API server reachable" FAIL "run 'make cluster'"
  echo; exit 1
fi

NODES=$("${KUBECTL[@]}" get nodes -o jsonpath='{range .items[*]}{.status.conditions[?(@.type=="Ready")].status}{"\n"}{end}' 2>/dev/null | grep -c True || true)
[ "${NODES:-0}" -eq 3 ] && row "Nodes Ready" PASS "3/3" || row "Nodes Ready" FAIL "${NODES:-0}/3"

# --- GPU simulation (repairs) -----------------------------------------------
GPU_NODE="${CLUSTER}-worker2"
GPU=$("${KUBECTL[@]}" get node "$GPU_NODE" -o jsonpath='{.status.allocatable.nvidia\.com/gpu}' 2>/dev/null || true)
if [ "$GPU" != "2" ]; then
  ./cluster/gpu-sim/patch-node.sh >/dev/null 2>&1 || true
  GPU=$("${KUBECTL[@]}" get node "$GPU_NODE" -o jsonpath='{.status.allocatable.nvidia\.com/gpu}' 2>/dev/null || true)
  [ "$GPU" = "2" ] && row "GPU pool advertises nvidia.com/gpu" PASS "2 (re-applied)" \
                   || row "GPU pool advertises nvidia.com/gpu" FAIL "got '${GPU:-<none>}'"
else
  row "GPU pool advertises nvidia.com/gpu" PASS "2"
fi

GPU_TAINT=$("${KUBECTL[@]}" get node "$GPU_NODE" -o jsonpath='{.spec.taints[?(@.key=="nvidia.com/gpu")].effect}' 2>/dev/null || true)
[ "$GPU_TAINT" = "NoSchedule" ] && row "GPU pool tainted" PASS "NoSchedule" \
                                || row "GPU pool tainted" FAIL "got '${GPU_TAINT:-<none>}'"

# --- namespaces -------------------------------------------------------------
for ns in ml-prod ml-staging monitoring; do
  if "${KUBECTL[@]}" get ns "$ns" >/dev/null 2>&1; then row "Namespace ${ns}" PASS ""
  else row "Namespace ${ns}" FAIL "missing"; fi
done

# --- workloads --------------------------------------------------------------
PROD=$(ready_count ml-prod inference-api)
[ "${PROD:-0}" -ge 3 ] && row "ml-prod/inference-api pods Ready" PASS "${PROD}/3" \
                       || row "ml-prod/inference-api pods Ready" FAIL "${PROD:-0}/3"

STG=$(ready_count ml-staging inference-api)
[ "${STG:-0}" -ge 1 ] && row "ml-staging/inference-api pods Ready" PASS "${STG}/1" \
                      || row "ml-staging/inference-api pods Ready" FAIL "${STG:-0}/1"

LOAD=$(ready_count ml-prod load-generator)
[ "${LOAD:-0}" -ge 1 ] && row "Load generator Ready" PASS "${LOAD}/1" \
                       || row "Load generator Ready" FAIL "${LOAD:-0}/1"

HPA=$("${KUBECTL[@]}" -n ml-prod get hpa inference-api -o jsonpath='{.spec.maxReplicas}' 2>/dev/null || true)
[ -n "$HPA" ] && row "HPA present in ml-prod" PASS "maxReplicas=${HPA}" \
              || row "HPA present in ml-prod" FAIL "missing"

# --- prometheus -------------------------------------------------------------
PROM=$(ready_count monitoring prometheus)
[ "${PROM:-0}" -ge 1 ] && row "Prometheus Ready" PASS "${PROM}/1" \
                       || row "Prometheus Ready" FAIL "${PROM:-0}/1"

if [ "${PROM:-0}" -ge 1 ]; then
  SERIES=$("${KUBECTL[@]}" -n monitoring exec deploy/prometheus -c prometheus -- \
    wget -qO- 'http://localhost:9090/api/v1/query?query=count(inference_requests_total)' 2>/dev/null \
    | grep -o '"value":\[[^]]*\]' | grep -o '[0-9]*"]' | tr -d '"]' || true)
  [ -n "${SERIES:-}" ] && [ "${SERIES:-0}" -gt 0 ] \
    && row "Prometheus has stub metrics" PASS "${SERIES} series" \
    || row "Prometheus has stub metrics" FAIL "no inference_requests_total yet (scrape takes ~30s)"
fi

echo
if [ "$FAILED" = 0 ]; then
  echo "${BOLD}${GREEN}ALL PASS${RESET} — cluster is at healthy baseline."
else
  echo "${BOLD}${RED}FAILURES ABOVE${RESET} — try 'make reset', or 'make clean && make cluster'."
fi
echo
exit "$FAILED"
