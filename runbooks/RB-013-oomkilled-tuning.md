---
id: RB-013
title: Model server OOMKilled under batch load
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: inference-api
model: sentiment-v2
gpu_type: a10g
provider: aws
region: us-east-1
last_reviewed: 2026-02-28
---

# Model server OOMKilled under batch load

## Symptoms

- Pods restarting with `OOMKilled` in the last state
- Restarts correlate with batch traffic, not with deployments
- Memory usage sawtooths up to the limit and drops

## Cause

Batch requests are held in memory for the duration of the batch. A memory limit
sized for single-request serving is exceeded when batching is enabled.

## Remediation

1. Confirm the termination reason:

       kubectl -n ml-prod get pod <pod> -o jsonpath='{.status.containerStatuses[0].lastState}'

2. Compare peak memory to the configured limit before changing anything —
   OOMKilled with headroom to spare means a leak, not an undersized limit.
3. Raise the memory limit, or cap the batch size at the application level.
   Prefer capping the batch: an unbounded batch size means no limit is ever
   large enough.
