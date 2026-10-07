#!/usr/bin/env python3
"""
run_campaign.py - run the enabled cases of the run matrix, locally

    python3 run_campaign.py --list                 what would run
    python3 run_campaign.py                        run them one after another
    python3 run_campaign.py --jobs 2 --np 10       two cases at a time
    python3 run_campaign.py --mesh-only
    python3 run_campaign.py --force                redo finished cases

Reads WingWheel_RunMatrix.csv, takes every row with Enable_Mesh (and
Enable_Solve) set, prepares the case if needed, and runs
./Allmesh -> ./Allsolve -> ./Allpost --summary inside it.

Resumable: a case that already carries the .stage_mesh / .stage_solve marker
is skipped unless --force is given. Interrupting with Ctrl-C or creating a
file called STOP next to this script stops the campaign after the cases that
are currently running finish.

Parallelism has two independent knobs:
  --jobs  how many CASES run at the same time
  --np    how many MPI RANKS each of those cases gets
The product must fit the machine; the script refuses to oversubscribe unless
you pass --allow-oversubscribe.

Standard library only.
"""

import argparse
import csv
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

if sys.version_info < (3, 6):
    sys.exit("run_campaign.py needs Python 3.6 or newer")

HERE = os.path.dirname(os.path.abspath(__file__))
SIMS_DIR = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(SIMS_DIR)

MATRIX = os.path.join(HERE, "WingWheel_RunMatrix.csv")
STATUS = os.path.join(HERE, "campaign_status.csv")
STOP_FILE = os.path.join(HERE, "STOP")
LOG_DIR = os.path.join(HERE, "logs")

STATUS_COLUMNS = [
    "Case_Name", "Stage", "Result", "Cells", "Layer_Coverage_pct",
    "Converged", "Iterations", "CL_A_total", "CD_A_total",
    "CL_A_wing", "CD_A_wing", "CL_A_wheel", "CD_A_wheel",
    "yPlus_wing_avg", "Runtime_min", "Finished",
]

_print_lock = threading.Lock()


def say(*parts):
    with _print_lock:
        print("[{}]".format(datetime.now().strftime("%H:%M:%S")), *parts,
              flush=True)


# ---------------------------------------------------------------------------
# matrix
# ---------------------------------------------------------------------------
def truthy(value):
    return str(value).strip().lower() in ("true", "1", "yes", "y", "x")


def read_matrix(path, want_solve):
    if not os.path.isfile(path):
        sys.exit(
            "ERROR: {} does not exist.\n"
            "       Create it with:  python3 build_matrix.py --enable-reference"
            .format(path)
        )

    selected = []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            if not truthy(row.get("Enable_Mesh")):
                continue
            if want_solve and not truthy(row.get("Enable_Solve")):
                # meshing was asked for but not solving: still a valid job
                pass
            selected.append(row)
    return selected


# ---------------------------------------------------------------------------
# one case
# ---------------------------------------------------------------------------
def case_dir(name):
    return os.path.join(SIMS_DIR, name)


def marker(name, stage):
    return os.path.join(case_dir(name), ".stage_" + stage)


def prepare(row, force, log):
    """Create the case directory if it is not there yet."""
    name = row["Case_Name"]
    target = case_dir(name)

    if os.path.isdir(target) and not force:
        return True

    cmd = [
        sys.executable, os.path.join(SIMS_DIR, "prepare_case.py"),
        "--span", row["S_c"], "--height", row["h_c"],
        "--aoa", row["AOA_deg"], "--width", row["W_c"],
        "--quiet",
    ]
    if force:
        cmd.append("--force")

    with open(log, "a") as fh:
        fh.write("\n=== prepare_case.py ===\n")
        fh.flush()
        rc = subprocess.call(cmd, stdout=fh, stderr=subprocess.STDOUT)
    return rc == 0


def run_stage(name, script, args, np, log):
    """Run one All* script inside the case directory."""
    env = dict(os.environ)
    # activate.sh lets an inherited NP win over env/project.env
    env["NP"] = str(np)

    cmd = [os.path.join(case_dir(name), script)] + list(args)

    with open(log, "a") as fh:
        fh.write("\n=== {} {} (NP={}) ===\n".format(script, " ".join(args), np))
        fh.flush()
        rc = subprocess.call(
            cmd, cwd=case_dir(name), env=env,
            stdout=fh, stderr=subprocess.STDOUT,
        )
    return rc == 0


def run_case(row, opts):
    """Prepare, mesh, solve and summarise one case. Returns a status dict."""
    name = row["Case_Name"]
    t0 = time.time()
    log = os.path.join(LOG_DIR, name + ".log")

    result = {
        "Case_Name": name, "Stage": "prepare", "Result": "running",
        "Finished": "",
    }

    with open(log, "a") as fh:
        fh.write("\n{}\n=== {} started {} ===\n".format(
            "=" * 68, name, datetime.now().isoformat(timespec="seconds")))

    # --- prepare ---------------------------------------------------------
    if not prepare(row, opts.force, log):
        result.update(Stage="prepare", Result="failed")
        say("FAILED (prepare)", name, "->", log)
        return result

    # --- mesh ------------------------------------------------------------
    if opts.stage in ("all", "mesh"):
        if os.path.isfile(marker(name, "mesh")) and not opts.force:
            say("skip mesh (done)", name)
        else:
            result["Stage"] = "mesh"
            say("meshing", name, "on", opts.np, "ranks")
            args = ["--force"] if opts.force else []
            if not run_stage(name, "Allmesh", args, opts.np, log):
                result.update(Result="failed")
                say("FAILED (mesh)", name, "->", log)
                return result

    # --- solve -----------------------------------------------------------
    if opts.stage in ("all", "solve") and truthy(row.get("Enable_Solve")):
        if os.path.isfile(marker(name, "solve")) and not opts.force:
            say("skip solve (done)", name)
        else:
            result["Stage"] = "solve"
            say("solving", name, "on", opts.np, "ranks")
            if not run_stage(name, "Allsolve", [], opts.np, log):
                result.update(Result="failed")
                say("FAILED (solve)", name, "->", log)
                return result

        result["Stage"] = "post"
        run_stage(name, "Allpost", ["--summary"], opts.np, log)

    result.update(Result="ok", Stage="done")
    result["Runtime_min"] = "{:.1f}".format((time.time() - t0) / 60.0)
    result.update(read_results(name))
    result["Finished"] = datetime.now().isoformat(timespec="seconds")

    say("done", name, "in", result["Runtime_min"], "min")
    return result


def read_results(name):
    """Pull the headline numbers out of the case's results.json."""
    import json

    path = os.path.join(case_dir(name), "results.json")
    if not os.path.isfile(path):
        return {}

    try:
        with open(path) as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return {}

    out = {}
    mesh = data.get("mesh", {})
    if "cells" in mesh:
        out["Cells"] = mesh["cells"]
    if "layer_coverage_pct" in mesh:
        out["Layer_Coverage_pct"] = mesh["layer_coverage_pct"]

    solve = data.get("solve", {})
    out["Converged"] = solve.get("converged", "")
    if "iterations" in solve:
        out["Iterations"] = solve["iterations"]

    for group in ("total", "wing", "wheel"):
        g = data.get("forces", {}).get(group, {})
        if "Cl" in g:
            out["CL_A_" + group] = "{:.6f}".format(g["Cl"]["mean"])
        if "Cd" in g:
            out["CD_A_" + group] = "{:.6f}".format(g["Cd"]["mean"])

    # Average y+ over the wing patches, as a single sanity number
    yplus = data.get("yplus", {})
    wing = [v["avg"] for k, v in yplus.items() if k.startswith("wing-")]
    if wing:
        out["yPlus_wing_avg"] = "{:.2f}".format(sum(wing) / len(wing))

    return out


# ---------------------------------------------------------------------------
# status file
# ---------------------------------------------------------------------------
def write_status(results):
    tmp = STATUS + ".tmp"
    with open(tmp, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=STATUS_COLUMNS,
                                extrasaction="ignore")
        writer.writeheader()
        for name in sorted(results):
            writer.writerow(results[name])
    os.replace(tmp, STATUS)


# ---------------------------------------------------------------------------
def check_resources(jobs, np, allow_over):
    try:
        cores = len(os.sched_getaffinity(0))
    except AttributeError:
        cores = os.cpu_count() or 1

    wanted = jobs * np
    if wanted > cores and not allow_over:
        sys.exit(
            "ERROR: --jobs {} x --np {} = {} ranks, but only {} cores are "
            "available.\n"
            "       Lower one of them, or pass --allow-oversubscribe if you "
            "really mean it\n"
            "       (MPI processes competing for cores usually run slower "
            "than running\n"
            "        the cases one after another).".format(
                jobs, np, wanted, cores)
        )
    return cores


def default_np():
    """NP from env/project.env, so the campaign agrees with a single case."""
    env_file = os.path.join(PROJECT_ROOT, "env", "project.env")
    if os.path.isfile(env_file):
        with open(env_file) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("NP=") and not line.startswith("#"):
                    value = line[3:].strip().strip('"').strip("'")
                    try:
                        return int(value)
                    except ValueError:
                        pass
    return 8


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", default=MATRIX)
    ap.add_argument("--jobs", "-j", type=int, default=1,
                    help="cases to run at the same time (default 1)")
    ap.add_argument("--np", type=int, default=None,
                    help="MPI ranks per case (default: NP from env/project.env)")
    ap.add_argument("--mesh-only", dest="stage", action="store_const",
                    const="mesh", default="all",
                    help="mesh the cases, do not solve")
    ap.add_argument("--solve-only", dest="stage", action="store_const",
                    const="solve", help="solve only, assume a mesh exists")
    ap.add_argument("--force", action="store_true",
                    help="redo cases that are already finished")
    ap.add_argument("--list", action="store_true",
                    help="print the selected cases and exit")
    ap.add_argument("--allow-oversubscribe", action="store_true")
    opts = ap.parse_args()

    if opts.np is None:
        opts.np = default_np()

    rows = read_matrix(opts.matrix, opts.stage in ("all", "solve"))

    if not rows:
        print("No cases have Enable_Mesh set in {}".format(opts.matrix))
        print("Enable the reference case with:")
        print("  python3 build_matrix.py --enable-reference")
        return 0

    if opts.list:
        print("{} case(s) selected:\n".format(len(rows)))
        print("  {:<28} {:>6} {:>6} {:>5} {:>6}  {:<16} {}".format(
            "Case_Name", "S/c", "h/c", "AOA", "W/c", "Interaction", "solve?"))
        for r in rows:
            done = "done" if os.path.isfile(marker(r["Case_Name"], "solve")) else ""
            print("  {:<28} {:>6} {:>6} {:>5} {:>6}  {:<16} {} {}".format(
                r["Case_Name"], r["S_c"], r["h_c"], r["AOA_deg"], r["W_c"],
                r["Interaction"],
                "yes" if truthy(r.get("Enable_Solve")) else "no", done))
        return 0

    cores = check_resources(opts.jobs, opts.np, opts.allow_oversubscribe)

    os.makedirs(LOG_DIR, exist_ok=True)
    if os.path.isfile(STOP_FILE):
        os.remove(STOP_FILE)

    print("=" * 68)
    print("  Campaign: {} case(s)".format(len(rows)))
    print("  {} case(s) at a time x {} ranks = {} of {} cores".format(
        opts.jobs, opts.np, opts.jobs * opts.np, cores))
    print("  stage: {}{}".format(opts.stage, "  (force)" if opts.force else ""))
    print("  logs:  {}".format(LOG_DIR))
    print("  stop early:  touch {}".format(STOP_FILE))
    print("=" * 68)

    results = {}
    t0 = time.time()
    stopped = False

    try:
        if opts.jobs == 1:
            for i, row in enumerate(rows, 1):
                if os.path.isfile(STOP_FILE):
                    say("STOP file found, stopping")
                    stopped = True
                    break
                say("--- {}/{} {}".format(i, len(rows), row["Case_Name"]))
                results[row["Case_Name"]] = run_case(row, opts)
                write_status(results)
        else:
            with ThreadPoolExecutor(max_workers=opts.jobs) as pool:
                futures = {}
                for row in rows:
                    if os.path.isfile(STOP_FILE):
                        stopped = True
                        break
                    futures[pool.submit(run_case, row, opts)] = row["Case_Name"]

                for n, fut in enumerate(as_completed(futures), 1):
                    name = futures[fut]
                    try:
                        results[name] = fut.result()
                    except Exception as exc:          # noqa: BLE001
                        results[name] = {
                            "Case_Name": name, "Stage": "?",
                            "Result": "crashed: {}".format(exc),
                        }
                        say("CRASHED", name, exc)
                    write_status(results)
                    say("({}/{} complete)".format(n, len(futures)))
    except KeyboardInterrupt:
        say("interrupted")
        stopped = True

    write_status(results)

    ok = sum(1 for r in results.values() if r.get("Result") == "ok")
    bad = len(results) - ok

    print("=" * 68)
    print("  finished {} case(s) in {:.1f} min".format(
        len(results), (time.time() - t0) / 60.0))
    print("  ok: {}   failed: {}".format(ok, bad))
    if stopped:
        print("  stopped early, {} case(s) not started".format(
            len(rows) - len(results)))
    print("  status: {}".format(STATUS))
    print("=" * 68)

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
