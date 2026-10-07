#!/usr/bin/env bash
# ===========================================================================
# mesh_monitor.sh - live progress of snappyHexMesh
#
#   ./mesh_monitor.sh [log.snappyHexMesh]
#
# Run in a second shell while ./Allmesh is working. Read-only; Ctrl-C to quit.
# ===========================================================================
set -uo pipefail

LOG="${1:-log.snappyHexMesh}"
INTERVAL=3

G=$'\033[0;32m'; Y=$'\033[1;33m'; B=$'\033[0;34m'; C=$'\033[0;36m'
W=$'\033[1;37m'; R=$'\033[0;31m'; N=$'\033[0m'

# The phases snappyHexMesh works through, in order, with the string in the
# log that marks each one as started.
PHASES=(
    "Refinement:Refinement phase"
    "Shell refinement:Shell refinement iteration"
    "Surface refinement:Surface refinement iteration"
    "Removing cells:Removing mesh beyond surface intersections"
    "Snapping:Morph phase"
    "Layer addition:Layer addition phase"
    "Writing:Writing mesh"
)

while true; do
    printf '\033[2J\033[H'
    printf '%s snappyHexMesh %s %s\n' "$W" "$(basename "$(pwd)")" "$N"
    printf '%s\n' "------------------------------------------------------------"

    if [ ! -f "$LOG" ]; then
        printf '%swaiting for %s ...%s\n' "$Y" "$LOG" "$N"
        sleep "$INTERVAL"
        continue
    fi

    # --- phase checklist ---------------------------------------------------
    current=""
    for entry in "${PHASES[@]}"; do
        label="${entry%%:*}"
        needle="${entry#*:}"
        if grep -q "$needle" "$LOG" 2>/dev/null; then
            printf '  %s+%s %s\n' "$G" "$N" "$label"
            current="$label"
        else
            printf '  %so%s %s\n' "$B" "$N" "$label"
        fi
    done
    [ -n "$current" ] && printf '\n  now: %s%s%s\n' "$Y" "$current" "$N"

    # --- cell count --------------------------------------------------------
    cells=$(grep -oE 'Total number of cells = [0-9]+' "$LOG" 2>/dev/null \
            | tail -1 | grep -oE '[0-9]+$')
    [ -z "${cells:-}" ] && cells=$(grep -oE '^\s*cells:\s*[0-9]+' "$LOG" \
            2>/dev/null | tail -1 | grep -oE '[0-9]+')
    if [ -n "${cells:-}" ]; then
        printf '\n  cells:  %s%s%s  (baseline finishes near 19 M)\n' \
            "$C" "$(printf "%'d" "$cells" 2>/dev/null || echo "$cells")" "$N"
    fi

    # --- layer coverage ----------------------------------------------------
    cov=$(grep -iE 'overall.*coverage' "$LOG" 2>/dev/null | tail -1)
    [ -n "$cov" ] && printf '  layers: %s%s%s\n' "$G" "$(echo "$cov" | xargs)" "$N"

    # --- errors ------------------------------------------------------------
    if grep -qE '^--> FOAM FATAL|^\s*#[0-9]+ ' "$LOG" 2>/dev/null; then
        printf '\n  %sFATAL - snappyHexMesh aborted%s\n' "$R" "$N"
        grep -E '^--> FOAM FATAL' -A4 "$LOG" | head -8 | sed 's/^/    /'
    fi

    # --- tail --------------------------------------------------------------
    printf '\n%s\n' "------------------------------------------------------------"
    tail -n 5 "$LOG" | cut -c1-76 | sed 's/^/  /'

    printf '\n  %s  Ctrl-C to quit\n' "$(date '+%H:%M:%S')"
    sleep "$INTERVAL"
done
