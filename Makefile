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

.PHONY: help doctor setup tour cluster verify reset clean load-stop test record \
        lab1 lab2 lab3 lab4

# NOTE: break-1..break-7 are deliberately NOT in .PHONY.
#
# GNU make skips implicit-rule search for any target listed in .PHONY, so
# naming them there stops the `break-%` pattern rule below from ever matching.
# `make break-1` then prints "Nothing to be done" and exits 0 — a silent no-op.
#
# That shipped. The agent was asked to investigate a cluster where nothing had
# been injected, correctly reported that nothing was wrong, and every wrapper
# around it exited 0.

help:
	@sed -n '2,14p' Makefile | sed 's/^# \?//'

doctor:
	@./scripts/doctor.sh

setup:
	@./scripts/setup.sh

tour:
	@./scripts/tour.sh

record:
	@./scripts/record.sh $(N)

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
	@printf "\033[2m  instructions: labs/lab1-knowledge-layer/LAB.md   expected output: labs/lab1-knowledge-layer/EXPECTED.md\033[0m\n"
	@$(PY) labs/lab1-knowledge-layer/ask.py $(ARGS)

lab2:
	@printf "\033[2m  instructions: labs/lab2-live-state-agent/LAB.md   expected output: labs/lab2-live-state-agent/EXPECTED.md\033[0m\n"
	@$(PY) labs/lab2-live-state-agent/investigate.py $(ARGS)

lab3:
	@printf "\033[2m  instructions: labs/lab3-guardrails/LAB.md   expected output: labs/lab3-guardrails/EXPECTED.md\033[0m\n"
	@$(PY) labs/lab3-guardrails/remediate.py $(ARGS)

lab4:
	@printf "\033[2m  instructions: labs/lab4-evals/LAB.md   expected output: labs/lab4-evals/EXPECTED.md\033[0m\n"
	@$(PY) labs/lab4-evals/run_evals.py $(ARGS)
