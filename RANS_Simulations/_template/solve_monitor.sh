#!/usr/bin/env bash
# ===========================================================================
# solve_monitor.sh - live residuals and forces during simpleFoam
#
#   ./solve_monitor.sh [log.simpleFoam]
#
# Run in a second shell while ./Allsolve is working. Read-only; Ctrl-C to quit.
# ===========================================================================
set -uo pipefail

LOG="${1:-log.simpleFoam}"
INTERVAL=4

G=$'\033[0;32m'; Y=$'\033[1;33m'; C=$'\033[0;36m'
W=$'\033[1;37m'; R=$'\033[0;31m'; N=$'\033[0m'

FORCES="postProcessing/forceCoeffs_total/0/coefficient.dat"

# Pull the value of one named column out of an OpenFOAM .dat file.
# Finds the column by name in the '# Time ...' header, never by position.
dat_col() {
    local file="$1" name="$2" rows="${3:-1}"
    [ -f "$file" ] || return 1
    awk -v want="$name" -v nrows="$rows" '
        /^#/ {
            sub(/^#[ \t]*/, "")
            if ($1 == "Time") { for (i = 1; i <= NF; i++) if ($i == want) col = i }
            next
        }
        NF && col { buf[NR] = $col; last = NR }
        END { if (col && last) print buf[last] }
    ' "$file"
}

while true; do
    printf '\033[2J\033[H'
    printf '%s simpleFoam %s %s\n' "$W" "$(basename "$(pwd)")" "$N"
    printf '%s\n' "----------------------------------------------------------------"

    if [ ! -f "$LOG" ]; then
        printf '%swaiting for %s ...%s\n' "$Y" "$LOG" "$N"
        sleep "$INTERVAL"
        continue
    fi

    # --- iteration ---------------------------------------------------------
    iter=$(grep -oE '^Time = [0-9]+' "$LOG" | tail -1 | awk '{print $3}')
    end=$(foamDictionary -entry endTime -value system/controlDict 2>/dev/null)
    printf '  iteration: %s%s%s' "$C" "${iter:-0}" "$N"
    [ -n "${end:-}" ] && printf ' / %s' "$end"
    printf '\n'

    exec_t=$(grep -oE 'ExecutionTime = [0-9.]+' "$LOG" | tail -1 | awk '{print $3}')
    if [ -n "${exec_t:-}" ] && [ -n "${iter:-}" ] && [ "${iter:-0}" -gt 0 ]; then
        per=$(awk -v t="$exec_t" -v i="$iter" 'BEGIN{printf "%.2f", t/i}')
        printf '  elapsed:   %.0f s   (%s s / iteration)\n' "$exec_t" "$per"
        if [ -n "${end:-}" ]; then
            left=$(awk -v e="$end" -v i="$iter" -v p="$per" \
                   'BEGIN{printf "%.0f", (e-i)*p/60}')
            printf '  remaining: ~%s min at this rate (residualControl may stop sooner)\n' "$left"
        fi
    fi

    # --- residuals ---------------------------------------------------------
    printf '\n  %sinitial residuals%s\n' "$W" "$N"
    for f in Ux Uy Uz p k omega; do
        v=$(grep -oE "Solving for $f, Initial residual = [0-9.e+-]+" "$LOG" \
            | tail -1 | grep -oE '[0-9.e+-]+$')
        [ -n "${v:-}" ] && printf '    %-7s %s\n' "$f" "$v"
    done

    if grep -q 'solution converged' "$LOG"; then
        printf '\n  %sCONVERGED - residualControl satisfied%s\n' "$G" "$N"
    fi

    # --- forces ------------------------------------------------------------
    if [ -f "$FORCES" ]; then
        cl=$(dat_col "$FORCES" Cl)
        cd_=$(dat_col "$FORCES" Cd)
        printf '\n  %sforces, total (coefficient-areas, m2)%s\n' "$W" "$N"
        [ -n "${cl:-}" ] && printf '    CL.A    %s   (negative = downforce)\n' "$cl"
        [ -n "${cd_:-}" ] && printf '    CD.A    %s\n' "$cd_"
    fi

    # --- failure -----------------------------------------------------------
    if grep -qE '^--> FOAM FATAL' "$LOG"; then
        printf '\n  %sFATAL - solver aborted%s\n' "$R" "$N"
        grep -E '^--> FOAM FATAL' -A4 "$LOG" | head -8 | sed 's/^/    /'
    fi

    printf '\n  %s  Ctrl-C to quit\n' "$(date '+%H:%M:%S')"
    sleep "$INTERVAL"
done
