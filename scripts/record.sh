#!/usr/bin/env bash
# record.sh — set up one take, cleanly, so nothing you don't want is on camera.
#
#     ./scripts/record.sh 3        scenario 03
#     ./scripts/record.sh lab1     the Lab 1 contrast
#
# It resets the cluster, injects the fault, waits however long that fault needs
# to become visible, clears the screen, and then STOPS. You start your recorder,
# press Enter, and the only thing on the clip is the command and its output.
#
# The waiting is the part worth automating. break-4 is invisible for 60 seconds
# — record it too early and the agent correctly reports that nothing is wrong,
# which looks exactly like your demo failing.

set -uo pipefail
cd "$(dirname "$0")/.."

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
GREEN=$'\033[32m'; YELLOW=$'\033[33m'

TARGET="${1:-}"
[ -n "$TARGET" ] || { echo "usage: $0 <1-7|lab1>"; exit 1; }

Q='why are prod inference pods repeatedly restarting?'

prep() {
  printf "${DIM}resetting…${RESET}\n"
  ./faults/reset.sh >/dev/null 2>&1
}

ready() {  # ready <what you will type> <what to say it is>
  clear; printf '\e[3J'
  printf "\n${GREEN}${BOLD}READY TO RECORD${RESET}  ${DIM}%s${RESET}\n\n" "$2"
  printf "  1. start your recorder\n"
  printf "  2. press Enter here\n"
  printf "  3. the take runs — stop recording when the answer finishes\n\n"
  printf "${DIM}  (the command about to run: %s)${RESET}\n\n" "$1"
  read -r _ </dev/tty
  clear; printf '\e[3J'
}

case "$TARGET" in
  lab1)
    prep
    ready "make lab1 (twice)" "Lab 1 contrast — INSURANCE for the most important 90s"
    make lab1 ARGS="\"$Q\" --environment prod --namespace ml-prod"
    printf "\n${DIM}--- now the same question, metadata-blind ---${RESET}\n\n"
    sleep 2
    make lab1 ARGS="\"$Q\" --no-metadata-filter"
    ;;
  4)
    prep
    printf "${DIM}injecting break-4…${RESET}\n"
    ./faults/break-4.sh >/dev/null
    printf "${YELLOW}waiting 90s — break-4 is INVISIBLE before 60s.${RESET}\n"
    printf "${DIM}p95 is still 24ms at T+30s. Do not shorten this.${RESET}\n"
    for i in $(seq 90 -5 5); do printf "\r  %ds " "$i"; sleep 5; done
    printf "\r        \r"
    ready "make lab2 ARGS='--scenario 4'" "scenario 04 — latency + throttling"
    make lab2 ARGS="--scenario 4"
    ;;
  [1-7])
    prep
    printf "${DIM}injecting break-%s…${RESET}\n" "$TARGET"
    "./faults/break-${TARGET}.sh" >/dev/null
    sleep 8
    ready "make lab2 ARGS='--scenario $TARGET'" "scenario 0${TARGET}"
    make lab2 ARGS="--scenario $TARGET"
    ;;
  *) echo "usage: $0 <1-7|lab1>"; exit 1 ;;
esac

printf "\n${GREEN}take complete — stop recording.${RESET}\n"
printf "${DIM}next take: ./scripts/record.sh <n>   (it resets for you)${RESET}\n\n"
