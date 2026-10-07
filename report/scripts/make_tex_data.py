#!/usr/bin/env python3
"""
make_tex_data.py - turn a finished case into LaTeX macros for the report

    python3 make_tex_data.py --case <dir> --out report/generated/case_data.tex

Every number in the report comes from here, so nothing is typed by hand and
nothing can silently go stale. A quantity that is not available yet becomes
the macro value "n/a" rather than being omitted, so the report still builds.

Python 3.6 compatible, standard library only.
"""

import argparse
import json
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


def read_timing(case):
    """Stage wall times from TIMING.txt, in seconds."""
    path = os.path.join(case, "TIMING.txt")
    out = {}
    if not os.path.isfile(path):
        return out
    txt = open(path, errors="replace").read()
    for stage in ("MESHING", "SOLVING", "POSTPROCESSING"):
        m = re.search(r">>> %s.*?\n\s+OK\s+\S+\s+\((\d+) s\)" % stage,
                      txt, re.S)
        if m:
            out[stage.lower()] = int(m.group(1))
    m = re.search(r"^TOTAL\s+\S+\s+\((\d+) s\)", txt, re.M)
    if m:
        out["total"] = int(m.group(1))
    m = re.search(r"^NP\s*:\s*(\d+)", txt, re.M)
    if m:
        out["np"] = int(m.group(1))
    m = re.search(r"^OpenFOAM\s*:\s*api (\d+)", txt, re.M)
    if m:
        out["api"] = m.group(1)
    return out


def read_layer_table(case):
    """The achieved per-patch layer table from log.snappyHexMesh."""
    path = os.path.join(case, "log.snappyHexMesh")
    if not os.path.isfile(path):
        return [], None
    txt = open(path, errors="replace").read()

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
    path = os.path.join(case, "log.snappyHexMesh")
    if not os.path.isfile(path):
        return []
    txt = open(path, errors="replace").read()
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


def solver_rate(case):
    path = os.path.join(case, "log.simpleFoam")
    if not os.path.isfile(path):
        return None, None
    txt = open(path, errors="replace").read()
    its = re.findall(r"^Time = (\d+)", txt, re.M)
    ex = re.findall(r"^ExecutionTime = ([\d.]+) s", txt, re.M)
    if not its or not ex:
        return None, None
    n = int(its[-1])
    t = float(ex[-1])
    return n, (t / n if n else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    case = os.path.abspath(args.case)
    res = {}
    rj = os.path.join(case, "results.json")
    if os.path.isfile(rj):
        try:
            res = json.load(open(rj))
        except ValueError:
            res = {}

    par = res.get("parameters", {})
    mesh = res.get("mesh", {})
    solve = res.get("solve", {})
    forces = res.get("forces", {})
    yplus = res.get("yplus", {})
    resid = res.get("residuals", {})

    timing = read_timing(case)
    layers, coverage = read_layer_table(case)
    levels = read_levels(case)
    n_iter, sec_per_iter = solver_rate(case)

    m = []           # (macro, value)

    def add(name, value):
        m.append((name, value))

    add("caseName", tex_escape(str(res.get("case", os.path.basename(case)))))
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

    add("nCells", thousands(mesh.get("cells")))
    add("nBaseCells", thousands(mesh.get("base_cells")))
    add("layerCoverage", fmt(coverage, "{:.1f}"))
    add("checkMeshOk", "yes" if mesh.get("checkMesh_ok") else "no")
    add("nCheckMeshFail", str(len(mesh.get("checkMesh_failures", []))))

    add("meshMinutes", fmt(timing.get("meshing", 0) / 60.0, "{:.0f}")
        if "meshing" in timing else "n/a")
    add("solveMinutes", fmt(timing.get("solving", 0) / 60.0, "{:.0f}")
        if "solving" in timing else "n/a")
    add("postMinutes", fmt(timing.get("postprocessing", 0) / 60.0, "{:.1f}")
        if "postprocessing" in timing else "n/a")
    add("totalMinutes", fmt(timing.get("total", 0) / 60.0, "{:.0f}")
        if "total" in timing else "n/a")

    add("nIter", str(n_iter) if n_iter else "n/a")
    add("secPerIter", fmt(sec_per_iter, "{:.2f}"))
    add("converged", "yes" if solve.get("converged") else "no")

    for g in ("total", "wing", "wheel"):
        gg = forces.get(g, {})
        add("cl" + g.capitalize(),
            fmt(gg.get("Cl", {}).get("mean") if gg.get("Cl") else None))
        add("cd" + g.capitalize(),
            fmt(gg.get("Cd", {}).get("mean") if gg.get("Cd") else None))
        sp = gg.get("Cl", {}).get("spread_rel") if gg.get("Cl") else None
        add("spread" + g.capitalize(),
            fmt(sp * 100.0 if sp is not None else None, "{:.2f}"))

    for f in ("p", "Ux", "Uy", "Uz", "k", "omega"):
        add("res" + f.replace("U", "U"), fmt(resid.get(f), "{:.2e}"))

    wing_y = [v["avg"] for k, v in yplus.items() if k.startswith("wing-")]
    wheel_y = [v["avg"] for k, v in yplus.items() if k.startswith("wheel-")]
    add("yplusWing", fmt(sum(wing_y) / len(wing_y) if wing_y else None, "{:.2f}"))
    add("yplusWheel",
        fmt(sum(wheel_y) / len(wheel_y) if wheel_y else None, "{:.2f}"))
    add("yplusMax", fmt(max((v["max"] for v in yplus.values()), default=None)
                        if yplus else None, "{:.1f}"))

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
