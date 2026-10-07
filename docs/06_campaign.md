# 6. Campaign — running many cases

420 combinations exist. You choose which ones run, and whether they run one
after another or several at a time. Everything is local; there is no job
scheduler involved.

```bash
cd RANS_Simulations/campaign

python3 build_matrix.py --enable-reference   # choose what runs
python3 run_campaign.py --list               # check the choice
python3 run_campaign.py                      # run, one case at a time
```

---

## 6.1 The run matrix

`build_matrix.py` writes `WingWheel_RunMatrix.csv`, one row per combination:

| column | meaning |
|---|---|
| `Case_Name` | `S1.42_h0.13_AOA8_W0.63` — also the directory name |
| `S_c` `h_c` `AOA_deg` `W_c` | the parameters |
| `Gap_c` | `(T − W) − S`; negative means the endplate reaches outboard past the wheel inner face |
| `Interaction` | `inboard` / `aligned` / `outboard_weak` / `outboard_strong` |
| `EP_Bottom_c` | endplate bottom edge above ground, `h − 0.04c` |
| `Enable_Mesh` | **you set this** — mesh this case |
| `Enable_Solve` | **you set this** — also solve it |
| `Notes` | free text, preserved across regeneration |

Enable cases by editing the CSV (any spreadsheet, or `sed`), or in bulk:

```bash
python3 build_matrix.py --enable-reference   # just the baseline
python3 build_matrix.py --enable-all         # all 420
python3 build_matrix.py                      # regenerate, keep current flags
```

**Regenerating preserves your flags and notes.** You can change the parameter
lists in `build_matrix.py` and re-run it without losing your selection.

> Enabling all 420 cases is tens of thousands of core-hours and tens of TB of
> intermediate data. Start with a line through the parameter space — one
> sweep of AOA at the baseline S/c, h/c and W/c is 7 cases.

Selecting a subset with the shell:

```bash
# all AOA at baseline S/c, h/c, W/c
python3 - <<'EOF'
import csv
rows = list(csv.DictReader(open("WingWheel_RunMatrix.csv")))
for r in rows:
    if r["S_c"] == "1.42" and r["h_c"] == "0.13" and r["W_c"] == "0.63":
        r["Enable_Mesh"] = r["Enable_Solve"] = "True"
with open("WingWheel_RunMatrix.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
EOF
```

---

## 6.2 Running

```bash
python3 run_campaign.py --list      # what would run, and what is already done
python3 run_campaign.py             # sequential
```

For each enabled row the runner does: `prepare_case.py` (if the directory does
not exist) → `./Allmesh` → `./Allsolve` → `./Allpost --summary`.

| option | effect |
|---|---|
| `--jobs N` | run N **cases** at the same time (default 1) |
| `--np M` | MPI **ranks per case** (default: `NP` from `env/project.env`) |
| `--mesh-only` | mesh everything, solve nothing |
| `--solve-only` | solve, assuming meshes exist |
| `--force` | redo cases that are already finished |
| `--allow-oversubscribe` | permit `jobs × np` > cores |

### The two kinds of parallelism

```
--jobs 1 --np 20      one case, 20 ranks        <- fastest single result
--jobs 2 --np 10      two cases, 10 ranks each
--jobs 4 --np 5       four cases, 5 ranks each  <- best total throughput
```

`jobs × np` must fit the machine. The runner refuses to oversubscribe:

```
ERROR: --jobs 4 x --np 20 = 80 ranks, but only 24 cores are available.
```

Which to choose: OpenFOAM scales sub-linearly, so **more concurrent cases
with fewer ranks each finishes a whole campaign sooner**, while fewer, wider
cases gets any one result sooner. The limit is memory, not cores — meshing
needs roughly 1.5 GB per million cells, so a 19 M cell case wants ~30 GB.
Four concurrent cases need ~120 GB. Check before committing.

`--np` is passed to each case through the environment, and `env/activate.sh`
lets an inherited `NP` override `project.env`. The mesh is decomposed for the
`NP` it was built with; `./Allsolve` refuses to run on a different count
rather than silently producing nonsense.

---

## 6.3 Resuming, stopping, watching

**Resumable by default.** A case with `.stage_mesh` / `.stage_solve` is
skipped. Re-run the same command after an interruption and it picks up.

**Stop cleanly** — the currently running cases finish, nothing new starts:

```bash
touch RANS_Simulations/campaign/STOP
```

Ctrl-C does the same. The `STOP` file is removed at the start of each run.

**Watch progress:**

```bash
tail -f RANS_Simulations/campaign/logs/S1.42_h0.13_AOA8_W0.63.log
column -s, -t RANS_Simulations/campaign/campaign_status.csv
```

`campaign_status.csv` is rewritten after every case (atomically, via a temp
file and rename, so reading it mid-campaign is safe):

| | |
|---|---|
| `Stage` `Result` | how far it got, and whether it worked |
| `Cells` `Layer_Coverage_pct` | mesh |
| `Converged` `Iterations` `Runtime_min` | solve |
| `CL_A_*` `CD_A_*` | forces, per group |
| `yPlus_wing_avg` | wall-treatment sanity |

One log per case in `campaign/logs/`, appended across restarts.

---

## 6.4 Disk

A finished case is tens of GB, dominated by `processor*/`. 420 of them will
not fit anywhere. Two options:

**Mesh and solve in waves**, pruning as you go:

```bash
python3 run_campaign.py --jobs 4 --np 5
for d in ../S*/ ; do
    python3 ../postprocessing/prune_case.py "$d" --force
done
```

`prune_case.py` keeps the setup, the logs, `postProcessing/`, `results.*` and
`images/`, dropping the case to a few MB. `results.json` — the thing you
actually want — survives.

**Or render images first** (`./Allpost --reconstruct --images`), then prune.

`controlDict` already sets `purgeWrite 2`, so only the two most recent written
states are kept during a run.

---

## 6.5 Collecting the campaign

Every case leaves a `results.json`. To build one table:

```bash
python3 - <<'EOF'
import csv, glob, json, os

rows = []
for path in sorted(glob.glob("RANS_Simulations/S*/results.json")):
    with open(path) as fh:
        r = json.load(fh)
    p, f = r.get("parameters", {}), r.get("forces", {})
    rows.append({
        "case":   r.get("case"),
        "S_c":    p.get("spanC"),
        "h_c":    p.get("heightC"),
        "AOA":    p.get("aoaDeg"),
        "W_c":    p.get("widthC"),
        "CL_A":   f.get("total", {}).get("Cl", {}).get("mean"),
        "CD_A":   f.get("total", {}).get("Cd", {}).get("mean"),
        "CL_A_wing":  f.get("wing", {}).get("Cl", {}).get("mean"),
        "CL_A_wheel": f.get("wheel", {}).get("Cl", {}).get("mean"),
        "spread": f.get("total", {}).get("Cl", {}).get("spread_rel"),
        "converged": r.get("solve", {}).get("converged"),
        "cells":  r.get("mesh", {}).get("cells"),
    })

with open("campaign_results.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)
print(len(rows), "cases -> campaign_results.csv")
EOF
```

Filter on `converged` and `spread` before plotting anything. A non-converged
case still produces a number, and that number is not a result.

---

Next: [7. Case reference](07_case_reference.md)
