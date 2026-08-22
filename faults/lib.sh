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

announce() { # announce <what was injected> <question to ask>
  printf "\n${BOLD}injected:${RESET} %s\n" "$1"
  printf "${BOLD}ask:${RESET}      ${DIM}%s${RESET}\n\n" "$2"
}
