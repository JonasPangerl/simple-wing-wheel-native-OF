#!/usr/bin/env bash
# ===========================================================================
# build.sh - regenerate the report figures and compile report.pdf
#
#   ./build.sh                      full build for the default case
#   ./build.sh --case <dir>         a different case
#   ./build.sh --no-figures         compile only, reuse existing figures
#   ./build.sh --figures-only       generate figures, do not compile
#
# Figures come from pvbatch (ParaView) and matplotlib. A figure that cannot
# be produced leaves a visible placeholder in the PDF rather than breaking
# the build, so a partial run still gives a readable report.
# ===========================================================================
set -uo pipefail
cd "${0%/*}" || exit 1

REPORT_DIR="$(pwd)"
PROJECT_ROOT="$(cd .. && pwd)"
FIG_DIR="${REPORT_DIR}/figures"
GEN_DIR="${REPORT_DIR}/generated"

CASE="${PROJECT_ROOT}/RANS_Simulations/S1.42_h0.13_AOA8_W0.63"
DO_FIGURES=1
DO_LATEX=1

while [ $# -gt 0 ]; do
    case "$1" in
        --case)         CASE="$2"; shift 2 ;;
        --no-figures)   DO_FIGURES=0; shift ;;
        --figures-only) DO_LATEX=0; shift ;;
        -h|--help)      sed -n '2,13p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
done

mkdir -p "$FIG_DIR" "$GEN_DIR"

# --- locate pvbatch --------------------------------------------------------
PVBATCH=""
if [ -f "${PROJECT_ROOT}/env/project.env" ]; then
    # shellcheck source=/dev/null
    . "${PROJECT_ROOT}/env/project.env"
fi
[ -n "${PVBATCH:-}" ] || PVBATCH="$(command -v pvbatch || true)"

step() { printf '\n=== %s ===\n' "$*"; }

if [ "$DO_FIGURES" -eq 1 ]; then

    step "Geometry figures"
    if [ -n "$PVBATCH" ] && [ -x "$PVBATCH" ]; then
        "$PVBATCH" --force-offscreen-rendering scripts/fig_geometry.py \
            --stl-dir "${PROJECT_ROOT}/Diasinos_Geometry_Generator/output" \
            --out "$FIG_DIR" || echo "  WARNING: geometry figures failed"
    else
        echo "  SKIPPED: no pvbatch (set PVBATCH in env/project.env)"
    fi

    step "Mesh figures"
    if [ -n "$PVBATCH" ] && [ -x "$PVBATCH" ] \
       && [ -f "${CASE}/processor0/constant/polyMesh/owner" ]; then
        "$PVBATCH" --force-offscreen-rendering scripts/fig_mesh.py \
            --case "$CASE" --out "$FIG_DIR" \
            || echo "  WARNING: mesh figures failed"
    else
        echo "  SKIPPED: no pvbatch, or no mesh in ${CASE}"
    fi

    step "Result figures"
    if [ -n "$PVBATCH" ] && [ -x "$PVBATCH" ] \
       && [ -d "${CASE}/postProcessing" ]; then
        "$PVBATCH" --force-offscreen-rendering scripts/fig_results.py \
            --case "$CASE" --out "$FIG_DIR" \
            || echo "  WARNING: result figures failed"
    else
        echo "  SKIPPED: no solution in ${CASE}"
    fi

    step "Convergence plots"
    python3 scripts/fig_convergence.py --case "$CASE" --out "$FIG_DIR" \
        || echo "  WARNING: convergence plots failed"
fi

step "Report data"
python3 scripts/make_tex_data.py --case "$CASE" \
    --out "${GEN_DIR}/case_data.tex" || exit 1

if [ "$DO_LATEX" -eq 1 ]; then
    step "LaTeX"
    if command -v latexmk > /dev/null 2>&1; then
        latexmk -pdf -interaction=nonstopmode -halt-on-error \
            -outdir=. report.tex > latexmk.log 2>&1
        rc=$?
    else
        pdflatex -interaction=nonstopmode -halt-on-error report.tex > latexmk.log 2>&1
        pdflatex -interaction=nonstopmode -halt-on-error report.tex >> latexmk.log 2>&1
        rc=$?
    fi

    if [ "$rc" -ne 0 ] || [ ! -f report.pdf ]; then
        echo "  FAILED - last LaTeX errors:"
        grep -A3 -E "^!|LaTeX Error" latexmk.log | head -40
        exit 1
    fi

    pages=$(pdfinfo report.pdf 2>/dev/null | awk '/^Pages/{print $2}')
    printf '\n  report.pdf written (%s pages, %s)\n' \
        "${pages:-?}" "$(du -h report.pdf | cut -f1)"
    n=$(find "$FIG_DIR" -name '*.png' 2>/dev/null | wc -l)
    printf '  %s figures in %s\n' "$n" "$FIG_DIR"
fi
