#!/usr/bin/env bash
# reset.sh — back to a healthy baseline from ANY combination of breaks, without
# rebuilding the cluster.
#
# The strategy is deliberately dumb: re-apply the manifests declaratively and
# delete the two objects the breaks create. Because every fault is injected by
# changing a field that the manifests fully specify, `kubectl apply` puts each
# one back — env vars, image tag, CPU limit, HPA target — with no per-fault
# undo logic to keep in sync. Adding break-8 later means writing break-8.sh and
# nothing else, as long as it follows the same rule.
. "$(dirname "$0")/lib.sh"

BOLD=$'\033[1m'; RESET_C=$'\033[0m'; DIM=$'\033[2m'
printf "${BOLD}==>${RESET_C} restoring baseline\n"

# Events outlive the fault that caused them by about an hour. An agent asked
# to investigate a fresh incident will happily read "Back-off pulling image
# v3-broken" left over from the previous break and diagnose the wrong thing.
# Clearing them is the difference between a reset and a reset that holds up on
# camera.
K -n ml-prod    delete events --all >/dev/null 2>&1 || true
K -n ml-staging delete events --all >/dev/null 2>&1 || true

# Objects that exist only because a break created them.
K -n ml-prod    delete deployment embedding-trainer  --ignore-not-found >/dev/null
K -n ml-staging delete service    inference-api-prod --ignore-not-found >/dev/null

# Everything else is a field the manifests own.
K apply -f workloads/manifests/ >/dev/null
K apply -f observability/prometheus.yaml >/dev/null
K apply -f cluster/rbac/ >/dev/null

# Node status patches do not survive a kubelet restart; re-assert.
./cluster/gpu-sim/patch-node.sh >/dev/null

# The ServiceAccount token is stable, but regenerating is cheap and means a
# reset always leaves a usable agent kubeconfig.
./scripts/make-agent-kubeconfig.sh >/dev/null

printf "${DIM}    waiting for rollouts${RESET_C}\n"
K -n ml-prod    rollout status deploy/inference-api  --timeout=180s >/dev/null
K -n ml-staging rollout status deploy/inference-api  --timeout=180s >/dev/null
K -n ml-prod    rollout status deploy/load-generator --timeout=120s >/dev/null

# Prometheus needs a scrape cycle before the metrics rows in verify can pass.
sleep 15

exec ./scripts/verify.sh
