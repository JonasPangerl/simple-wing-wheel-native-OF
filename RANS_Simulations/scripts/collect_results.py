#!/usr/bin/env python3
"""
collect_results.py - turn one finished case directory into results.json

Reads whatever the solver and the mesher left behind and writes a single
machine-readable summary next to it. The campaign tooling consumes
results.json; humans read results.txt.

Usage (from inside a case directory, or pointing at one):
    python3 ../scripts/collect_results.py [CASE_DIR] [--window N] [--quiet]

Deliberately dependency-free: standard library only, so it runs with whatever
python3 the cluster happens to have.

Column names are looked up from the '# Time ...' header line of each .dat
file rather than hard-coded by position, so this survives OpenFOAM changing
the column order between versions.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Averaging window: steady SIMPLE runs still wobble by a fraction of a percent
# from iteration to iteration, so the reported force is a mean over the last
# N iterations rather than the single final value.
DEFAULT_WINDOW = 50


# ---------------------------------------------------------------------------
# OpenFOAM postProcessing .dat files
# ---------------------------------------------------------------------------
def read_dat(path):
    """Read an OpenFOAM postProcessing .dat file.

    Returns (column_names, rows). The column names come from the last
    commented line before the data, which OpenFOAM writes as
    '# Time <name> <name> ...'.
    """
    names = []
    rows = []

    with path.open() as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                # Keep overwriting: the last comment line is the column header
                candidate = line.lstrip("#").split()
                if candidate and candidate[0] == "Time":
                    names = candidate
                continue
            parts = line.split()
            try:
                rows.append([float(p) for p in parts])
            except ValueError:
                # A ragged or partially-written line, e.g. the run was killed
                # mid-write. Skip it rather than failing the whole collection.
                continue

    return names, rows


def latest_dat(base, filename):
    """Find <base>/<time>/<filename> for the largest numeric <time>.

    A restarted run leaves several time directories; the newest one holds the
    continuation.
    """
    if not base.is_dir():
        return None

    candidates = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        f = d / filename
        if not f.is_file():
            continue
        try:
            candidates.append((float(d.name), f))
        except ValueError:
            continue

    if not candidates:
        return None
    return max(candidates, key=lambda t: t[0])[1]


def column_stats(names, rows, column, window):
    """Mean, spread and final value of one column over the last `window` rows."""
    if not names or not rows or column not in names:
        return None

    idx = names.index(column)
    values = [r[idx] for r in rows if len(r) > idx]
    if not values:
        return None

    tail = values[-window:]
    mean = sum(tail) / len(tail)

    return {
        "mean": mean,
        "final": values[-1],
        "min": min(tail),
        "max": max(tail),
        # Peak-to-peak spread over the window, as a fraction of |mean|. This is
        # the number that says whether the "converged" value means anything.
        "spread_rel": (max(tail) - min(tail)) / abs(mean) if mean else None,
        "n_samples": len(tail),
        "n_total": len(values),
    }


def collect_forces(case, window):
    """Force coefficients for each forceCoeffs_* function object."""
    out = {}
    pp = case / "postProcessing"
    if not pp.is_dir():
        return out

    for group_dir in sorted(pp.glob("forceCoeffs_*")):
        group = group_dir.name.replace("forceCoeffs_", "")
        dat = latest_dat(group_dir, "coefficient.dat")
        if dat is None:
            continue

        names, rows = read_dat(dat)
        entry = {}
        for coeff in ("Cd", "Cl", "CmPitch"):
            stats = column_stats(names, rows, coeff, window)
            if stats is not None:
                entry[coeff] = stats

        if entry:
            entry["source"] = str(dat.relative_to(case))
            out[group] = entry

    return out


def collect_residuals(case, window):
    """Final initial-residual per solved field, from the solverInfo function."""
    base = case / "postProcessing" / "residuals"
    dat = latest_dat(base, "solverInfo.dat")
    if dat is None:
        return {}

    names, rows = read_dat(dat)
    if not rows:
        return {}

    out = {}
    for name in names:
        # solverInfo writes '<field>_initial', '<field>_final', '<field>_iters'
        if not name.endswith("_initial"):
            continue
        field = name[: -len("_initial")]
        idx = names.index(name)
        values = [r[idx] for r in rows if len(r) > idx]
        if values:
            out[field] = values[-1]

    out["iterations"] = int(rows[-1][0]) if rows[-1] else None
    return out


# ---------------------------------------------------------------------------
# Log files
# ---------------------------------------------------------------------------
def collect_mesh(case):
    """Cell count, layer coverage and checkMesh verdict."""
    out = {}

    snappy = case / "log.snappyHexMesh"
    if snappy.is_file():
        text = snappy.read_text(errors="replace")

        # Final cell count: the last 'cells:' line snappyHexMesh prints
        cells = re.findall(r"^\s*cells:\s*(\d+)", text, re.MULTILINE)
        if cells:
            out["cells"] = int(cells[-1])

        # Layer coverage, printed as 'Overall layer coverage ... xx %'
        cov = re.findall(r"[Oo]verall.*?coverage[^0-9]*([0-9.]+)\s*%", text)
        if cov:
            out["layer_coverage_pct"] = float(cov[-1])

    check = case / "log.checkMesh"
    if check.is_file():
        text = check.read_text(errors="replace")
        out["checkMesh_ok"] = "Mesh OK" in text
        failed = re.findall(r"^\s*\*\*\*(.+)$", text, re.MULTILINE)
        if failed:
            out["checkMesh_failures"] = [f.strip() for f in failed][:10]

    block = case / "log.blockMesh"
    if block.is_file():
        m = re.search(r"^\s*cells:\s*(\d+)", block.read_text(errors="replace"),
                      re.MULTILINE)
        if m:
            out["base_cells"] = int(m.group(1))

    return out


def collect_yplus(case):
    """Per-patch y+ from the last block the yPlus function object logged.

    The yPlus function object writes lines of the form
        patch <name> y+ : min = a, max = b, average = c
    once per write time. Only the last block is of interest.
    """
    log = case / "log.simpleFoam"
    if not log.is_file():
        return {}

    pattern = re.compile(
        r"patch\s+(\S+)\s+y\+\s*:\s*min\s*=\s*([-\d.eE+]+)\s*,\s*"
        r"max\s*=\s*([-\d.eE+]+)\s*,\s*average\s*=\s*([-\d.eE+]+)"
    )

    blocks = []
    current = {}
    for line in log.read_text(errors="replace").splitlines():
        m = pattern.search(line)
        if m:
            patch, ymin, ymax, yavg = m.groups()
            if patch in current:
                # A new block started
                blocks.append(current)
                current = {}
            current[patch] = {
                "min": float(ymin),
                "max": float(ymax),
                "avg": float(yavg),
            }
        elif current and line.strip().startswith("Time ="):
            blocks.append(current)
            current = {}

    if current:
        blocks.append(current)

    return blocks[-1] if blocks else {}


def collect_solve_state(case):
    """How the solve ended, and how long each stage took."""
    out = {}

    result = case / ".solve_result"
    if result.is_file():
        parts = result.read_text().split()
        if parts:
            out["status"] = parts[0]
        if len(parts) > 1:
            try:
                out["iterations"] = int(parts[1])
            except ValueError:
                pass

    log = case / "log.simpleFoam"
    if log.is_file():
        text = log.read_text(errors="replace")
        out["converged"] = "solution converged" in text
        m = re.findall(r"^ExecutionTime = ([\d.]+) s", text, re.MULTILINE)
        if m:
            out["execution_time_s"] = float(m[-1])

    for stage in ("mesh", "solve"):
        marker = case / f".stage_{stage}"
        if marker.is_file():
            out[f"{stage}_finished"] = marker.read_text().strip()

    return out


def collect_parameters(case):
    """The case-defining parameters, straight out of include/caseParameters."""
    f = case / "include" / "caseParameters"
    if not f.is_file():
        return {}

    wanted = {
        "caseName": str, "spanC": float, "heightC": float,
        "aoaDeg": float, "widthC": float,
        "wingSTL": str, "wheelSTL": str,
        "UInf": float, "rhoInf": float, "nuInf": float, "cRef": float,
    }

    out = {}
    # Strip // comments, then match 'key value;'
    text = re.sub(r"//.*$", "", f.read_text(errors="replace"), flags=re.MULTILINE)
    for key, cast in wanted.items():
        m = re.search(rf"^\s*{re.escape(key)}\s+(.+?)\s*;", text, re.MULTILINE)
        if not m:
            continue
        raw = m.group(1).strip().strip('"')
        try:
            out[key] = cast(raw)
        except ValueError:
            out[key] = raw

    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def format_text(data):
    lines = []
    p = data.get("parameters", {})

    lines.append("=" * 68)
    lines.append(f"  {data.get('case', '?')}")
    lines.append("=" * 68)

    if p:
        lines.append("")
        lines.append(
            f"  S/c {p.get('spanC', '?')}   h/c {p.get('heightC', '?')}   "
            f"AOA {p.get('aoaDeg', '?')} deg   W/c {p.get('widthC', '?')}"
        )
        lines.append(
            f"  Uinf {p.get('UInf', '?')} m/s   chord {p.get('cRef', '?')} m"
        )

    # --- mesh ---
    mesh = data.get("mesh", {})
    if mesh:
        lines.append("")
        lines.append("  Mesh")
        if "cells" in mesh:
            lines.append(f"    cells              {mesh['cells']:,}")
        if "base_cells" in mesh:
            lines.append(f"    base cells         {mesh['base_cells']:,}")
        if "layer_coverage_pct" in mesh:
            lines.append(f"    layer coverage     {mesh['layer_coverage_pct']} %")
        if "checkMesh_ok" in mesh:
            lines.append(
                f"    checkMesh          {'OK' if mesh['checkMesh_ok'] else 'FAILED'}"
            )
        for f in mesh.get("checkMesh_failures", []):
            lines.append(f"      ! {f}")

    # --- solve ---
    solve = data.get("solve", {})
    if solve:
        lines.append("")
        lines.append("  Solve")
        verdict = "converged" if solve.get("converged") else "NOT converged"
        lines.append(f"    status             {verdict}")
        if "iterations" in solve:
            lines.append(f"    iterations         {solve['iterations']}")
        if "execution_time_s" in solve:
            lines.append(
                f"    solver time        {solve['execution_time_s'] / 60:.1f} min"
            )

    # --- residuals ---
    res = data.get("residuals", {})
    fields = [(k, v) for k, v in res.items() if k != "iterations"]
    if fields:
        lines.append("")
        lines.append("  Final initial residuals")
        for k, v in fields:
            lines.append(f"    {k:<18} {v:.3e}")

    # --- forces ---
    forces = data.get("forces", {})
    if forces:
        win = data.get("window")
        lines.append("")
        lines.append(f"  Force coefficient-areas  (mean over last {win} iterations)")
        lines.append(f"    {'group':<10} {'CL.A [m2]':>14} {'CD.A [m2]':>14} {'spread':>10}")
        for group in ("wing", "wheel", "total"):
            g = forces.get(group)
            if not g:
                continue
            cl = g.get("Cl", {})
            cd = g.get("Cd", {})
            spread = cl.get("spread_rel")
            spread_s = f"{spread * 100:.2f} %" if spread is not None else "-"
            lines.append(
                f"    {group:<10} {cl.get('mean', float('nan')):>14.6f} "
                f"{cd.get('mean', float('nan')):>14.6f} {spread_s:>10}"
            )
        lines.append("")
        lines.append("    Aref = 1 m2 on purpose: these are CL*A and CD*A, to match")
        lines.append("    the Diasinos papers. See system/forceCoeffs.")

    # --- y+ ---
    yplus = data.get("yplus", {})
    if yplus:
        lines.append("")
        lines.append("  y+  (last write)")
        lines.append(f"    {'patch':<24} {'min':>8} {'avg':>8} {'max':>8}")
        for patch in sorted(yplus):
            v = yplus[patch]
            lines.append(
                f"    {patch:<24} {v['min']:>8.2f} {v['avg']:>8.2f} {v['max']:>8.2f}"
            )
        lines.append("")
        lines.append("    The layer stack targets y+ ~ 2.5. Values far above ~30 mean")
        lines.append("    the wall functions are being used outside their design range.")

    lines.append("")
    lines.append("=" * 68)
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("case", nargs="?", default=".", help="case directory")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                    help=f"iterations to average forces over (default {DEFAULT_WINDOW})")
    ap.add_argument("--quiet", action="store_true", help="write files, print nothing")
    args = ap.parse_args()

    case = Path(args.case).resolve()
    if not case.is_dir():
        print(f"ERROR: not a directory: {case}", file=sys.stderr)
        return 1

    data = {
        "case": case.name,
        "window": args.window,
        "parameters": collect_parameters(case),
        "mesh": collect_mesh(case),
        "solve": collect_solve_state(case),
        "residuals": collect_residuals(case, args.window),
        "forces": collect_forces(case, args.window),
        "yplus": collect_yplus(case),
    }

    (case / "results.json").write_text(json.dumps(data, indent=2) + "\n")

    report = format_text(data)
    (case / "results.txt").write_text(report + "\n")

    if not args.quiet:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
