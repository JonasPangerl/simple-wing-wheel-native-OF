# AGENTS.md — orientation for coding agents

Read this before changing anything. It is short on purpose; the detail lives
in `docs/`.

## What this repository is

A steady-RANS campaign for an inverted front wing in ground effect beside a
rotating wheel. Sub-scale: chord **c = 75 mm**, freestream **10 m/s**,
Re_c ≈ 46 800. Half model, symmetry plane at y = 0, moving ground, rotating
wheel. 420-case parameter sweep over S/c, h/c, AOA and W/c.

**Native OpenFOAM v2606 only**: `snappyHexMesh` for the mesh, `simpleFoam`
for the solve. This project was converted from a HELYX setup; **there must be
no HELYX dependency left**. If you find one (`.bcm`, `caseSetup*`,
`helyxHexMesh`, `bFoam`, `additionalFields`, `smDict`), it is a bug.

## Hard invariants

Do not change these without being asked explicitly. Each one has downstream
consequences that are not local.

1. **Millimetres in, metres everywhere else.** The geometry generator writes
   STLs in mm. `Allmesh` scales them by 0.001 into
   `constant/triSurface/{wing,wheel}.stl`. Every dictionary, refinement box
   and domain bound is in metres.

2. **`Aref = 1 m²` in `system/forceCoeffs`.** Reported `Cl`/`Cd` are
   coefficient-*areas* (CL·A, CD·A), matching the Diasinos papers. Not a bug.

3. **Wheel rotation sign.** `wheelOmega = -227.92` rad/s about `(0 1 0)`
   through `(0 0 0.043875)`. It follows from requiring the contact point to
   move with the belt: `omega_y = -UInf / R`. Flipping the sign spins the
   wheel backwards.

4. **`include/caseParameters` is the single source of truth.** Every number
   that defines a case lives there and is pulled into the dictionaries with
   `#include "<case>/include/caseParameters"` and `$variable`. Do not hardcode
   a value into a dictionary that already exists as a parameter.

5. **`prepare_case.py` only rewrites the seven GEOMETRY keys** of
   `caseParameters`. It errors out if a key is missing rather than silently
   producing a case with template values. Keep that behaviour.

6. **Case names must agree** between `prepare_case.py:case_name()` and
   `campaign/build_matrix.py:case_name()` — byte for byte. The campaign
   matches directories by name.

7. **Python 3.6 compatible, standard library only.** `/usr/bin/python3` on a
   Rocky 8 cluster is 3.6.8 and `openpyxl` is not installed. No
   `from __future__ import annotations`, no `list[str]` annotations, no walrus.

8. **Patch groups, not patch lists.** `snappyHexMeshDict` puts surfaces into
   `wingGroup`, `wheelGroup`, `wheelRotating`, `wheelGround`. Boundary
   conditions and force groups address those. Adding an STL region means
   adding it to a group, not editing five field files.

9. **Never put a patch group inside a regex key.** In `0.orig/*`, a group must
   be its own **literal** entry:

   ```c
   ground        { type zeroGradient; }   // correct
   wingGroup     { $ground; }             // correct
   "(ground|wingGroup)" { ... }           // SILENTLY WRONG
   ```

   `GeometricBoundaryField::readField` resolves patch names (step 1) and patch
   groups (step 2) only for keys where `keyword().isLiteral()`. Regex keys are
   handled in step 3 and are matched against patch **names** only. A group
   inside a regex therefore matches nothing, every wing and wheel patch is
   left unset, and the run aborts with
   `Cannot find patchField entry for wing-suction`.
   Regex over real patch names, like `"(side|sky)"`, is fine.

## Layout

```
env/activate.sh            sourced by every script; sets up OpenFOAM
env/project.env            machine-specific, gitignored
RANS_Simulations/
  _template/               the case. All* scripts live inside it
    include/caseParameters   <- all case-defining numbers
    0.orig/                  U p k omega nut
    constant/                transportProperties turbulenceProperties
    system/                  blockMeshDict snappyHexMeshDict controlDict ...
  scripts/caseFunctions.sh   shell helpers: runSerial/runParallel/markDone
  scripts/collect_results.py case dir -> results.json
  campaign/build_matrix.py   parameter space -> WingWheel_RunMatrix.csv
  campaign/run_campaign.py   runs the enabled rows, locally
```

## Conventions

- **`renumberMesh` runs before any fields exist**, with `-no-fields`.
  Renumbering a mesh whose fields are already written, without renumbering
  them too, silently scrambles the solution. Keep it between `checkMesh` and
  the end of `Allmesh`.
- **Stage markers**, not log parsing, decide what is done: `.stage_mesh`,
  `.stage_solve`. `isDone`/`markDone` in `caseFunctions.sh`.
- **Logs** are `log.<application>` in the case directory, OpenFOAM style.
- `runSerial` / `runParallel` wrap applications: they write the log, **abort
  on failure** and dump the log tail. Do not replace them with OpenFOAM's
  `RunFunctions`, which does not fail the script on a solver abort.
- `restoreFields0` is this project's `restore0Dir`. OpenFOAM's is a shell
  function in `bin/tools/RunFunctions`, not an executable.
- Machine facts (paths, core counts) belong in `env/project.env`. Physics
  belongs in the case template. Never mix them.

## Verifying a change

There is no unit-test suite; verification is running the thing.

```bash
# dictionaries parse, without meshing or solving
source env/activate.sh
cd RANS_Simulations/S1.42_h0.13_AOA8_W0.63
foamDictionary system/snappyHexMeshDict  > /dev/null   # repeat per dict
blockMesh && checkMesh -constant

# full smoke test, coarse: drop the refinement levels first
```

After touching the mesh setup, the numbers to check are **cell count**
(baseline ≈ 19 M), **layer coverage** (HELYX reached 100 %) and **checkMesh**.
After touching the solve, check **y+** (target ≈ 2.5; the wall functions are
the all-y+ variants and misuse shows up as y+ ≫ 30) and the **force spread**
over the averaging window in `results.txt`.

## Known open issues

These are real and documented, not things to silently "fix":

- The wing STL has **2 duplicate triangles** on the endplate outer edge, a
  defect in the geometry generator. `Allmesh` reports it and continues.
- The wheel is tessellated at **1.53 mm** circumferentially (`n_circ = 180` in
  `wheel_generator.py`) against a 0.293 mm target cell at L6, so the tread
  shows facets. Raising `n_circ` is the fix, but it changes the geometry the
  existing comparisons were made against.
- `snappyHexMesh` cannot do **per-STL-region distance refinement**. The way
  around it, used for the endplate shedding edge: `Allmesh` extracts that
  region into its own file with `surfaceSplitByPatch`, and
  `snappyHexMeshDict` adds it as a geometry entry used **only** in
  `refinementRegions`. That makes the refinement follow the geometry across
  the sweep. Use the same trick for any other region that needs distance
  refinement — do not go back to fixed boxes.
  **Still fixed boxes, and the thing to re-check when extending the
  parameter range:** `L5-vortex-inboard/outboard`, which cover the vortex
  trajectory downstream.

- **`wing-TE`, `wing-endplate_TE` and `wheel-plinth` end up with zero prism
  layers, and that is accepted.** snappyHexMesh is known for incomplete layer
  coverage at sharp edges and where two layered surfaces meet; reducing the
  request to 2 thin layers did not change it, because the limit is topology
  and not thickness. Do not chase this. All three sit in L7 cells
  (0.146 mm), so the near-wall spacing is comparable to the layered regions
  anyway. Overall coverage is ~92 %. The number that matters is y⁺ in
  `results.txt`.
  Ordering note for the `layers` dict: `layerParameters` iterates the entries
  and overwrites as it goes, so the **last matching entry wins**.

- **A refinement box at L7 costs 8× what it does at L6 for the same volume.**
  Check `Cells per refinement level` in `log.snappyHexMesh` after touching
  the boxes. An oversized `L7-contact-patch` once accounted for 35 % of the
  whole mesh.
- The interaction classification in `build_matrix.py` puts **280 of 420**
  cases in `outboard_strong`. That is the existing threshold choice, carried
  over unchanged.
