# Wing + Wheel RANS campaign (native OpenFOAM)

Steady RANS of an inverted front wing in ground effect next to a rotating
wheel, on a sub-scale model (chord **c = 75 mm**, **10 m/s**), as a half model
with a symmetry plane. Built to sweep a 420-case parameter space and compare
against the Diasinos et al. papers.

**Pure native OpenFOAM v2606.** Meshing with `snappyHexMesh`, solving with
`simpleFoam` (segregated SIMPLEC). No dependency beyond OpenFOAM and
`python3`.

---

## What you need

| | |
|---|---|
| OpenFOAM | **v2606** (ESI/OpenCFD). Older works down to v2306 with a warning. |
| Python | 3.6 or newer, standard library only |
| ParaView | optional, only for rendering images |

---

## Quickstart

```bash
# 1. point the project at your OpenFOAM
cp env/project.env.example env/project.env
$EDITOR env/project.env            # set OPENFOAM_BASHRC and NP

# 2. generate the geometry (STLs)
cd Diasinos_Geometry_Generator
python3 -m geometry_generator.generate
cd ..

# 3. build one case and run it
cd RANS_Simulations
python3 prepare_case.py --span 1.42 --height 0.13 --aoa 8 --width 0.63
cd S1.42_h0.13_AOA8_W0.63
./Allrun
```

`./Allrun` meshes, solves and writes `results.txt` / `results.json`. Expect
roughly **19 M cells** and a few hours on 20 cores for the baseline case.

To run the whole sweep instead of one case, see
[docs/06_campaign.md](docs/06_campaign.md):

```bash
cd RANS_Simulations/campaign
python3 build_matrix.py --enable-reference   # pick what runs
python3 run_campaign.py --list               # check
python3 run_campaign.py --jobs 2 --np 10     # two cases at a time
```

---

## The four commands inside a case

| Command | Does |
|---|---|
| `./Allmesh` | geometry → `surfaceFeatureExtract` → `blockMesh` → `decomposePar` → `snappyHexMesh` → `checkMesh` |
| `./Allsolve` | initial fields → `potentialFoam` → `simpleFoam` |
| `./Allpost` | `--summary` (forces, y+), `--reconstruct`, `--images` |
| `./Allclean` | drop the solution; `--mesh` drops the mesh too |

They are resumable and skip finished stages. `./Allrun` is just the first
three in order.

---

## Repository map

```
env/                        OpenFOAM location and core count (machine-specific)
docs/                       the full process, start at 01_setup.md
Diasinos_Geometry_Generator/  parametric wing + wheel STL generator
RANS_Simulations/
  _template/                the case: 0.orig, constant, system, All* scripts
  prepare_case.py           _template -> a concrete case
  scripts/                  shared shell helpers + results collector
  campaign/                 run matrix and the campaign runner
  postprocessing/           ParaView slice and image rendering
```

---

## Documentation

**Read in order** for the full process:

1. [Setup](docs/01_setup.md) — install OpenFOAM v2606, configure the project
2. [Geometry](docs/02_geometry.md) — generate STLs, known geometry defects
3. [Meshing](docs/03_meshing.md) — the snappyHexMesh setup, level by level
4. [Solving](docs/04_solving.md) — boundary conditions, turbulence, convergence
5. [Post-processing](docs/05_postprocessing.md) — forces, y+, images
6. [Campaign](docs/06_campaign.md) — running many cases, sequentially or in parallel
7. [Case reference](docs/07_case_reference.md) — every dictionary entry and why it is set the way it is
8. [Troubleshooting](docs/08_troubleshooting.md) — what fails and why

[AGENTS.md](AGENTS.md) is the orientation file for AI coding agents, and a
useful summary of the project's invariants for humans too.

---

## Two things that will bite you if you do not know them

**Units.** The geometry generator writes STLs in **millimetres**. Everything
from `Allmesh` onward is in **metres** — the STLs are scaled by 0.001 on the
way in. Domain, refinement boxes and all dictionaries are metres.

**`Aref = 1 m²` is deliberate.** The `forceCoeffs` reference area is 1, not the
wing planform area, so the reported `Cl`/`Cd` are *coefficient-areas*
(CL·A, CD·A in m²). That is what the Diasinos papers tabulate. Changing it
silently breaks every comparison. See `RANS_Simulations/_template/system/forceCoeffs`.
