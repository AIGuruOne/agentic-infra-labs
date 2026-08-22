# Sourced by doctor.sh and setup.sh so they can never disagree about which
# interpreter the labs run on. Sets PY (command) and PYV (version) or leaves
# PY empty.
#
# 3.12 first, not "newest wins": every pinned wheel in requirements.txt has a
# prebuilt 3.12 artefact. 3.13 works and is accepted. 3.14 is excluded — the
# pinned kubernetes and mcp wheels have no 3.14 build, and a source compile on
# session morning is not a risk worth taking.
PY=""; PYV=""
for _c in python3.12 python3.13 python3.11 python3; do
  command -v "$_c" >/dev/null 2>&1 || continue
  _v=$("$_c" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || continue
  case "$_v" in 3.11|3.12|3.13) PY="$_c"; PYV="$_v"; break ;; esac
done
unset _c _v
