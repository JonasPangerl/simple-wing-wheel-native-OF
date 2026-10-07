# ===========================================================================
# caseFunctions.sh - shared helpers for the Allmesh / Allsolve / Allpost
#                    scripts inside a case directory
#
# Sourced, never executed. Assumes the current directory is a case directory.
#
# Deliberately does NOT use OpenFOAM's own bin/tools/RunFunctions: that writes
# log.<app> but does not fail the script when an application aborts, which is
# exactly the behaviour you do not want in an unattended campaign.
# ===========================================================================

# --- project environment ----------------------------------------------------
_cf_self="${BASH_SOURCE[0]}"
_cf_dir="$(cd "$(dirname "$(readlink -f "$_cf_self")")" && pwd)"

# shellcheck source=/dev/null
source "${_cf_dir}/../../env/activate.sh" || exit 1
unset _cf_self _cf_dir

CASE_DIR="$(pwd)"
CASE_NAME="$(basename "$CASE_DIR")"


# --- output -----------------------------------------------------------------
_cf_t0=$SECONDS

log() {
    printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

step() {
    printf '\n=== %s ===\n' "$*"
}

die() {
    printf '\nERROR (%s): %s\n' "$CASE_NAME" "$*" >&2
    exit 1
}

elapsed() {
    local s=$(( SECONDS - _cf_t0 ))
    printf '%dh%02dm%02ds' $(( s/3600 )) $(( (s%3600)/60 )) $(( s%60 ))
}


# --- stage markers ----------------------------------------------------------
# Plain files, so the campaign runner and a human both see the same state
# without parsing logs.
markDone()   { date '+%Y-%m-%dT%H:%M:%S' > ".stage_$1"; }
isDone()     { [ -f ".stage_$1" ]; }
clearStage() { rm -f ".stage_$1"; }


# --- running OpenFOAM applications ------------------------------------------
# Both wrappers write log.<app> in the case directory and abort on failure.
# On failure the tail of the log is printed, because in a campaign the log is
# the only thing anyone will look at.

_cf_fail() {
    local app="$1" logf="$2" rc="$3"
    printf '\n--- last 40 lines of %s ---\n' "$logf" >&2
    tail -n 40 "$logf" >&2
    die "$app exited with status $rc (full log: $CASE_DIR/$logf)"
}

# runSerial <app> [args...]
runSerial() {
    local app="$1"; shift
    local logf="log.${app}"

    command -v "$app" >/dev/null 2>&1 \
        || die "$app is not on the PATH - is this the right OpenFOAM build?"

    log "$app $*"
    if ! "$app" "$@" > "$logf" 2>&1; then
        _cf_fail "$app" "$logf" "$?"
    fi
}

# runParallel <app> [args...]   - adds -parallel and runs under mpirun
runParallel() {
    local app="$1"; shift
    local logf="log.${app}"

    command -v "$app" >/dev/null 2>&1 \
        || die "$app is not on the PATH - is this the right OpenFOAM build?"

    log "mpirun -np $NP $app $* -parallel"
    # shellcheck disable=SC2086
    if ! mpirun -np "$NP" $MPIRUN_ARGS "$app" "$@" -parallel > "$logf" 2>&1; then
        _cf_fail "$app" "$logf" "$?"
    fi
}


# --- decomposition ----------------------------------------------------------
# NP lives in env/project.env, so it has to be pushed into the dictionary
# rather than duplicated there.
syncNumberOfSubdomains() {
    local current
    current="$(foamDictionary -entry numberOfSubdomains -value \
                  system/decomposeParDict 2>/dev/null || echo '')"

    if [ "$current" != "$NP" ]; then
        log "setting numberOfSubdomains to $NP (was ${current:-unset})"
        foamDictionary -entry numberOfSubdomains -set "$NP" \
            system/decomposeParDict > /dev/null \
            || die "could not set numberOfSubdomains in system/decomposeParDict"
    fi
}

nProcDirs() {
    find . -maxdepth 1 -type d -name 'processor*' 2>/dev/null | wc -l
}

haveDecomposedMesh() {
    [ -f "processor0/constant/polyMesh/owner" ]
}


# --- initial fields ---------------------------------------------------------
# Equivalent of OpenFOAM's restore0Dir, reimplemented here because that is a
# shell function in bin/tools/RunFunctions rather than an executable, and this
# project does not source RunFunctions (see the header).
#
# Copying the undecomposed 0.orig straight into each processor directory is
# legitimate: every field has a uniform internalField, and the processor
# patches are covered by the #includeEtc "caseDicts/setConstraintTypes" line
# at the top of each boundaryField.
restoreFields0() {
    [ -d 0.orig ] || die "0.orig/ is missing - the case template is incomplete"

    local n
    n=$(nProcDirs)
    [ "$n" -gt 0 ] || die "no processor* directories - run ./Allmesh first"

    log "restoring 0/ from 0.orig/ into $n processor directories"
    local d
    for d in processor*; do
        rm -rf "${d}/0"
        cp -r 0.orig "${d}/0"
    done
}


# --- case parameters --------------------------------------------------------
# Reads one entry out of include/caseParameters.
caseParam() {
    foamDictionary -entry "$1" -value include/caseParameters 2>/dev/null
}
