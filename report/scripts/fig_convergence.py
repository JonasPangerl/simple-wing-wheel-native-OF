#!/usr/bin/env python3
"""
fig_convergence.py - residual and force history plots for the report

    python3 fig_convergence.py --case <dir> --out <figures-dir>

Reads the postProcessing .dat files written during the solve. Plain
matplotlib, no ParaView. Python 3.6 compatible, like the rest of the
project's tooling.

Column names are looked up from the '# Time ...' header line, never by
position.
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

if sys.version_info < (3, 6):
    sys.exit("needs Python 3.6 or newer")

# Residual targets from system/fvSolution:residualControl
TARGETS = {"p": 1e-5, "Ux": 1e-5, "Uy": 1e-5, "Uz": 1e-5,
           "k": 1e-4, "omega": 1e-4}

COLOURS = {
    "Ux": "#1f77b4", "Uy": "#2ca8c2", "Uz": "#17becf",
    "p":  "#d62728", "k":  "#2ca02c", "omega": "#8c564b",
}

AVG_WINDOW = 50   # must match collect_results.py


def _tok(x):
    """float if the token is numeric, else the raw string.

    solverInfo.dat mixes text and numbers in one row (solver names,
    'true'/'false' convergence flags), so a row cannot be parsed as all
    floats. Doing so silently discarded every line of the residual history.
    """
    try:
        return float(x)
    except ValueError:
        return x


def read_dat(path):
    """Return (names, rows) for an OpenFOAM postProcessing .dat file."""
    names, rows = [], []
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            if line.lstrip().startswith("#"):
                cand = line.lstrip("#").split()
                if cand and cand[0] == "Time":
                    names = cand
                continue
            rows.append([_tok(t) for t in line.split()])
    return names, rows


def column(names, rows, key):
    """Numeric values of one named column; non-numeric entries dropped."""
    if key not in names:
        return None
    i = names.index(key)
    out = []
    for r in rows:
        if len(r) > i and isinstance(r[i], float):
            out.append(r[i])
    return out


def latest(base, fname):
    if not os.path.isdir(base):
        return None
    best = None
    for d in os.listdir(base):
        p = os.path.join(base, d, fname)
        if os.path.isfile(p):
            try:
                t = float(d)
            except ValueError:
                continue
            if best is None or t > best[0]:
                best = (t, p)
    return best[1] if best else None


def style(ax):
    ax.grid(True, which="major", alpha=0.30, lw=0.6)
    ax.grid(True, which="minor", alpha=0.15, lw=0.4)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def plot_residuals(case, out):
    path = latest(os.path.join(case, "postProcessing", "residuals"),
                  "solverInfo.dat")
    if path is None:
        print("  no solverInfo.dat, skipping residuals")
        return False

    names, rows = read_dat(path)
    t = column(names, rows, "Time")
    if not t:
        print("  solverInfo.dat has no data yet")
        return False

    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    plotted = 0
    for field in ("Ux", "Uy", "Uz", "p", "k", "omega"):
        y = column(names, rows, field + "_initial")
        if not y:
            continue
        ax.semilogy(t[:len(y)], y, lw=1.1, label=field,
                    color=COLOURS.get(field))
        plotted += 1

    # residualControl thresholds: 1e-5 for p and U, 1e-4 for k and omega
    ax.axhline(1e-5, color="0.35", ls="--", lw=0.9)
    ax.axhline(1e-4, color="0.55", ls=":", lw=0.9)
    ax.text(t[-1], 1.15e-5, "residualControl  p, U", ha="right", va="bottom",
            fontsize=8, color="0.3")
    ax.text(t[-1], 1.15e-4, "residualControl  k, omega", ha="right",
            va="bottom", fontsize=8, color="0.45")

    ax.set_xlabel("SIMPLE iteration")
    ax.set_ylabel("initial residual")
    ax.set_title("Residual history", loc="left", fontsize=11)
    ax.legend(ncol=3, frameon=False, fontsize=9, loc="upper right")
    style(ax)
    fig.tight_layout()
    p = os.path.join(out, "conv_residuals.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print("  wrote %s (%d fields, %d iterations)" % (p, plotted, len(t)))
    return True


def plot_forces(case, out):
    groups = [("total", "#1f3f7a"), ("wing", "#1f77b4"), ("wheel", "#2ca02c")]
    data = {}
    for g, _ in groups:
        path = latest(os.path.join(case, "postProcessing", "forceCoeffs_" + g),
                      "coefficient.dat")
        if path is None:
            continue
        names, rows = read_dat(path)
        t = column(names, rows, "Time")
        cl = column(names, rows, "Cl")
        cd = column(names, rows, "Cd")
        if t and cl and cd:
            data[g] = (t, cl, cd)

    if not data:
        print("  no coefficient.dat, skipping forces")
        return False

    fig, axes = plt.subplots(2, 1, figsize=(9.0, 6.8), sharex=True)

    for g, col in groups:
        if g not in data:
            continue
        t, cl, cd = data[g]
        axes[0].plot(t[:len(cl)], cl, lw=1.1, color=col, label=g)
        axes[1].plot(t[:len(cd)], cd, lw=1.1, color=col, label=g)

    # Mark the window collect_results.py averages over
    tmax = max(d[0][-1] for d in data.values())
    for ax in axes:
        ax.axvspan(max(0, tmax - AVG_WINDOW), tmax, color="0.85", alpha=0.6,
                   zorder=0)

    axes[0].set_ylabel(r"$C_L \cdot A$  [m$^2$]")
    axes[0].set_title("Force history.  negative lift = downforce.  "
                      "grey band = the %d iterations averaged for the result"
                      % AVG_WINDOW, loc="left", fontsize=10)
    axes[0].axhline(0.0, color="0.4", lw=0.7)
    axes[0].legend(frameon=False, fontsize=9, ncol=3)

    axes[1].set_ylabel(r"$C_D \cdot A$  [m$^2$]")
    axes[1].set_xlabel("SIMPLE iteration")
    axes[1].legend(frameon=False, fontsize=9, ncol=3)

    for ax in axes:
        style(ax)
    fig.tight_layout()
    p = os.path.join(out, "conv_forces.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print("  wrote %s (%d groups)" % (p, len(data)))
    return True


def plot_forces_zoom(case, out):
    """Last 300 iterations, to judge whether the force has actually settled."""
    path = latest(os.path.join(case, "postProcessing", "forceCoeffs_total"),
                  "coefficient.dat")
    if path is None:
        return False
    names, rows = read_dat(path)
    t = column(names, rows, "Time")
    cl = column(names, rows, "Cl")
    if not t or not cl or len(t) < 20:
        return False

    n = min(300, len(cl))
    tt, yy = t[-n:], cl[-n:]
    mean = sum(yy[-AVG_WINDOW:]) / min(AVG_WINDOW, len(yy))

    fig, ax = plt.subplots(figsize=(9.0, 4.0))
    ax.plot(tt, yy, lw=1.2, color="#1f3f7a")
    ax.axhline(mean, color="#d62728", ls="--", lw=1.0,
               label="mean of last %d = %.6f" % (AVG_WINDOW, mean))
    ax.axvspan(tt[-1] - AVG_WINDOW, tt[-1], color="0.85", alpha=0.6, zorder=0)
    ax.set_xlabel("SIMPLE iteration")
    ax.set_ylabel(r"$C_L \cdot A$  [m$^2$]  total")
    ax.set_title("Force settling, last %d iterations" % n, loc="left",
                 fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    style(ax)
    fig.tight_layout()
    p = os.path.join(out, "conv_forces_zoom.png")
    fig.savefig(p, dpi=150)
    plt.close(fig)
    print("  wrote %s" % p)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    plot_residuals(args.case, args.out)
    plot_forces(args.case, args.out)
    plot_forces_zoom(args.case, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
