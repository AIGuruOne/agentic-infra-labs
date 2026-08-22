#!/usr/bin/env bash
# cluster.sh — kind create + gpu-sim + workloads + prometheus, ending in verify.
#
# Idempotent: if the cluster already exists it is reused, and every apply is
# declarative. Target is under 5 minutes from clean on the reference Mac.
#
# The inference stub is BUILT here and side-loaded with `kind load`, never
# pulled from a registry. That one decision is why this repo works identically
# on Apple Silicon, x86 Linux, and WSL2 without an attendee ever thinking about
# CPU architecture.

set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER="agentic-infra-labs"
KUBECTL=(kubectl --context "kind-${CLUSTER}")
IMAGE="inference-stub"

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
say() { printf "${BOLD}==>${RESET} %s\n" "$1"; }

START=$(date +%s)

# --- cluster ----------------------------------------------------------------
if kind get clusters 2>/dev/null | grep -qx "$CLUSTER"; then
  say "cluster '${CLUSTER}' already exists — reusing"
else
  say "creating kind cluster '${CLUSTER}' (1 control-plane + 2 workers)"
  kind create cluster --config cluster/kind-config.yaml --wait 120s
fi

say "waiting for nodes"
"${KUBECTL[@]}" wait --for=condition=Ready nodes --all --timeout=180s >/dev/null

# --- gpu simulation ---------------------------------------------------------
say "simulating GPU pool"
./cluster/gpu-sim/patch-node.sh

# --- image ------------------------------------------------------------------
say "building inference stub image (locally — never pulled)"
docker build -q -t "${IMAGE}:v2" workloads/inference-stub >/dev/null
# staging deliberately runs an older tag. That drift IS scenario 06, so it is
# seeded here rather than injected by a break script.
docker tag "${IMAGE}:v2" "${IMAGE}:v1"

say "loading image into cluster nodes"
kind load docker-image "${IMAGE}:v2" "${IMAGE}:v1" --name "$CLUSTER" 2>&1 | grep -v '^Image:' || true

# --- workloads --------------------------------------------------------------
say "applying namespaces and workloads"
"${KUBECTL[@]}" apply -f workloads/manifests/ >/dev/null

# --- observability ----------------------------------------------------------
say "applying Prometheus"
"${KUBECTL[@]}" apply -f observability/prometheus.yaml >/dev/null

# metrics-server: without it every HPA reads <unknown>/70% and scenario 05 has
# nothing live to inspect. ~70 MB — cheap relative to what it makes possible.
say "applying metrics-server"
"${KUBECTL[@]}" apply -f observability/metrics-server.yaml >/dev/null

# --- rbac -------------------------------------------------------------------
say "applying scoped agent ServiceAccount"
"${KUBECTL[@]}" apply -f cluster/rbac/ >/dev/null
./scripts/make-agent-kubeconfig.sh >/dev/null

# --- settle -----------------------------------------------------------------
say "waiting for workloads to become Ready"
"${KUBECTL[@]}" -n ml-prod    rollout status deploy/inference-api  --timeout=180s >/dev/null
"${KUBECTL[@]}" -n ml-staging rollout status deploy/inference-api  --timeout=180s >/dev/null
"${KUBECTL[@]}" -n ml-prod    rollout status deploy/load-generator --timeout=120s >/dev/null
"${KUBECTL[@]}" -n monitoring rollout status deploy/prometheus     --timeout=180s >/dev/null
"${KUBECTL[@]}" -n kube-system rollout status deploy/metrics-server --timeout=180s >/dev/null

say "letting Prometheus complete a scrape cycle"
sleep 20

ELAPSED=$(( $(date +%s) - START ))
printf "\n${DIM}cluster ready in %dm%02ds${RESET}\n" $((ELAPSED/60)) $((ELAPSED%60))

./scripts/verify.sh
