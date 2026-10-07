# ===========================================================================
# activate.sh - put OpenFOAM on the PATH and export the project settings
#
# Must be SOURCED, not executed:
#   source env/activate.sh
#
# Every script in this project sources this file, so it is the single place
# where the OpenFOAM environment is set up. It is deliberately quiet unless
# something is wrong.
#
# Exports: FOAM_* / WM_* (from OpenFOAM), NP, MPIRUN_ARGS, PVBATCH,
#          PROJECT_ROOT, OF_API
# ===========================================================================

# --- locate the project root, regardless of where we were sourced from -----
if [ -n "${BASH_SOURCE[0]:-}" ]; then
    _act_self="${BASH_SOURCE[0]}"
else
    echo "activate.sh: needs bash (BASH_SOURCE is unset)" >&2
    return 1 2>/dev/null || exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "$(readlink -f "$_act_self")")/.." && pwd)"
export PROJECT_ROOT
unset _act_self

_env_file="${PROJECT_ROOT}/env/project.env"

if [ ! -f "$_env_file" ]; then
    cat >&2 <<EOF

ERROR: ${_env_file} does not exist.

Create it from the template and set OPENFOAM_BASHRC:

    cp env/project.env.example env/project.env
    \${EDITOR:-vi} env/project.env

See docs/01_setup.md for the full walkthrough.

EOF
    unset _env_file
    return 1 2>/dev/null || exit 1
fi

# An NP already present in the environment wins over the one in project.env.
# This is what lets the campaign runner give each concurrently running case a
# slice of the machine without rewriting the config file.
_np_override="${NP:-}"

# shellcheck source=/dev/null
. "$_env_file"
unset _env_file

if [ -n "$_np_override" ]; then
    NP="$_np_override"
fi
unset _np_override

# --- defaults for anything the user left blank ------------------------------
: "${NP:=8}"
: "${MPIRUN_ARGS:=}"
: "${PVBATCH:=}"
: "${MODULES_TO_LOAD:=}"
export NP MPIRUN_ARGS PVBATCH

# --- optional environment modules ------------------------------------------
if [ -n "$MODULES_TO_LOAD" ]; then
    if ! command -v module >/dev/null 2>&1; then
        for _init in /usr/share/Modules/init/bash /etc/profile.d/modules.sh \
                     /usr/share/lmod/lmod/init/bash; do
            [ -f "$_init" ] && . "$_init" && break
        done
        unset _init
    fi

    if command -v module >/dev/null 2>&1; then
        for _m in $MODULES_TO_LOAD; do
            module load "$_m" 2>/dev/null \
                || echo "activate.sh: warning: could not load module '$_m'" >&2
        done
        unset _m
    else
        echo "activate.sh: warning: MODULES_TO_LOAD is set but 'module' is unavailable" >&2
    fi
fi

# --- OpenFOAM ---------------------------------------------------------------
if [ -z "${OPENFOAM_BASHRC:-}" ]; then
    echo "ERROR: OPENFOAM_BASHRC is empty in env/project.env" >&2
    echo "       Set it to the etc/bashrc of your OpenFOAM installation." >&2
    return 1 2>/dev/null || exit 1
fi

if [ ! -f "$OPENFOAM_BASHRC" ]; then
    echo "ERROR: OPENFOAM_BASHRC does not point at a file:" >&2
    echo "       $OPENFOAM_BASHRC" >&2
    return 1 2>/dev/null || exit 1
fi

# OpenFOAM's bashrc trips over 'set -u' and over an inherited errexit
case "$-" in *u*) _had_u=1; set +u ;; *) _had_u=0 ;; esac
case "$-" in *e*) _had_e=1; set +e ;; *) _had_e=0 ;; esac

# shellcheck source=/dev/null
. "$OPENFOAM_BASHRC"

[ "$_had_u" = 1 ] && set -u
[ "$_had_e" = 1 ] && set -e
unset _had_u _had_e

if ! command -v simpleFoam >/dev/null 2>&1; then
    echo "ERROR: sourced $OPENFOAM_BASHRC but simpleFoam is not on the PATH." >&2
    echo "       The installation looks incomplete or not built." >&2
    return 1 2>/dev/null || exit 1
fi

# --- version gate -----------------------------------------------------------
# $FOAM_API is set by v2112 and newer. Fall back to the META-INFO file.
OF_API="${FOAM_API:-}"
if [ -z "$OF_API" ] && [ -f "${WM_PROJECT_DIR:-}/META-INFO/api-info" ]; then
    OF_API="$(sed -n 's/^api=//p' "${WM_PROJECT_DIR}/META-INFO/api-info")"
fi
export OF_API

if [ -z "$OF_API" ]; then
    echo "activate.sh: warning: could not determine the OpenFOAM api version." >&2
    echo "             Expected 2606. Continuing anyway." >&2
elif [ "$OF_API" -lt 2306 ] 2>/dev/null; then
    echo "ERROR: OpenFOAM api $OF_API is too old for this project (need >= 2306)." >&2
    echo "       The case dictionaries use the <case>/ include syntax and" >&2
    echo "       function objects that older versions do not have." >&2
    return 1 2>/dev/null || exit 1
elif [ "$OF_API" != "2606" ]; then
    echo "activate.sh: note: running against OpenFOAM api $OF_API, this project" >&2
    echo "             was set up and verified on 2606." >&2
fi
