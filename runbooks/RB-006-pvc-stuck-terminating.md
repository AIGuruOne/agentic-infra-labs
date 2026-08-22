---
id: RB-006
title: PersistentVolumeClaim stuck Terminating
environment: prod
cluster: ml-cluster-1
namespace: ml-prod
service: null
model: null
gpu_type: null
provider: aws
region: us-east-1
last_reviewed: 2026-01-27
---

# PersistentVolumeClaim stuck Terminating

## Symptoms

- PVC remains in `Terminating` indefinitely after deletion
- A new PVC of the same name cannot be created

## Cause

The `kubernetes.io/pvc-protection` finalizer is held while any pod still
references the claim, including pods that are themselves stuck terminating.

## Remediation

1. Find the referencing pods:

       kubectl -n ml-prod get pods -o json | jq '.items[] | select(.spec.volumes[]?.persistentVolumeClaim.claimName=="<pvc>") | .metadata.name'

2. Remove those pods first. The PVC will finish deleting on its own.
3. Only if no pod references it and it is still stuck, remove the finalizer —
   and record why, because a manually removed finalizer can orphan the
   underlying volume.
