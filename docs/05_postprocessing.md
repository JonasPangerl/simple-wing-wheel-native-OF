# 5. Post-processing

```bash
cd RANS_Simulations/S1.42_h0.13_AOA8_W0.63
./Allpost --summary        # numbers    (cheap, always do this)
./Allpost --reconstruct    # merge processor*/ for ParaView  (expensive)
./Allpost --images         # render slices (needs ParaView)
```

Most of what you need is written **during** the solve by function objects, so
`--summary` only has to read and condense it.

---

## 5.1 What the solver writes

| Function object | Output | When |
|---|---|---|
| `forceCoeffs_{wing,wheel,total}` | `postProcessing/forceCoeffs_*/0/coefficient.dat` | every iteration |
| `residuals` | `postProcessing/residuals/0/solverInfo.dat` | every iteration |
| `yPlus` | `postProcessing/yPlus/0/yPlus.dat` + `yPlus` field | each write time |
| `fieldDerived` | `Cp`, `CpT`, `vorticity`, `Q`, `wallShearStress` | each write time |

Dictionaries: `system/forceCoeffs`, `system/residuals`, `system/yPlus`,
`system/fieldDerived`, all included from `system/controlDict`.

Derived fields are computed at write times only, so they cost almost nothing
during the run.

---

## 5.2 `results.json` and `results.txt`

`./Allpost --summary` runs `scripts/collect_results.py`, which condenses the
case into one machine-readable and one human-readable file.

```
====================================================================
  S1.42_h0.13_AOA8_W0.63
====================================================================

  S/c 1.42   h/c 0.13   AOA 8 deg   W/c 0.63
  Uinf 10.0 m/s   chord 0.075 m

  Mesh
    cells              18,720,401
    base cells         123,624
    layer coverage     100.0 %
    checkMesh          OK

  Solve
    status             converged
    iterations         1340
    solver time        98.4 min

  Force coefficient-areas  (mean over last 50 iterations)
    group        CL.A [m2]      CD.A [m2]     spread
    wing          -0.004213       0.000871     0.31 %
    wheel         -0.000204       0.001355     0.44 %
    total         -0.004417       0.002226     0.28 %

  y+  (last write)
    patch                         min      avg      max
    wing-suction                 0.41     2.38     7.92
    ...
====================================================================
```

Three numbers decide whether the result is usable:

1. **`status`** — did `residualControl` stop the run, or did it hit `endTime`?
2. **`spread`** — peak-to-peak variation of CL·A over the averaging window,
   as a fraction of the mean. Converged residuals with a 5 % force swing mean
   an unsteady flow being forced into a steady solve.
3. **`y+`** — the layer stack targets ≈ 2.5. Far above 30 and the wall
   functions are outside their design range.

Forces are reported as a **mean over the last 50 iterations**, not the final
value. Change the window with `--window N`.

`collect_results.py` reads column names from the `# Time ...` header of each
`.dat` file rather than by position, so it survives OpenFOAM reordering
columns between versions.

### Reading it from your own script

```python
import json
with open("results.json") as fh:
    r = json.load(fh)

r["forces"]["total"]["Cl"]["mean"]      # CL.A
r["forces"]["total"]["Cl"]["spread_rel"]
r["mesh"]["cells"]
r["solve"]["converged"]
r["yplus"]["wing-suction"]["avg"]
```

---

## 5.3 The `Aref = 1 m²` convention

`system/forceCoeffs` sets `Aref 1`, so the reported `Cl` and `Cd` are
**coefficient-areas**: CL·A and CD·A, in m². This matches what the Diasinos
papers tabulate, and is why `results.txt` labels them `CL.A [m2]`.

To get a conventional coefficient, divide by whatever reference area you want
to use — but then say which area you used, because the half-model planform
area changes with S/c across the campaign, which is exactly why the papers
avoid it.

`lRef` is the chord (0.075 m) and is only used for the moment coefficient.

Force groups:

| group | patches |
|---|---|
| `wing` | `wingGroup` — the nine `wing-*` patches |
| `wheel` | `wheelGroup` — the four `wheel-*` patches |
| `total` | both |

Tunnel walls, inlet, outlet and the symmetry plane are **not** in any group,
so they contribute nothing.

---

## 5.4 Opening a case in ParaView

```bash
./Allpost --reconstruct
paraview case.foam
```

`--reconstruct` runs `reconstructParMesh -constant` and
`reconstructPar -latestTime`, writing a full single-piece copy of the mesh and
the latest fields. For a 19 M cell mesh that is tens of GB — only do it for
cases you actually want to look at, and consider
`postprocessing/prune_case.py` afterwards.

Fields worth looking at:

| field | what it shows |
|---|---|
| `CpT` | vortex cores and wake losses — the most informative single field |
| `Cp` | surface loading on the wing |
| `Q` | vortex structures as isosurfaces |
| `vorticity` (x-component) | sense and strength of the endplate vortex |
| `yPlus` | whether the wall treatment is valid, patch by patch |
| `wallShearStress` | separation lines |
| `nSurfaceLayers` | where snappyHexMesh dropped layers |

> `vorticity` component 0 is **streamwise vorticity**. The field called
> `omega` is the turbulence specific dissipation rate and has nothing to do
> with it.

---

## 5.5 Batch image rendering

Needs `PVBATCH` set in `env/project.env`, and a reconstructed case.

```bash
./Allpost --reconstruct
./Allpost --images          # -> images/
```

Configuration lives in `RANS_Simulations/postprocessing/`:

| file | controls |
|---|---|
| `slices.yaml` | slice planes, positions, framing, which fields |
| `colormaps.yaml` | colour maps and ranges per field |
| `views.yaml` | camera positions for surface views |
| `slice_render.py` | the slice renderer |
| `render_case.py` | surface and volume views |
| `make_contact_sheets.py` | contact sheets from rendered images |
| `dump_camera.py` | read a camera out of an interactive ParaView session |

All geometry in `slices.yaml` is in **metres**, with the landmark positions
of the baseline case noted in its header.

### Field names changed in the migration

The HELYX post-processing produced several fields with no native equivalent.
`colormaps.yaml` and `slices.yaml` have been updated accordingly:

| HELYX | now |
|---|---|
| `pressureCoeff` | `Cp` |
| `totalPressureCoeff` | `CpT` |
| `magVorticity` | `vorticity`, coloured by Magnitude |
| `skinFrictionCoefficient` | `wallShearStress` |
| `helicitySignedNormalizedQ` | `Q` (loses the helicity sign) |
| `normalizedHelicity`, `normalizedHelicityVol`, `k-factor` | dropped, no equivalent |

The one real loss is the helicity sign on the Q field, which made the
rotation direction of a vortex readable from a single plot. Pair `Q` with the
x-component of `vorticity` to recover it.

The `Q` colour range in both config files is a **guess**
(±5·10⁵). Q scales with the square of a velocity gradient, so it is
mesh-dependent. Check the actual range once and set it.

---

## 5.6 Shrinking a finished case

```bash
python3 ../postprocessing/prune_case.py . --dry-run
python3 ../postprocessing/prune_case.py . --force
```

Removes `processor*/`, `constant/polyMesh` and the numeric time directories;
keeps the setup, the logs, `postProcessing/`, `results.*` and `images/`. A
19 M cell case drops from tens of GB to a few MB. `0.orig` survives because
its name is not numeric.

The case can be re-run afterwards with `./Allmesh && ./Allsolve`.

---

Next: [6. Campaign](06_campaign.md)
