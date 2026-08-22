#!/usr/bin/env bash
# patch-node.sh — advertise a fake nvidia.com/gpu extended resource on the GPU
# node. No device plugin, no NVIDIA container runtime, no GPU hardware.
#
# Extended resources can only be set via the node *status* subresource, and
# kubectl has no verb for it, so this opens a short-lived `kubectl proxy` and
# PATCHes /api/v1/nodes/<node>/status directly.
#
# Idempotent. Called by `make cluster` and `make reset`, and re-applied by
# verify.sh whenever the resource has gone missing — node status patches do not
# survive a kubelet restart, and a laptop that slept overnight will have lost
# them. verify.sh repairing this instead of failing on it is deliberate.

set -euo pipefail

GPU_NODE="${GPU_NODE:-agentic-infra-labs-worker2}"
GPU_COUNT="${GPU_COUNT:-2}"
PROXY_PORT="${PROXY_PORT:-8001}"

current=$(kubectl get node "$GPU_NODE" -o jsonpath='{.status.capacity.nvidia\.com/gpu}' 2>/dev/null || true)
if [ "$current" = "$GPU_COUNT" ]; then
  echo "gpu-sim: ${GPU_NODE} already advertises nvidia.com/gpu=${GPU_COUNT}"
  exit 0
fi

kubectl proxy --port="$PROXY_PORT" >/dev/null 2>&1 &
PROXY_PID=$!
trap 'kill "$PROXY_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 40); do
  curl -sf "http://127.0.0.1:${PROXY_PORT}/api" >/dev/null 2>&1 && break
  sleep 0.25
done

curl -sf -X PATCH \
  -H "Content-Type: application/json-patch+json" \
  --data '[{"op":"add","path":"/status/capacity/nvidia.com~1gpu","value":"'"${GPU_COUNT}"'"}]' \
  "http://127.0.0.1:${PROXY_PORT}/api/v1/nodes/${GPU_NODE}/status" >/dev/null

# Confirm rather than trust: the PATCH can return 200 and still be reconciled
# away if the node object was mid-update.
for _ in $(seq 1 20); do
  got=$(kubectl get node "$GPU_NODE" -o jsonpath='{.status.allocatable.nvidia\.com/gpu}' 2>/dev/null || true)
  [ "$got" = "$GPU_COUNT" ] && { echo "gpu-sim: ${GPU_NODE} now advertises nvidia.com/gpu=${GPU_COUNT}"; exit 0; }
  sleep 0.5
done

echo "gpu-sim: FAILED to set nvidia.com/gpu on ${GPU_NODE}" >&2
exit 1
