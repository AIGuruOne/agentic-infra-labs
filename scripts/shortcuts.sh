# Short names for the commands used in the session.
#
#     source scripts/shortcuts.sh
#
# Every one PRINTS THE REAL COMMAND before it runs it. That is the whole point:
# when you see `k1` on a screen share, the next line shows you exactly what it
# expanded to, so nothing is hidden behind a shortcut. Type the long form
# yourself any time — the shortcuts save keystrokes, not understanding.

_agentic_run() {
  printf '\033[2m$ %s\033[0m\n' "$1"
  eval "$1"
}

_Q='why are prod inference pods repeatedly restarting?'

# --- orientation -------------------------------------------------------------
tour() { _agentic_run "make tour"; }

# --- Lab 1: the same question, with and without the metadata filter ----------
k1() { _agentic_run "make lab1 ARGS='\"$_Q\" --environment prod --namespace ml-prod'"; }
k2() { _agentic_run "make lab1 ARGS='\"$_Q\" --no-metadata-filter'"; }

# --- Lab 2: inject a fault, then investigate it ------------------------------
s1() { _agentic_run "make reset && make break-1 && make lab2 ARGS='--scenario 1'"; }
s2() { _agentic_run "make reset && make break-2 && make lab2 ARGS='--scenario 2'"; }

# --- Segment 5 scenarios, if you are running them live -----------------------
s3() { _agentic_run "make reset && make break-3 && make lab2 ARGS='--scenario 3'"; }
s4() { _agentic_run "make reset && make break-4 && make lab2 ARGS='--scenario 4'"; }
s5() { _agentic_run "make reset && make break-5 && make lab2 ARGS='--scenario 5'"; }
s6() { _agentic_run "make reset && make break-6 && make lab2 ARGS='--scenario 6'"; }

# --- Lab 3: guardrails -------------------------------------------------------
rbac()   { _agentic_run "make lab3 ARGS='--rbac-demo'"; }
g0()     { _agentic_run "make reset && make break-7"; }
g1()     { _agentic_run "make lab3"; }
g2()     { _agentic_run "make lab3 ARGS='--allow-writes'"; }
gcheck() { _agentic_run "kubectl -n ml-prod get deploy inference-api -o jsonpath='{..image}'; echo"; }

# --- Lab 4 -------------------------------------------------------------------
ev() { _agentic_run "make lab4 ARGS='--replay'"; }

# --- housekeeping ------------------------------------------------------------
r()   { _agentic_run "make reset"; }
v()   { _agentic_run "make verify"; }
cls() { clear; printf '\033[3J'; }

printf '\033[1mshortcuts loaded\033[0m — each one prints the real command before running it\n'
printf '  \033[2mtour\033[0m         the cluster, the workloads, the runbooks\n'
printf '  \033[2mk1  k2\033[0m       Lab 1 — with the metadata filter / without\n'
printf '  \033[2ms1  s2\033[0m       Lab 2 — scenario 1 / scenario 2\n'
printf '  \033[2ms3..s6\033[0m       scenarios 3-6\n'
printf '  \033[2mrbac\033[0m         who the agent is, and what it cannot do\n'
printf '  \033[2mg0 g1 g2\033[0m     guardrails — inject / read-only / approval gate\n'
printf '  \033[2mgcheck\033[0m       which image is deployed right now\n'
printf '  \033[2mev\033[0m           the eval scorecard\n'
printf '  \033[2mr  v  cls\033[0m    reset / verify / clear screen\n'
