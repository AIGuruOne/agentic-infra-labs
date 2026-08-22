---
id: RB-011
title: HPA configured but never scaling
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: inference-api
model: sentiment-v2
gpu_type: a10g
provider: aws
region: us-east-1
last_reviewed: 2026-05-30
---

# HPA configured but never scaling

An HPA that exists is not the same as an HPA that works. Before assuming the
autoscaler is broken, read its live spec and status — the common failures are
configuration, not the controller.

## Symptoms

- Replica count never moves regardless of load
- HPA shows a current utilisation far below its target
- HPA `TARGETS` column shows `<unknown>`

## Causes

1. **Target threshold set too high to ever be reached.** Model serving is often
   I/O bound and sits at single-digit CPU. A 95% CPU target will never fire.
   Thresholds above 80% are almost always a copy-paste from a batch workload.
2. **`minReplicas` equal to `maxReplicas`.** The HPA has nowhere to scale. This
   is sometimes set deliberately during an incident freeze and then never
   reverted.
3. **No metrics source.** `<unknown>` in the TARGETS column means
   metrics-server is absent or not scraping; the HPA cannot act without a
   current value.
4. **No CPU requests on the container.** Utilisation is a percentage *of the
   request*. With no request there is no denominator.

## Remediation

1. Read the live object, not the manifest in git:

       kubectl -n ml-prod get hpa inference-api -o yaml
       kubectl -n ml-prod describe hpa inference-api

2. Check `minReplicas`, `maxReplicas`, and the target utilisation together.
   Any of the four causes above is sufficient on its own.
3. For this service, a 60-70% CPU target with `minReplicas: 3` and
   `maxReplicas: 10` is the reviewed baseline. The 70% figure was chosen to
   leave headroom for the ~30s pod start time; a higher target means the new
   replicas arrive after the latency spike has already been served.
