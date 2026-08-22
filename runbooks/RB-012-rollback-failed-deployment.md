---
id: RB-012
title: Rolling back a failed inference deployment
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: inference-api
model: sentiment-v2
gpu_type: a10g
provider: aws
region: us-east-1
last_reviewed: 2026-06-11
---

# Rolling back a failed inference deployment

## Symptoms

- New pods never reach Ready after a deployment
- `ImagePullBackOff` with `manifest unknown` — the tag does not exist
- Rollout stalled with the previous ReplicaSet still serving traffic

## Cause

A deployment referenced an image tag that was never pushed, or was pushed and
later deleted. Because the rollout is stalled rather than complete, the
previous ReplicaSet is usually still serving — the service is degraded, not
down, and there is time to do this correctly.

## Remediation

Always dry-run first. A rollback is a write to production and should be shown
before it is made.

1. Identify the current and previous revisions:

       kubectl -n ml-prod rollout history deployment/inference-api

2. Show what the rollback would do, without doing it:

       kubectl -n ml-prod rollout undo deployment/inference-api --dry-run=server

3. Execute only after a human has reviewed the diff:

       kubectl -n ml-prod rollout undo deployment/inference-api

4. Watch it converge:

       kubectl -n ml-prod rollout status deployment/inference-api

5. Confirm the serving image tag is the expected known-good one, and that
   replica count matches `minReplicas`.

## Notes

Do not scale the deployment to zero to "clear" the bad ReplicaSet. That
converts a degraded service into an outage, and the stalled rollout is already
protecting you by keeping the old pods alive.
