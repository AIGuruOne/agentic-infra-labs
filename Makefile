# The entire attendee UX lives here. Every target is idempotent.
#
#   make doctor    pre-flight check. Run this BEFORE the session. Prints your tier.
#   make setup     installs/verifies tooling
#   make tour      what is this cluster? what are these runbooks? start here
#   make cluster   kind create + gpu-sim + prometheus + workloads; ends with verify
#   make verify    health PASS/FAIL table
#   make break-1 .. make break-7    inject a fault
#   make reset     back to a healthy baseline without a full rebuild
#   make clean     delete the cluster
#   make lab1 .. make lab4

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c

CLUSTER := agentic-infra-labs
PY      := .venv/bin/python
KUBECTL := kubectl --context kind-$(CLUSTER)

.PHONY: help doctor setup tour cluster verify reset clean load-stop test \
        break-1 break-2 break-3 break-4 break-5 break-6 break-7 \
        lab1 lab2 lab3 lab4

help:
	@sed -n '2,14p' Makefile | sed 's/^# \?//'

doctor:
	@./scripts/doctor.sh

setup:
	@./scripts/setup.sh

tour:
	@./scripts/tour.sh

cluster:
	@./scripts/cluster.sh

verify:
	@./scripts/verify.sh

reset:
	@./faults/reset.sh

clean:
	@kind delete cluster --name $(CLUSTER) 2>/dev/null || true
	@echo "cluster $(CLUSTER) deleted"

break-%:
	@./faults/break-$*.sh

load-stop:
	@$(KUBECTL) -n ml-prod scale deployment/load-generator --replicas=0
	@echo "load generator stopped. \`make reset\` brings it back."

test:
	@$(PY) -m pytest

lab1:
	@$(PY) labs/lab1-knowledge-layer/ask.py $(ARGS)

lab2:
	@$(PY) labs/lab2-live-state-agent/investigate.py $(ARGS)

lab3:
	@$(PY) labs/lab3-guardrails/remediate.py $(ARGS)

lab4:
	@$(PY) labs/lab4-evals/run_evals.py $(ARGS)
