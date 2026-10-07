#!/usr/bin/env bash
# ============================================================================
# run_slices.sh - cluster wrapper for slice_render.py
#
# Loads the ParaView module and runs pvbatch. MESA is used because it renders
# in software and therefore works on any batch node, with no GPU required.
#
# Examples:
#   ./run_slices.sh --case ../DUMMY_test --preview --quick
#   ./run_slices.sh --case ../DUMMY_test --report-ranges
#   ./run_slices.sh --case ../DUMMY_test --dirs x --quick
#   ./run_slices.sh --case ../DUMMY_test            # everything in slices.yaml
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Software rendering (MESA): no GPU needed, runs anywhere.
# For a GPU node, swap in paraview/EGL/org.5.13.2 instead.
PARAVIEW_MODULE="${PARAVIEW_MODULE:-paraview/MESA/org.5.13.2}"

if command -v module >/dev/null 2>&1 || [[ -n "${MODULESHOME:-}" ]]; then
  # `module` is a shell function, so it may need sourcing in a non-interactive shell.
  if ! command -v module >/dev/null 2>&1; then
    # shellcheck disable=SC1090,SC1091
    source "${MODULESHOME}/init/bash"
  fi
  echo "Loading ${PARAVIEW_MODULE}"
  module load "${PARAVIEW_MODULE}"
else
  echo "WARNING: no module system found; relying on pvbatch in PATH." >&2
fi

if ! command -v pvbatch >/dev/null 2>&1; then
  echo "ERROR: pvbatch not found after loading ${PARAVIEW_MODULE}." >&2
  echo "Available ParaView modules:" >&2
  module avail paraview 2>&1 | sed 's/^/  /' >&2 || true
  exit 1
fi

echo "pvbatch: $(command -v pvbatch)"
echo ""

# Offscreen rendering; without this pvbatch can fail on a node with no display.
exec pvbatch --force-offscreen-rendering "${SCRIPT_DIR}/slice_render.py" "$@"
