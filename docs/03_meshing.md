# 3. Meshing

```bash
cd RANS_Simulations/S1.42_h0.13_AOA8_W0.63
./Allmesh
```

Baseline result: **≈ 20 M cells**, 4 prism layers on wing and wheel, 3 on the
ground. Measured on 20 ranks of a 24-core workstation: **under an hour**, peak
memory around 60 GB.

Layer addition is the expensive part — about 60 % of the total. See
[§3.7](#37-measured-on-the-baseline-case) for the full breakdown.

---

## 3.1 What `./Allmesh` does

| Step | Tool | Output |
|---|---|---|
| scale geometry mm → m | `surfaceTransformPoints` | `constant/triSurface/{wing,wheel}.stl` |
| sanity check | `surfaceCheck` | `log.surfaceCheck.*` (advisory) |
| feature edges | `surfaceFeatureExtract` | `constant/extendedFeatureEdgeMesh/*.eMesh` |
| background mesh | `blockMesh` | `constant/polyMesh` — 123 624 cells |
| extract the shedding edge | `surfaceSplitByPatch` | `constant/triSurface/endplate_bottom.stl` |
| split for MPI | `decomposePar` | `processor*/` (scotch) |
| refine, snap, layer | `snappyHexMesh` | the mesh |
| quality report | `checkMesh` | `log.checkMesh` |
| cell renumbering | `renumberMesh` | better cache locality |

The mesh is left **decomposed** in `processor*/`, which is what `./Allsolve`
expects. `./Allpost --reconstruct` merges it when you want to open it in
ParaView.

`./Allmesh` is a no-op if `.stage_mesh` exists. Force it with
`./Allmesh --force`.

---

## 3.2 The domain

`system/blockMeshDict`. All metres.

```
x  -0.712500 .. 1.181250     -9.50c .. 15.75c
y   0.000000 .. 0.675000      0.00c ..  9.00c      (half model)
z   0.000000 .. 0.637500      0.00c ..  8.50c      (z=0 is the ground)
```

Base cell is a **cube of 0.01875 m** = 18.75 mm = 0.25c, chosen so it divides
all three extents exactly:

```
1.893750 / 0.01875 = 101
0.675000 / 0.01875 =  36
0.637500 / 0.01875 =  34      ->  101 x 36 x 34 = 123 624 cells
```

A cubic base cell is not cosmetic: every refinement level halves the edge, so
the level-to-size table only holds if the starting cell is cubic.

| level | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|
| cell size [mm] | 4.688 | 2.344 | 1.172 | 0.586 | 0.293 | 0.146 |

### Patches

| patch | type | where | why |
|---|---|---|---|
| `inlet` | patch | xMin | fixed 10 m/s |
| `outlet` | patch | xMax | fixed pressure |
| `symmetry` | **symmetry** | yMin | the half-model plane |
| `side` | patch | yMax | frictionless (`slip`) |
| `ground` | **wall** | zMin | moving belt, carries layers |
| `sky` | patch | zMax | frictionless (`slip`) |

`side` and `sky` are `patch`, not `wall`, on purpose. A `wall` there would be
picked up by the `meshWave` wall-distance field that kOmegaSST blends on, and
would appear in the force-integration groups.

---

## 3.3 Refinement

`system/snappyHexMeshDict`. Three mechanisms stack.

### Surface levels (per STL region)

`level (min max)`: every cell cutting the surface reaches `min`; cells seeing
a feature sharper than `resolveFeatureAngle` (30°) go to `max`.

| region | level | reasoning |
|---|---|---|
| `wing-suction`, `wing-pressure` | 5 6 | the pressure-carrying surfaces |
| `wing-TE` | **6 7** | blunt TE is only 0.5 mm thick; needs >1 cell across |
| `wing-endplate_inner/outer/top` | 4 5 | flat, nothing to resolve |
| `wing-endplate_bottom` | 5 6 | sheds the main endplate vortex |
| `wing-endplate_LE`, `_TE` | 5 5 | fixed, no feature escalation |
| `wheel-tread/shoulders/sidewall` | 5 6 | |
| `wheel-plinth` | **6 7** | contact patch, strongest gradients |

### Distance refinement around the bodies

```
wing  { mode distance; levels ((0.015 5) (0.030 4)); }
wheel { mode distance; levels ((0.015 5) (0.030 4)); }
```

L5 within 15 mm of the surface, L4 within 30 mm. Read as increasing distance
with decreasing level.

### Volume boxes

`searchableBox` regions, all `mode inside`.

| box | level | covers |
|---|---|---|
| `L2-farfield` | 2 | the working section |
| `L3-body` | 3 | around both bodies |
| `L4-neargeom` | 4 | immediate vicinity |
| `L4-wake` | 4 | downstream of x = 40 mm |
| `L5-vortex-inboard` | 5 | inboard endplate vortex **path** |
| `L5-vortex-outboard` | 5 | outboard vortex **path** |
| `L6-contact-patch` | 6 | the wheel/ground contact zone |

Two boxes that an earlier version of the list had are deliberately gone:

- **`L5-gap-underwing`** — redundant. The wing surfaces already reach L5–L6
  from their own surface levels, and the distance refinement puts L5 within
  15 mm of them, which covers the ground-effect gap.
- **`L6-endplate-bottom-edge`** — replaced by distance refinement on the edge
  itself (below), which is both cheaper and parameter-following.

`L6-contact-patch` is at L6, not L7. The plinth surface level is (6 7), so
the cells at the wall are L6 at their coarsest and the plinth carries no
prism layers; a box finer than the wall cannot improve a resolution the wall
does not have, it only adds cells and a worse transition. Sized to the
geometric contact zone: with R = 43.875 mm the wheel surface is below
z = 4 mm only for |x| ≤ 18.4 mm.

### Refining the endplate vortex so it follows the geometry

The dominant vortex of this case is shed from the **bottom edge of the
endplate**. Its position moves with every parameter: span, ride height and
angle of attack all shift it. A fixed box is the wrong tool.

snappyHexMesh cannot apply distance refinement to one *region* of a
multi-region surface — but it can to a separate geometry *file*. So `Allmesh`
extracts just that strip:

```bash
surfaceSplitByPatch -patches '(wing-endplate_bottom)' constant/triSurface/wing.stl
mv constant/triSurface/wing_wing-endplate_bottom.stl    constant/triSurface/endplate_bottom.stl
```

and `snappyHexMeshDict` adds it as a geometry entry used **only** in
`refinementRegions` (the patch itself already comes from `wing.stl`):

```c
endplateBottomEdge
{
    mode    distance;
    levels  ((0.006 6) (0.030 5));
}
```

L6 within 6 mm of the shedding edge, L5 out to 30 mm. Roughly 0.2 M cells,
and it tracks the geometry across the whole parameter sweep.

> Only the 91 × 3 mm bottom strip is extracted. A distance shell around the
> whole endplate would be a great deal of mesh for no benefit.

Division of labour: this entry resolves where the vortex is **created**; the
`L5-vortex-inboard/outboard` boxes cover its downstream **trajectory**. Those
two are still fixed boxes, and are the thing to re-check when extending the
parameter range.

---

## 3.4 Layers

```
relativeSizes       false;      // absolute, in metres
firstLayerThickness 0.00014;    // 0.14 mm
expansionRatio      1.3;
nSurfaceLayers      4;          // wing-* and wheel-*
```

Thicknesses 0.140, 0.182, 0.237, 0.308 mm → 0.866 mm total. The ground gets
3 layers starting at 0.25 mm.

This puts the first cell centre at **y⁺ ≈ 2.5**, inside the buffer layer. That
choice drives the wall-function selection in [04_solving.md](04_solving.md) —
the two must be changed together.

Rough derivation: Re_c = 46 800 → Cf ≈ 0.058·Re^−0.2 ≈ 0.0068 →
τ_w ≈ 0.39 Pa → u_τ ≈ 0.58 m/s → y⁺(0.07 mm) ≈ 2.5.

---

## 3.4b Decomposition and renumbering

`decomposePar` splits the **background** mesh (123 624 cells) with `scotch`,
and `snappyHexMesh` rebalances as it refines. Measured on the baseline case
the final imbalance is **0.8 %**, so no `redistributePar` pass is needed.

`Allmesh` then runs:

```bash
mpirun -np $NP renumberMesh -overwrite -constant -no-fields -parallel
```

snappyHexMesh leaves the cells in refinement order, which scatters
neighbouring cells across memory. CuthillMcKee bandwidth reduction fixes
that, and on the baseline case it cut the matrix profile from
**8.84·10¹¹ to 1.69·10¹¹** — a factor of 5.2. That is cache locality the
solver gets for free.

`-no-fields` is correct here because `Allmesh` renumbers **before** any
fields exist; `Allsolve` restores `0/` afterwards. Renumbering a mesh whose
fields are already in place without renumbering them too would silently
scramble the solution.

---

## 3.5 Mesh quality limits

`system/meshQualityDict` starts from OpenFOAM's defaults and relaxes them:

| entry | here | OF default | why |
|---|---|---|---|
| `maxNonOrtho` | 75 | 65 | layer cells on curved surfaces |
| `maxInternalSkewness` | 6 | 4 | same |
| `minFaceWeight` | 0.05 | 0.02 | |
| `minTetQuality` | **−1e30** | 1e−9 | the important one |

`minTetQuality -1e30` effectively disables the tet-quality constraint.
With absolute layer thicknesses on curved surfaces, enforcing a positive tet
quality costs most of the layer coverage. The trade is accepted knowingly:
coverage buys near-wall accuracy, and the solver tolerates the resulting
cells. If the solve diverges immediately, this is the first knob to question.

---

## 3.6 Checking the mesh

`./Allmesh` prints the headline numbers; the three that matter:

```bash
grep -E 'cells:' log.snappyHexMesh | tail -1        # ~19 M for the baseline
grep -i 'coverage' log.snappyHexMesh                # overall layer coverage
grep -E '\*\*\*|Mesh OK' log.checkMesh
```

`checkMesh` failures do **not** abort `./Allmesh`. A snappyHexMesh mesh of
this kind routinely reports a handful of bad faces, and whether that matters
is a judgement call. Read the log.

To look at the mesh:

```bash
./Allpost --reconstruct
paraview case.foam
```

`writeFlags` includes `layerFields`, so there is a `nSurfaceLayers` volume
field to colour by — the fastest way to find where layers were dropped.

---

## 3.7 Measured on the baseline case

`S1.42_h0.13_AOA8_W0.63`, OpenFOAM v2606, 20 MPI ranks on one 24-core node.

### Where the time goes

| stage | time |
|---|---|
| scale STLs, `surfaceCheck`, `surfaceFeatureExtract`, `blockMesh`, `decomposePar` | ~15 s |
| refinement (feature, surface, shell) | ~10 min |
| snapping | ~10 min |
| **layer addition** | **~34 min** |
| `checkMesh` | ~1 min |

Layer addition dominates. If you are iterating on refinement only, set
`addLayers false` in `snappyHexMeshDict` and you get answers three times
faster.

### Cells per refinement level

Printed by snappyHexMesh at the end as `Cells per refinement level`. Worth
checking after any change to the boxes — it is the fastest way to see where
the cells actually went:

```
L0  0.11 M     L4  4.30 M
L1  0.02 M     L5 11.58 M
L2  0.52 M     L6  1.19 M
L3  0.59 M     L7  0.003 M
```

Total 18.32 M. L5 alone is 63 % of the mesh — it is the distance refinement
around both bodies, and it is the first place to look if the cell count needs
to come down. L7 is now almost empty: the only thing left at that level is
feature escalation on `wing-TE` and `wheel-plinth`, because
`L6-contact-patch` is a level-6 box (see below).

### Two lessons from getting this wrong

**A box at L7 is expensive, so size it to the geometry.** The first version of
`L7-contact-patch` was 100 × 52 × 8 mm and produced **10.07 M cells — 35 % of
the entire mesh**, pushing the total to 28.5 M cells. What the refinement is
meant to be is a thin shell following the plinth; a box fills that volume
solid instead. Sizing it to the actual contact zone
(|x| ≤ 18 mm, where the wheel surface is below z = 4 mm) brings it to 2.4 M.

Each level costs 8× the previous one for the same volume, so this arithmetic
is worth doing before meshing rather than after.

**Three patches get no prism layers at all, and asking for thinner ones does
not change it.** The per-patch table at the end of `log.snappyHexMesh` is the
thing to read:

```
patch                faces    target   achieved   thickness
ground              180851         3       2.92      92.3 %
wing-suction         28951         4       3.88      95.1 %
wing-pressure        27637         4       3.87      96.2 %
wing-TE                746         2          0         0 %
wing-endplate_inner  13234         4       3.45      79.1 %
wing-endplate_outer  14498         4       3.71      94.3 %
wing-endplate_top     3256         4       2.85        76 %
wing-endplate_bottom  3256         4       2.85      76.4 %
wing-endplate_LE      1356         4       3.87      97.3 %
wing-endplate_TE       212         2          0         0 %
wheel-tread          38861         4       3.95      84.3 %
wheel-shoulders      26056         4       3.88      89.9 %
wheel-sidewall       33128         4       4.00       100 %
wheel-plinth           902         2          0         0 %
```

Overall coverage 96.0 %.

`wing-TE`, `wing-endplate_TE` and `wheel-plinth` are at zero. They were
originally asked for 4 layers from 0.14 mm (0.87 mm total), which is more
than fits on a 0.5 mm blunt edge — but reducing them to 2 layers from
0.05 mm (0.115 mm) **did not help**. The limit is not thickness, it is
topology: snappyHexMesh refuses to extrude across a sharp convex edge under
its `featureAngle` / medial-axis rules, and the plinth additionally collides
with the ground layers where it cuts the ground plane.

**This is accepted, not an open defect.** snappyHexMesh is well known for
leaving gaps in layer coverage, particularly at sharp edges and where two
layered surfaces meet. Patches with no layers are a property of the mesher,
not a sign the setup is wrong — do not spend time chasing them.

It also matters less here than it looks, because all three sit inside the
finest refinement: at L7 the cell is 0.146 mm, so the first cell centre is
~0.073 mm from the wall, about the same wall distance the prism layers give
elsewhere and well inside the range the all-y⁺ wall functions cover.

The number to actually check is y⁺ in the `results.txt` of the case you run.
If you ever do need layers on a sharp edge, the lever is
`addLayersControls/featureAngle` (60 here) — raising it forces extrusion
across sharper edges, at some cost in cell quality.

The wheel tread and shoulders reaching only 63 % and 66 % is a different
thing: they are tessellated at 1.53 mm against 0.293 mm cells (see
[02_geometry.md](02_geometry.md#25-known-geometry-issues)), so the layers get
squeezed by the facets.

> Ordering matters in `addLayersControls/layers`. `layerParameters` iterates
> the entries in order and overwrites as it goes, so **the last matching
> entry wins** — regex or literal alike. Specific patches must come after the
> regexes they override.

---

## 3.8 Making it cheaper while you iterate

A 19 M cell mesh is a slow way to find a typo. Drop every surface level by
one and the boxes with it:

```bash
foamDictionary -entry 'castellatedMeshControls/refinementSurfaces/wing/level' \
    -set '(4 5)' system/snappyHexMeshDict
foamDictionary -entry 'castellatedMeshControls/maxGlobalCells' \
    -set 4000000 system/snappyHexMeshDict
```

That lands around 2 M cells and meshes in minutes. Do not report numbers from
it.

---

Next: [4. Solving](04_solving.md)
