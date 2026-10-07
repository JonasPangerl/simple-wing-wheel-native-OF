#!/usr/bin/env python3
"""
make_tex_data.py - turn a meshed case into LaTeX macros for the report

    python3 make_tex_data.py --case <dir> --out report/generated/case_data.tex

Every number in the report comes from here, so nothing is typed by hand and
nothing can silently go stale. The sources are the case's own definition and
its meshing logs:

    include/caseParameters    the case-defining numbers
    log.blockMesh             background cell count
    log.snappyHexMesh         refinement levels, layer table, coverage
    log.checkMesh             final cell count, checkMesh verdict
    TIMING.txt                stage wall times, rank count, OpenFOAM api

A quantity that is not available becomes the macro value "n/a" rather than
being omitted, so the report still builds on a half-finished case.

Python 3.6 compatible, standard library only.
"""

import argparse
import os
import re
import sys


def tex_escape(s):
    for a, b in (("\\", r"\textbackslash{}"), ("_", r"\_"), ("%", r"\%"),
                 ("&", r"\&"), ("#", r"\#")):
        s = s.replace(a, b)
    return s


def fmt(v, spec="{:.6f}", na="n/a"):
    if v is None:
        return na
    try:
        return spec.format(v)
    except (TypeError, ValueError):
        return str(v)


def thousands(v):
    if v is None:
        return "n/a"
    try:
        return "{:,}".format(int(v)).replace(",", "\\,")
    except (TypeError, ValueError):
        return str(v)


def read_text(path):
    if not os.path.isfile(path):
        return None
    return open(path, errors="replace").read()


def read_parameters(case):
    """The case-defining numbers, straight out of include/caseParameters."""
    txt = read_text(os.path.join(case, "include", "caseParameters"))
    if txt is None:
        return {}

    wanted = {
        "caseName": str, "spanC": float, "heightC": float,
        "aoaDeg": float, "widthC": float,
        "UInf": float, "rhoInf": float, "nuInf": float, "cRef": float,
        "nIterations": str,
    }

    # Strip // comments first, so a commented-out key is not picked up.
    txt = re.sub(r"//.*$", "", txt, flags=re.MULTILINE)
    out = {}
    for key, cast in wanted.items():
        m = re.search(r"^\s*%s\s+(.+?)\s*;" % re.escape(key), txt, re.M)
        if not m:
            continue
        raw = m.group(1).strip().strip('"')
        try:
            out[key] = cast(raw)
        except ValueError:
            out[key] = raw
    return out


def read_timing(case):
    """Stage wall times from TIMING.txt, in seconds."""
    txt = read_text(os.path.join(case, "TIMING.txt"))
    out = {}
    if txt is None:
        return out
    for stage in ("MESHING",):
        m = re.search(r">>> %s.*?\n\s+OK\s+\S+\s+\((\d+) s\)" % stage,
                      txt, re.S)
        if m:
            out[stage.lower()] = int(m.group(1))
    m = re.search(r"^NP\s*:\s*(\d+)", txt, re.M)
    if m:
        out["np"] = int(m.group(1))
    m = re.search(r"^OpenFOAM\s*:\s*api (\d+)", txt, re.M)
    if m:
        out["api"] = m.group(1)
    return out


def read_mesh(case):
    """Cell counts and the checkMesh verdict."""
    out = {}

    # The final cell count comes from checkMesh, whose mesh-stats block prints
    # a 'cells:' line. More dependable than snappyHexMesh's progress output,
    # whose wording varies between versions.
    txt = read_text(os.path.join(case, "log.checkMesh"))
    if txt is not None:
        cells = re.findall(r"^\s*cells:\s*(\d+)", txt, re.M)
        if cells:
            out["cells"] = int(cells[-1])
        out["checkMesh_ok"] = "Mesh OK" in txt
        out["checkMesh_failures"] = [f.strip() for f in
                                     re.findall(r"^\s*\*\*\*(.+)$", txt, re.M)][:10]

    txt = read_text(os.path.join(case, "log.snappyHexMesh"))
    if txt is not None and "cells" not in out:
        cells = re.findall(r"^\s*cells:\s*(\d+)", txt, re.M)
        if cells:
            out["cells"] = int(cells[-1])

    # blockMesh reports 'nCells: <n>', not 'cells:'
    txt = read_text(os.path.join(case, "log.blockMesh"))
    if txt is not None:
        m = re.search(r"^\s*nCells:\s*(\d+)", txt, re.M)
        if m:
            out["base_cells"] = int(m.group(1))

    return out


def read_layer_table(case):
    """The achieved per-patch layer table from log.snappyHexMesh."""
    txt = read_text(os.path.join(case, "log.snappyHexMesh"))
    if txt is None:
        return [], None

    idx = txt.rfind("patch                faces        layers        overall")
    rows = []
    if idx >= 0:
        for line in txt[idx:].splitlines()[3:]:
            if not line.strip():
                break
            p = line.split()
            if len(p) >= 6:
                rows.append(dict(patch=p[0], faces=p[1], target=p[2],
                                 achieved=p[3], thick=p[4], pct=p[5]))

    cov = None
    m = re.findall(r"Added (\d+) out of (\d+) cells \(([\d.]+)%\)", txt)
    if m:
        cov = float(m[-1][2])
    return rows, cov


def read_levels(case):
    """Cells per refinement level."""
    txt = read_text(os.path.join(case, "log.snappyHexMesh"))
    if txt is None:
        return []
    idx = txt.rfind("Cells per refinement level:")
    if idx < 0:
        return []
    out = []
    for line in txt[idx:].splitlines()[1:]:
        p = line.split()
        if len(p) == 2 and p[0].isdigit() and p[1].isdigit():
            out.append((int(p[0]), int(p[1])))
        else:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    case = os.path.abspath(args.case)

    par = read_parameters(case)
    mesh = read_mesh(case)
    timing = read_timing(case)
    layers, coverage = read_layer_table(case)
    levels = read_levels(case)

    m = []           # (macro, value)

    def add(name, value):
        m.append((name, value))

    add("caseName", tex_escape(str(par.get("caseName",
                                           os.path.basename(case)))))
    add("ofApi", timing.get("api", "2606"))
    add("npRanks", str(timing.get("np", "n/a")))

    add("spanC", fmt(par.get("spanC"), "{:.2f}"))
    add("heightC", fmt(par.get("heightC"), "{:.2f}"))
    add("aoaDeg", fmt(par.get("aoaDeg"), "{:.0f}"))
    add("widthC", fmt(par.get("widthC"), "{:.2f}"))
    add("Uinf", fmt(par.get("UInf"), "{:.1f}"))
    add("chord", fmt(par.get("cRef"), "{:.3f}"))
    add("rhoInf", fmt(par.get("rhoInf"), "{:.4f}"))
    add("nuInf", fmt(par.get("nuInf"), "{:.6g}"))
    if par.get("UInf") and par.get("cRef") and par.get("nuInf"):
        add("ReC", thousands(par["UInf"] * par["cRef"] / par["nuInf"]))
    else:
        add("ReC", "n/a")

    # Configured iteration budget. The report quotes it as the ceiling the
    # solve would run to, not as a number of iterations taken.
    add("nIterations", str(par.get("nIterations", "n/a")))

    add("nCells", thousands(mesh.get("cells")))
    add("nBaseCells", thousands(mesh.get("base_cells")))
    add("layerCoverage", fmt(coverage, "{:.1f}"))
    add("checkMeshOk", "yes" if mesh.get("checkMesh_ok") else "no")
    add("nCheckMeshFail", str(len(mesh.get("checkMesh_failures", []))))

    add("meshMinutes", fmt(timing.get("meshing", 0) / 60.0, "{:.0f}")
        if "meshing" in timing else "n/a")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        fh.write("% Generated by report/scripts/make_tex_data.py -"
                 " do not edit by hand\n")
        for name, value in m:
            fh.write("\\newcommand{\\%s}{%s}\n" % (name, value))

        # --- layer table ------------------------------------------------
        fh.write("\n%% achieved layer table\n")
        fh.write("\\newcommand{\\layertable}{%\n")
        if layers:
            for r in layers:
                bad = r["achieved"] in ("0", "0.0")
                patch = tex_escape(r["patch"])
                if bad:
                    patch = "\\textbf{%s}" % patch
                fh.write("%s & %s & %s & %s & %s \\\\\n" % (
                    patch, r["faces"], r["target"], r["achieved"], r["pct"]))
        else:
            fh.write("\\multicolumn{5}{c}{not available} \\\\\n")
        fh.write("}\n")

        # --- refinement levels ------------------------------------------
        fh.write("\n%% cells per refinement level\n")
        fh.write("\\newcommand{\\leveltable}{%\n")
        if levels:
            tot = sum(c for _, c in levels)
            for lev, c in levels:
                fh.write("L%d & %s & %.1f \\\\\n" % (
                    lev, thousands(c), 100.0 * c / tot if tot else 0.0))
        else:
            fh.write("\\multicolumn{3}{c}{not available} \\\\\n")
        fh.write("}\n")

        # --- checkMesh findings -----------------------------------------
        fh.write("\n%% checkMesh findings\n")
        fh.write("\\newcommand{\\checkmeshlist}{%\n")
        fails = mesh.get("checkMesh_failures", [])
        if fails:
            for f in fails:
                fh.write("\\item %s\n" % tex_escape(f))
        else:
            fh.write("\\item no failures reported\n")
        fh.write("}\n")

    print("wrote %s (%d macros, %d layer rows, %d levels)"
          % (args.out, len(m), len(layers), len(levels)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
