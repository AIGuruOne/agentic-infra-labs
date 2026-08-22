---
id: RB-002
title: GPU pods stuck Pending — insufficient resources or taint mismatch
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: embedding-trainer
model: embedding-v1
gpu_type: a10g
provider: aws
region: us-east-1
last_reviewed: 2026-05-22
---

# GPU pods stuck Pending

A GPU workload that will not schedule almost always has **more than one**
reason, and the scheduler reports all of them in a single event. Read the whole
event before acting — fixing one cause leaves the pod Pending and makes it look
like the fix did nothing.

## Symptoms

- Pod stays `Pending`, never assigned a node
- `FailedScheduling` event, e.g.
  `0/3 nodes are available: 1 Insufficient nvidia.com/gpu, 2 node(s) had untolerated taint(s)`

## Causes

There are two distinct failures, and they are commonly present together:

1. **Insufficient GPU capacity.** The pod requests more `nvidia.com/gpu` than
   any single node advertises. GPU requests are not divisible across nodes.
2. **Untolerated taint.** GPU nodes are tainted (typically
   `nvidia.com/gpu=present:NoSchedule`) so that non-GPU work does not land on
   expensive hardware. A pod without a matching toleration is refused even when
   capacity exists.

## Remediation

1. Check what the GPU nodes actually advertise:

       kubectl get nodes -o custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu

2. Check the taints on those nodes:

       kubectl get nodes -o json | jq '.items[] | {name:.metadata.name, taints:.spec.taints}'

3. Reduce the pod's GPU request to something a single node can satisfy, **and**
   add the matching toleration:

       tolerations:
         - key: "nvidia.com/gpu"
           operator: "Equal"
           value: "present"
           effect: "NoSchedule"

4. Re-check the pod. If it is still Pending, re-read the scheduler event — the
   message will now name whichever cause remains.
