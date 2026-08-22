---
id: RB-007
title: Inference latency spike after a deployment
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: inference-api
model: sentiment-v2
gpu_type: a10g
provider: aws
region: us-east-1
last_reviewed: 2026-06-19
---

# Inference latency spike after a deployment

## Symptoms

- p95 of `inference_request_duration_seconds` steps up sharply
- The step change lines up with a rollout, not with a traffic change
- Request rate is flat or lower than usual while latency is higher

## Cause

Most latency step-changes that coincide with a rollout are CPU throttling, not
load. A CPU limit that was adequate for the previous revision is not adequate
for the new one, and the container spends most of each 100ms CFS period
descheduled.

Latency caused by load rises with the request rate. Latency caused by
throttling does not — that is how you tell them apart.

## Remediation

1. Establish when it changed, and confirm it matches a rollout:

       histogram_quantile(0.95, sum(rate(inference_request_duration_seconds_bucket[5m])) by (le))
       kubectl -n ml-prod rollout history deployment/inference-api

2. Confirm throttling directly:

       sum(rate(container_cpu_cfs_throttled_seconds_total{namespace="ml-prod",container="inference-api"}[5m]))

   A non-zero value here means the container is being held at its limit.

3. Compare CPU usage against the limit:

       sum(rate(container_cpu_usage_seconds_total{namespace="ml-prod",container="inference-api"}[5m]))

4. Raise the CPU limit to give headroom above steady-state usage, or roll back
   the revision that changed it. Confirm p95 returns to baseline before closing.

Raising replicas instead of the limit does not fix throttling — each replica is
throttled independently.
