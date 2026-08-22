#!/usr/bin/env bash
# Scenario 05 — autoscaling that cannot fire.
#
# Target CPU raised to 95% and min pinned equal to max. Both are individually
# defensible-looking config; together the HPA is decorative. Real CPU sits
# around 1%, so it will never reach 95%, and even if it did, min==max leaves it
# nowhere to scale. The agent should read the live HPA and say both.
. "$(dirname "$0")/lib.sh"

K -n ml-prod patch hpa inference-api --type=merge -p \
  '{"spec":{"minReplicas":3,"maxReplicas":3,"metrics":[{"type":"Resource","resource":{"name":"cpu","target":{"type":"Utilization","averageUtilization":95}}}]}}' >/dev/null

announce \
  "ml-prod HPA now targets 95% CPU with minReplicas == maxReplicas == 3" \
  "Where is autoscaling configured for this deployment, and will it actually scale?"
