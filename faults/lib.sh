# Shared by every break script and by reset.sh.
#
# Contract: a break script prints exactly two lines — what was injected, and
# the question to ask the agent. Nothing else reaches the terminal, because on
# a screen share every extra line is a line the audience has to decide to
# ignore.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[1]}")/.."

CLUSTER="agentic-infra-labs"
KUBECTL=(kubectl --context "kind-${CLUSTER}")
K() { "${KUBECTL[@]}" "$@"; }

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'

# wait_for <seconds> <description> <shell test>
#
# A break script must not return until what it injected is actually observable.
# Without this, `make break-1 && make lab2` is a race: the agent calls list_pods
# before the rollout has produced a failing pod, correctly reports that nothing
# is wrong, and it looks exactly like the demo is broken. It passes when you
# rehearse and fails on stage.
#
# Prints nothing unless it has to wait more than a moment, so the two-line
# output contract still holds for the fast faults.
wait_for() {
  local timeout="$1" what="$2" test_cmd="$3" waited=0 announced=0
  while [ "$waited" -lt "$timeout" ]; do
    if eval "$test_cmd" >/dev/null 2>&1; then
      [ "$announced" = 1 ] && printf "\r%*s\r" 60 ""
      return 0
    fi
    if [ "$waited" -ge 4 ] && [ "$announced" = 0 ]; then
      printf "${DIM}waiting for %s…${RESET}" "$what" >&2
      announced=1
    fi
    [ "$announced" = 1 ] && printf "." >&2
    sleep 2
    waited=$(( waited + 2 ))
  done
  [ "$announced" = 1 ] && printf "\n" >&2
  printf "${BOLD}warning:${RESET} %s did not appear within %ss — the agent may not see it yet\n" \
    "$what" "$timeout" >&2
  return 1
}

announce() { # announce <what was injected> <question to ask>
  printf "\n${BOLD}injected:${RESET} %s\n" "$1"
  printf "${BOLD}ask:${RESET}      ${DIM}%s${RESET}\n\n" "$2"
}
