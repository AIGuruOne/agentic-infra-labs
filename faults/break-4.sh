#!/usr/bin/env bash
# Scenario 04 — latency spike.
#
# One rollout, two things at once: the stub starts burning 250ms of real CPU
# per request, and the CPU limit is tightened to 50m. Neither alone tells the
# story. Prometheus says p95 jumped; the rollout timestamp says when; the
# container_cpu_cfs_throttled metric says the pods are being held at the limit
# for most of every scheduling period.
#
# The burn is deliberately CPU-bound rather than a sleep. A sleeping process is
# never throttled by a CPU limit, so a sleep-based "latency spike" would leave
# the agent hunting for throttling evidence that does not exist — a demo that
# lies about its own mechanism.
. "$(dirname "$0")/lib.sh"

K -n ml-prod set env deployment/inference-api CPU_BURN_MS=250 LATENCY_MS=0 >/dev/null
K -n ml-prod patch deployment inference-api --type=json -p \
  '[{"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/cpu","value":"50m"},
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/cpu","value":"50m"}]' >/dev/null

announce \
  "ml-prod/inference-api now burns 250ms CPU per request with its CPU limit cut to 50m, in one rollout" \
  "What should I check now that model latency in ml-prod has suddenly increased?"
