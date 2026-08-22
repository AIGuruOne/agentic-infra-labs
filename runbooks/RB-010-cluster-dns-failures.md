---
id: RB-010
title: Intermittent DNS resolution failures inside the cluster
environment: prod
cluster: ml-cluster-1
namespace: kube-system
service: coredns
model: null
gpu_type: null
provider: aws
region: us-east-1
last_reviewed: 2026-04-02
---

# Intermittent DNS resolution failures inside the cluster

## Symptoms

- Sporadic `Name or service not known` from application pods
- Requests to in-cluster Services fail some of the time and succeed on retry
- CoreDNS pods showing elevated latency or restarts

## Cause

Usually CoreDNS pod pressure or an `ndots` interaction causing excessive
lookups for external names. Less commonly, conntrack table exhaustion on nodes.

## Remediation

1. Check CoreDNS replica health and resource usage.
2. Set `dnsConfig.options.ndots: 2` on chatty workloads, or fully qualify
   external hostnames with a trailing dot.
3. Scale CoreDNS with cluster size; the default replica count does not scale
   automatically.
