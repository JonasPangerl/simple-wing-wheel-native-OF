# 8. Troubleshooting

Ordered by where in the pipeline it goes wrong.

---

## 8.1 Environment

**`env/project.env does not exist`**
→ `cp env/project.env.example env/project.env` and set `OPENFOAM_BASHRC`.

**`OPENFOAM_BASHRC does not point at a file`**
→ Must be an **absolute** path to `etc/bashrc`, not the installation root.

**`sourced ... but simpleFoam is not on the PATH`**
→ OpenFOAM is unpacked but not built, or built with a different
`WM_OPTIONS` than the `etc/bashrc` now reports. Check that
`$WM_PROJECT_DIR/platforms/$WM_OPTIONS/bin/simpleFoam` exists.

**`OpenFOAM api 2212 is too old`**
→ Needs ≥ 2306 for the `#include "<case>/..."` syntax. See
[01_setup.md](01_setup.md).

**`mpirun: command not found`, but only inside a run**
→ Your MPI comes from a module that is not in `MODULES_TO_LOAD`.

---

## 8.2 Geometry

**`geometry not found` from `Allmesh` or `prepare_case.py`**
→ Only the baseline geometry is committed. Generate the rest:
`cd Diasinos_Geometry_Generator && .venv/bin/python -m geometry_generator.generate`.
Check the expected file name in `include/caseParameters` (`wingSTL`,
`wheelSTL`) against what is in `output/wings/`.

**`ModuleNotFoundError: No module named 'dataclasses'`**
→ The geometry generator needs Python ≥ 3.7. Use the venv
([02_geometry.md](02_geometry.md#23-running-the-generator)). The *simulation*
scripts run on 3.6; only the generator does not.

**`No module named 'stl'`**
→ `pip install -r requirements.txt` in the generator's venv (`numpy-stl`).

**`surfaceCheck` reports illegal triangles / not closed**
→ Expected on this geometry, and non-fatal by design. See
[02_geometry.md §2.5](02_geometry.md#25-known-geometry-issues).

---

## 8.3 Meshing

**snappyHexMesh stops with the cell count pinned at `maxGlobalCells`**
→ Refinement was cut off mid-level, so the mesh is wrong, not just coarse.
Raise `castellatedMeshControls/maxGlobalCells` (currently 40 M; the baseline
finishes around 19 M). Remember snappyHexMesh counts cells *before* removing
the region outside the fluid.

**Out of memory during meshing**
→ Roughly 1.5 GB per million cells. A 19 M cell case wants ~30 GB across the
ranks. Lower `--jobs` in a campaign, or raise `NP` so the mesh is split more
finely — but note that each rank also carries the full triSurface.

**A patch got zero layers**
→ Read the per-patch table at the end of `log.snappyHexMesh` (`patch / faces
/ target / achieved / thickness`). If `achieved` is 0 the requested stack
does not fit: 4 layers from 0.14 mm with ratio 1.3 total 0.87 mm, and a blunt
0.5 mm trailing edge has at most 0.25 mm per side. Give that patch its own
entry with fewer, thinner layers — `wing-TE`, `wing-endplate_TE` and
`wheel-plinth` already have one. Put specific entries **after** the regexes
they override; the last matching entry wins.

**`Layer specification for X does not match any patch`**
→ A key in `addLayersControls/layers` matches nothing. Check it against the
patch names snappyHexMesh actually created (the `patchInfo/name` entries in
`snappyHexMeshDict`), not against the STL solid names.

**The mesh is far bigger than expected**
→ Look at `Cells per refinement level` at the end of `log.snappyHexMesh`.
A `searchableBox` fills its volume solid, and each level costs 8× the
previous one, so an oversized box at L6 or L7 dominates everything else.
This happened here: a 100 × 52 × 8 mm box at L7 was 35 % of the mesh.

**Layer coverage much below 100 %**
→ Check `log.snappyHexMesh` for which patches lost layers, and colour the
reconstructed mesh by `nSurfaceLayers`. Usual causes, in order:
1. `meshQualityDict` too strict — `minTetQuality` is the dominant one
2. `firstLayerThickness` too large for the local cell size (a 0.14 mm first
   layer needs at least L6 = 0.293 mm cells)
3. `nLayerIter` / `nRelaxedIter` too low
4. genuinely thin geometry: the 0.5 mm blunt TE cannot take 0.87 mm of layers
   on both sides

**`Entry 'relaxed' not found in dictionary "meshQualityControls"`**
→ `addLayersControls/nRelaxedIter` is set but `system/meshQualityDict` has no
`relaxed` sub-dictionary. Painful one: it aborts *after* the layers have been
built, so a 40-minute mesh is lost. The block is shipped in
`meshQualityDict`; if you replaced that file, put it back. Note it *replaces*
the main quality settings rather than extending them, so it has to be
complete.

**snappyHexMesh spends many minutes in `Shell refinement iteration` with
almost no new cells**
→ `minRefinementCells` is too small for the mesh size. The loop runs until
fewer than that many cells are selected, capped at 100 iterations. At the
tutorial value of 10 this case burned ~8 minutes adding ~1000 cells. It is
set to 1000 here for that reason.

**`locationInMesh` is outside the mesh / the mesh comes out empty**
→ `(0.5001 0.3001 0.3001)` must be inside the fluid and off the base-mesh
face planes. If you change the domain, move it.

**The mesh leaks into the inside of the wing or the wheel**
→ The STLs are not closed by design (two parts each). No `mode inside`
refinement region is attached to them for this reason. If you add one, it will
misbehave.

**Faceted wing or wheel surfaces**
→ The STL tessellation is coarser than the cells. The wheel is 1.53 mm
circumferentially against 0.293 mm cells. See
[02_geometry.md §2.5](02_geometry.md#25-known-geometry-issues). Refining the
mesh further does not help; the geometry has to be re-tessellated.

**`checkMesh` reports failures but `Allmesh` continued**
→ Deliberate. A snappyHexMesh mesh of this kind routinely reports some bad
faces, and whether it matters is a judgement call. Read `log.checkMesh`; if
the solve then diverges, start with `meshQualityDict`.

---

## 8.4 Solving

**`the mesh is decomposed for 20 ranks but env/project.env says NP=8`**
→ Either set `NP=20`, or `./Allmesh --force` to redecompose. The check exists
because running on a mismatched count would silently produce nonsense.

**`no processor* directories - run ./Allmesh first`**
→ `./Allclean --mesh` was run, or meshing never completed. `.stage_mesh` is
the marker.

**Diverges in the first few iterations**
→ In order: lower relaxation (`U 0.7`, `k`/`omega` 0.5); switch
`div(phi,U)` to `bounded Gauss upwind` for a few hundred iterations and then
back with `--continue`; check `patchSummary`; then question the mesh.

**Residuals stall at ~1e-3 and will not drop**
→ Usually physical, not numerical: the flow is genuinely unsteady. Check the
**force spread** in `results.txt`. If the forces oscillate steadily, a steady
RANS run cannot converge further, and the honest answer is a time-averaged
value with the spread quoted — or a transient run. Expect this at high AOA and
low ride height.

The residual *fields* are written (`writeResidualFields true`), so you can
open the case in ParaView and see where it will not settle. Far more useful
than the global number.

**y⁺ comes out at 50–200 instead of ~2.5**
→ Layers were not built where you think. Check layer coverage first. The wall
functions are the all-y⁺ variants so the run still completes, but the
near-wall solution is not trustworthy.

**Converged, but the forces look wrong in sign**
→ Check the wheel rotation sign (`wheelOmega` must be **negative**) and that
`liftDir` is `(0 0 1)`. Downforce is reported as a **negative** CL·A. An
inverted wing in ground effect at 8° should give a clearly negative wing CL·A.

**`forceCoeffs` aborts: cannot find patch group**
→ `wingGroup` / `wheelGroup` come from `patchInfo/inGroups` in
`snappyHexMeshDict`. If you renamed an STL region without updating the groups,
the mesh has no such group. `./Allmesh --force` after fixing it.

---

## 8.5 Post-processing

**`results.txt` has no forces section**
→ `postProcessing/forceCoeffs_*/` is missing: the solve never ran, or
`controlDict`'s `functions` block failed to load. Check `log.simpleFoam`.

**`nothing to reconstruct - no processor*/ mesh`**
→ Already pruned, or never meshed.

**`PVBATCH is empty in env/project.env`**
→ Image rendering needs ParaView. The numbers do not.

**ParaView shows no `Cp` / `CpT` / `Q`**
→ Those are written at **write times** only. Make sure you reconstructed the
latest time (`./Allpost --reconstruct` does `-latestTime`), and that the run
reached a write time (`writeEvery` is 500 iterations).

**`Q` renders as flat colour**
→ The range in `colormaps.yaml` / `slices.yaml` is a guess (±5·10⁵). Q scales
with the square of a velocity gradient. Read the real range in ParaView and
set it.

---

## 8.6 Campaign

**`No cases have Enable_Mesh set`**
→ `python3 build_matrix.py --enable-reference`.

**`--jobs 4 x --np 20 = 80 ranks, but only 24 cores`**
→ Lower one. `--allow-oversubscribe` exists but competing MPI processes are
usually slower than running the cases in sequence.

**A case is skipped although it should rerun**
→ `.stage_mesh` / `.stage_solve` mark it done. `--force`, or
`./Allclean --mesh` in that directory.

**The campaign fills the disk**
→ Each finished case is tens of GB in `processor*/`. Run in waves and prune
([06_campaign.md §6.4](06_campaign.md#64-disk)).

**A case crashed and the campaign carried on**
→ By design. `campaign_status.csv` carries the `Result`, and
`campaign/logs/<case>.log` has the full output.

---

## 8.7 Checking a change without running anything

```bash
source env/activate.sh
cd RANS_Simulations/S1.42_h0.13_AOA8_W0.63

# does every dictionary parse, with the includes resolved?
for d in system/*Dict system/controlDict system/fvSchemes system/fvSolution \
         constant/transportProperties constant/turbulenceProperties; do
    foamDictionary "$d" > /dev/null && echo "ok   $d" || echo "FAIL $d"
done

# do the field files parse?
for f in 0.orig/*; do foamDictionary "$f" > /dev/null \
    && echo "ok   $f" || echo "FAIL $f"; done

# is a parameter resolving as expected?
foamDictionary -entry nu -value constant/transportProperties   # 1.60278e-05

# the domain, cheaply
blockMesh && checkMesh -constant
```

`foamDictionary` expands `#include` and `$variable`, so this catches the
majority of setup mistakes in seconds.
