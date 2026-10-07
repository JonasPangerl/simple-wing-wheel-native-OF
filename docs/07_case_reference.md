# 7. Case reference

Every file in the case template, what it does, and — where it matters — why
it is set the way it is.

Read this when you need to change the setup and want to know what else moves
with it.

---

## 7.1 Case layout

```
S1.42_h0.13_AOA8_W0.63/
├── Allrun Allmesh Allsolve Allpost Allclean    the only commands you need
├── case.foam                                   empty marker, for ParaView
├── include/
│   ├── caseParameters                          ALL case-defining numbers
│   └── forceCoeffsBase                         settings shared by 3 force objects
├── 0.orig/                                     U p k omega nut
├── constant/
│   ├── transportProperties                     nu
│   ├── turbulenceProperties                    kOmegaSST
│   └── triSurface/                             scaled STLs (made by Allmesh)
└── system/
    ├── blockMeshDict                           the domain
    ├── snappyHexMeshDict                       the mesh
    ├── meshQualityDict                         quality limits
    ├── surfaceFeatureExtractDict               feature edges
    ├── decomposeParDict                        MPI split
    ├── controlDict                             run control + function objects
    ├── fvSchemes  fvSolution                   numerics
    ├── forceCoeffs  residuals  yPlus  fieldDerived    function objects
```

`include/caseParameters` is the single source of truth. Dictionaries pull from
it with:

```c
#include "<case>/include/caseParameters"
nu  $nuInf;
```

The `<case>/` tag needs OpenFOAM **api ≥ 2306**, which is why
`env/activate.sh` enforces it.

If a number already exists in `caseParameters`, never hardcode it into a
dictionary. `prepare_case.py` rewrites only the seven GEOMETRY keys and errors
out if one is missing, rather than silently producing a case with template
values.

---

## 7.2 `include/caseParameters`

| key | value | used by |
|---|---|---|
| `caseName` | per case | traceability |
| `spanC` `heightC` `aoaDeg` `widthC` | per case | traceability, `results.json` |
| `wingSTL` `wheelSTL` | per case | `Allmesh` geometry lookup |
| `UInf` `flowVelocity` | 10, `(10 0 0)` | `0.orig/U`, forces, `fieldDerived` |
| `pRef` | 0 | `0.orig/p` |
| `rhoInf` | 1.1629 | forces, `fieldDerived` |
| `nuInf` | 1.60278e-05 | `constant/transportProperties` |
| `cRef` | 0.075 | `lRef` for moments |
| `ARef` | **1** | `Aref` — see below |
| `turbI` `turbL` | 0.0015, 0.03 | inlet k and omega |
| `kInlet` `omegaInlet` | 3.375e-04, 1.118 | `0.orig/k`, `0.orig/omega` |
| `groundVelocity` | `(10 0 0)` | `ground`, `wheelGround` |
| `wheelOmega` `wheelAxis` `wheelOrigin` | −227.92, `(0 1 0)`, `(0 0 0.043875)` | `wheelRotating` |
| `nIterations` `writeEvery` | 2000, 500 | `controlDict` |

Derived, for checking:

```
Re_c       = UInf·cRef/nuInf                    = 46 795
kInlet     = 1.5·(UInf·turbI)²                  = 3.375e-04
omegaInlet = √kInlet/(0.09^0.25 · turbL)        = 1.118
wheelOmega = −UInf/R,  R = 0.585c = 0.043875    = −227.92
```

### Why `ARef = 1`

The reference area is 1 m², not the wing planform area, so `forceCoeffs`
reports **CL·A and CD·A** rather than CL and CD. That is the quantity the
Diasinos papers tabulate, and it sidesteps the question of which area to use
when S/c varies across the campaign.

---

## 7.3 Mesh dictionaries

### `blockMeshDict`

Domain `x −0.7125…1.18125`, `y 0…0.675`, `z 0…0.6375` m, split
`101 × 36 × 34` → 123 624 cubic cells of 18.75 mm.

The domain bounds are designed in mm and written here in metres; the base edge
length of 18.75 mm is what makes the cells cubic.

`blockMeshDict` names the boundary patches directly, so nothing has to be
renamed after meshing:

| face | patch | type |
|---|---|---|
| min x | `inlet` | patch |
| max x | `outlet` | patch |
| min y | `symmetry` | symmetry |
| max y | `side` | patch (slip) |
| min z | `ground` | wall |
| max z | `sky` | patch (slip) |

`side` and `sky` became `patch` rather than `wall` deliberately: as walls they
would enter the `meshWave` wall-distance field that kOmegaSST blends on, and
appear in force-integration groups.

### `snappyHexMeshDict`

See [03_meshing.md](03_meshing.md) for the levels. Where each piece of the
refinement specification lives:

| intent | entry |
|---|---|
| per-region surface level | `refinementSurfaces/<surface>/regions/<region>/level (min max)` |
| distance refinement around a body | `refinementRegions/<surface> { mode distance; levels ((0.015 5) (0.030 4)); }` |
| volume boxes | `geometry` `searchableBox` + `refinementRegions ... mode inside` |
| feature escalation | `resolveFeatureAngle 30` (global, not per patch) |
| layer count | `addLayersControls/layers/"wing-.*"/nSurfaceLayers 4` |
| first layer thickness | `firstLayerThickness 0.00014` with `relativeSizes false` |
| layer growth | `expansionRatio 1.3` |
| ground override | `layers/ground { nSurfaceLayers 3; firstLayerThickness 0.00025; }` |
| quality limits | `meshQualityDict` |
| patch names and groups | `patchInfo { type wall; inGroups (...); }` per region |

#### Two things snappyHexMesh cannot express directly

**1. Per-region distance refinement.** The endplate shedding edge
(`wing-endplate_bottom`) wants a distance shell around it, but snappyHexMesh
refines by distance only around a whole geometry entry, never around one
region of it.

The way around it: `Allmesh` extracts that one region into its own file with
`surfaceSplitByPatch`, and `snappyHexMeshDict` adds it as a geometry entry
(`endplateBottomEdge`) used **only** in `refinementRegions` — L6 within 6 mm,
L5 within 30 mm. Because it is the real geometry, the refinement follows the
edge for any span, ride height or angle of attack. **Use the same trick for
any other region that needs distance refinement; do not go back to a fixed
box.**

Two refinements are still fixed boxes, and they are the thing to re-check when
extending the parameter range:

```
L5-vortex-inboard    the downstream trajectory of the inboard vortex
L5-vortex-outboard   the same, outboard
```

They cover where the vortex *goes*, not where it is created, and they are
positioned for the baseline geometry.

**2. Refinement across a curvature radius.** There is no "n cells across the
local curvature radius" control. snappyHexMesh escalates from the min to the
max surface level where it sees a feature sharper than the global
`resolveFeatureAngle`. The min/max pairs are chosen to bracket the cell sizes
the curvature needs, but the *distribution* of refinement over a curved
surface is coarser-grained than a true curvature criterion would give.

### `meshQualityDict`

Starts from `#includeEtc "caseDicts/meshQualityDict"`, then relaxes it:
`maxNonOrtho 75`, `maxInternalSkewness 6`, `minFaceWeight 0.05`,
`minVolRatio 1e-4`, `minDeterminant 1e-4`, `minTwist 0.05`,
`minTetQuality -1e30`.

`minTetQuality -1e30` is the consequential one: it disables the tet-quality
constraint. With absolute layer thicknesses on curved surfaces, enforcing it
costs most of the layer coverage.

### `surfaceFeatureExtractDict`

`includedAngle 150` on both STLs, `openEdges yes`, `nonManifoldEdges no`.
Produces the `.eMesh` files that `explicitFeatureSnap` uses to keep the blunt
TE and the endplate edges sharp.

Safe because both STLs are vertex-welded (1106 vertices for 1142 wing
triangles), so dihedral angles are well defined.

### `decomposeParDict`

`method scotch`, `numberOfSubdomains` overwritten by the run scripts from
`NP`. Chosen because it needs no geometric hints and balances a locally
refined mesh well, where `simple` or `hierarchical` would not.

---

## 7.4 Physics and numerics

### `constant/turbulenceProperties`

`kOmegaSST`, with `kProduction Menter2003` as OpenFOAM's standard. Two model
extensions that an external-aero vortex case would benefit from do not exist
natively and are therefore absent:

| extension | status |
|---|---|
| curvature correction | **not available** — vortex cores diffuse faster |
| separation fix | **not available** — separation onset may differ |

The near-wall treatment is covered by the all-y⁺ wall functions below, and the
startup is handled by `potentialFoam` initialisation rather than a viscosity
ramp.

### `0.orig/*` boundary conditions

| field | condition | where |
|---|---|---|
| U | `noSlip` | wing |
| U | `fixedValue $groundVelocity` | ground, plinth |
| U | `rotatingWallVelocity` | wheel tread, shoulders, sidewall |
| U | `slip` | side, sky |
| all | `symmetry` | symmetry plane |
| p | `zeroGradient` | walls |
| k | `turbulentIntensityKineticEnergyInlet` | inlet |
| omega | `turbulentMixingLengthFrequencyInlet` | inlet |
| k | **`kLowReWallFunction`** | walls |
| omega | **`omegaWallFunction`** | walls |
| nut | **`nutUSpaldingWallFunction`** | walls |

The three wall functions are matched to the y⁺ ≈ 2.5 layer stack. They are
the all-y⁺ continuous variants and must change together with the layer
thickness.

### `fvSchemes`

A segregated SIMPLEC run, with a conventional steady external-aero scheme
set:

```
ddtSchemes      steadyState
div(phi,U)      bounded Gauss linearUpwindV grad(U)
turbulence      bounded Gauss upwind              // deliberate, 1st order
grad(U)         cellLimited Gauss linear 1
laplacian       Gauss linear corrected
wallDist        meshWave
```

### `fvSolution`

```
p               GAMG
U k omega       smoothSolver / GaussSeidel
SIMPLE          consistent yes     // SIMPLEC
relaxation      U 0.9, k/omega 0.7
residualControl p 1e-5, U 1e-5, k/omega 1e-4
```

`residualControl` is residual-based, not force-based, which is why
`collect_results.py` also reports the **force spread** over the averaging
window — a residual criterion alone can declare success on a case whose forces
are still swinging.

### `controlDict`

`application simpleFoam`, `startFrom latestTime`, `endTime $nIterations`,
`deltaT 1`, `purgeWrite 2`.

For a steady SIMPLE run "time" is the iteration counter, which is why
`deltaT` is 1 and `endTime` is an iteration count.

---

## 7.5 Function objects

| what | where |
|---|---|
| forces split `all` / `wing` / `wheel` | three `forceCoeffs` objects in `system/forceCoeffs` |
| monitors and residual history | `postProcessing/*/0/*.dat`, condensed into `results.json` |
| derived fields | `system/fieldDerived` |
| pressure coefficient | `pressure`, `mode staticCoeff` → `Cp` |
| total pressure coefficient | `pressure`, `mode totalCoeff` → `CpT` |
| vorticity | `vorticity` (vector; take the magnitude when plotting) |
| skin friction | `wallShearStress` |
| wall spacing | `yPlus` |
| vortex identification | `Q` |

The shared `forceCoeffs` settings live in `include/forceCoeffsBase` rather
than as a base dictionary inside the `functions` block. Anything that is a
dictionary in `functions` is constructed as a real function object, and a
`forceCoeffs` without `patches` aborts the run.

---

## 7.6 Patch groups

Assigned by `patchInfo/inGroups` in `snappyHexMeshDict`, and the reason the
field files are short.

| group | members | used for |
|---|---|---|
| `wingGroup` | all nine `wing-*` | `noSlip`, wing forces |
| `wheelGroup` | all four `wheel-*` | wheel forces |
| `wheelRotating` | `wheel-tread`, `-shoulders`, `-sidewall` | `rotatingWallVelocity` |
| `wheelGround` | `wheel-plinth` | moves with the belt |

A wheel region is in **two** groups: `wheelGroup` for forces and one motion
group for its velocity condition.

Adding an STL region means adding it to a group in `snappyHexMeshDict` — not
editing five field files.

### A group must never sit inside a regex key

In `0.orig/*`, each group needs its own **literal** entry:

```c
ground        { type zeroGradient; }   // correct
wingGroup     { $ground; }             // correct
"(ground|wingGroup)" { ... }           // silently wrong
```

`GeometricBoundaryField::readField` works in three passes: exact patch names,
then patch **groups**, then regex. The first two only consider keys for which
`keyword().isLiteral()` is true, and the regex pass matches against patch
**names** only. A group name inside a regex therefore matches nothing at all.
The patches fall through unset and the run aborts with

```
Cannot find patchField entry for wing-suction
```

Regex over genuine patch names — `"(side|sky)"`, `"(inlet|outlet)"` — is fine,
and is used in these files.

---

Next: [8. Troubleshooting](08_troubleshooting.md)
