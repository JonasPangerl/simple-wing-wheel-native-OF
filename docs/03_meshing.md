# 3. Meshing

```bash
cd RANS_Simulations/S1.42_h0.13_AOA8_W0.63
./Allmesh
```

Baseline result: **≈ 19 M cells**, 4 prism layers on wing and wheel, 3 on the
ground. On 20 cores expect roughly 1–2 hours and ~30 GB of RAM.

---

## 3.1 What `./Allmesh` does

| Step | Tool | Output |
|---|---|---|
| scale geometry mm → m | `surfaceTransformPoints` | `constant/triSurface/{wing,wheel}.stl` |
| sanity check | `surfaceCheck` | `log.surfaceCheck.*` (advisory) |
| feature edges | `surfaceFeatureExtract` | `constant/extendedFeatureEdgeMesh/*.eMesh` |
| background mesh | `blockMesh` | `constant/polyMesh` — 123 624 cells |
| split for MPI | `decomposePar` | `processor*/` |
| refine, snap, layer | `snappyHexMesh` | the mesh |
| quality report | `checkMesh` | `log.checkMesh` |

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

Translated directly from the previous HELYX table. `level (min max)`: every
cell cutting the surface reaches `min`; cells seeing a feature sharper than
`resolveFeatureAngle` (30°) go to `max`.

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

Seven `searchableBox` regions carried over from the HELYX `volRef` list, plus
two that compensate for a snappyHexMesh limitation (below). All `mode inside`.

| box | level | covers |
|---|---|---|
| `L2-farfield` | 2 | the working section |
| `L3-body` | 3 | around both bodies |
| `L4-neargeom` | 4 | immediate vicinity |
| `L4-wake` | 4 | downstream of x = 40 mm |
| `L5-gap-underwing` | 5 | the ground-effect gap |
| `L5-vortex-inboard` | 5 | inboard endplate vortex path |
| `L5-vortex-outboard` | 5 | outboard vortex path |
| `L6-endplate-bottom-edge` | 6 | see below |
| `L7-contact-patch` | 7 | see below |

### The one thing that could not be translated

HELYX applied **distance refinement per STL region**: L6 within 3 mm of
`wing-ep-bottom`, and L7 within 5 mm of `wheel-plinth`. snappyHexMesh can do
distance refinement only around a *whole* geometry entry, not around one
region of it.

Substituted with two explicit boxes placed over those features:

```
L6-endplate-bottom-edge   (-0.145 0.095 0.004) .. (-0.048 0.112 0.016)
L7-contact-patch          (-0.050 0.070 0.000) .. ( 0.050 0.122 0.008)
```

Equivalent in intent, not identical in shape: a box instead of a shell
following the surface. If you change the geometry substantially — much
different ride height or wheel width — **these boxes do not follow it** and
must be repositioned. This is the main thing to re-check when extending the
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
3 layers starting at 0.25 mm, carried over from the HELYX override.

This puts the first cell centre at **y⁺ ≈ 2.5**, inside the buffer layer. That
choice drives the wall-function selection in [04_solving.md](04_solving.md) —
the two must be changed together.

Rough derivation: Re_c = 46 800 → Cf ≈ 0.058·Re^−0.2 ≈ 0.0068 →
τ_w ≈ 0.39 Pa → u_τ ≈ 0.58 m/s → y⁺(0.07 mm) ≈ 2.5.

---

## 3.5 Mesh quality limits

`system/meshQualityDict` starts from OpenFOAM's defaults and relaxes them the
way HELYX did:

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
grep -i 'coverage' log.snappyHexMesh                # HELYX reached 100 %
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

## 3.7 Making it cheaper while you iterate

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
