# 7. Case reference

Every file in the case template, what it does, and — where it matters — what
it replaced in the HELYX setup this project was converted from.

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
when S/c varies across the campaign. Carried over unchanged from the HELYX
setup, where `smGlobals::referenceValues::area` was 1 for the same reason.

---

## 7.3 Mesh dictionaries

### `blockMeshDict`

Domain `x −0.7125…1.18125`, `y 0…0.675`, `z 0…0.6375` m, split
`101 × 36 × 34` → 123 624 cubic cells of 18.75 mm.

Carried over from HELYX `baseMesh::BB*` (which was in mm) and
`meshOptionsGeneral::ManualLevel0EdgeLength 18.75`. The cell count matches the
HELYX mesh log exactly.

Patch renaming: HELYX meshed with generic `minX`/`maxX`/… names and then ran
`renamePatches`. blockMesh names them directly instead:

| HELYX | here | type |
|---|---|---|
| `minX` → `inlet-main` | `inlet` | patch |
| `maxX` → `outlet-main` | `outlet` | patch |
| `minY` → `symmetry-plane` | `symmetry` | symmetry |
| `maxY` → `tu-side-slip` | `side` | patch (slip) |
| `minZ` → `tu-grd-moving` | `ground` | wall |
| `maxZ` → `tu-sky-slip` | `sky` | patch (slip) |

`side` and `sky` became `patch` rather than `wall` deliberately: as walls they
would enter the `meshWave` wall-distance field that kOmegaSST blends on, and
appear in force-integration groups.

### `snappyHexMeshDict`

See [03_meshing.md](03_meshing.md) for the levels. The mapping from the HELYX
`.bcm`:

| HELYX | here |
|---|---|
| `<patch>@profile::RefLevelMin/Max` | `refinementSurfaces/<surface>/regions/<region>/level (min max)` |
| `RegionRefinementLevels ((15.0 5) (30.0 4))` (mm) | `refinementRegions/<surface> { mode distance; levels ((0.015 5) (0.030 4)); }` |
| `volRef::List` boxes | `geometry` `searchableBox` + `refinementRegions ... mode inside` |
| `Curvature <n>` (cells across curvature) | **no equivalent**; approximated by the min/max level pair plus `resolveFeatureAngle 30` |
| `FeatureRefineAngle` | `resolveFeatureAngle` (global, not per patch) |
| `LayersNLayers 4` | `addLayersControls/layers/"wing-.*"/nSurfaceLayers 4` |
| `LayersFirstLayerThickness 0.14` (mm, absolute) | `firstLayerThickness 0.00014` with `relativeSizes false` |
| `LayersExpRatio 1.3` | `expansionRatio 1.3` |
| `CustomHHMDict` minZ override | `layers/ground { nSurfaceLayers 3; firstLayerThickness 0.00025; }` |
| `meshOptionsQuality::*` | `meshQualityDict` |
| `meshOptionsSnapControls::*` | `snapControls` (small subset; most HELYX knobs do not exist) |
| naming-convention block (`#BEGIN NC`) | `patchInfo { type wall; inGroups (...); }` per region |

#### Two things that could not be translated

**1. Per-region distance refinement.** HELYX refined to L6 within 3 mm of
`wing-ep-bottom` and L7 within 5 mm of `wheel-plinth`. snappyHexMesh supports
distance refinement only around a whole geometry entry, not one region of it.
Replaced by two explicit boxes:

```
L6-endplate-bottom-edge   (-0.145 0.095 0.004) .. (-0.048 0.112 0.016)
L7-contact-patch          (-0.050 0.070 0.000) .. ( 0.050 0.122 0.008)
```

Same intent, different shape — a box instead of a shell following the surface.
**These boxes are positioned for the baseline geometry and do not follow the
parameters.** At a very different ride height or wheel width they need
repositioning. This is the main thing to re-check when extending the sweep.

**2. The `Curvature` setting.** HELYX refined by number of cells across a
curvature radius, per patch (8 on the wing surfaces, 18 on the TE, 12 on the
wheel). snappyHexMesh has no such control — it escalates from min to max level
where it sees features sharper than the global `resolveFeatureAngle`. The
min/max pairs were chosen to bracket the same cell sizes, but the *distribution*
of refinement over a curved surface will differ.

### `meshQualityDict`

Starts from `#includeEtc "caseDicts/meshQualityDict"`, then relaxes it as
HELYX did: `maxNonOrtho 75`, `maxInternalSkewness 6`, `minFaceWeight 0.05`,
`minVolRatio 1e-4`, `minDeterminant 1e-4`, `minTwist 0.05`,
`minTetQuality -1e30`.

`minTetQuality -1e30` is the consequential one: it disables the tet-quality
constraint. With absolute layer thicknesses on curved surfaces, enforcing it
costs most of the layer coverage. HELYX used the same value.

### `surfaceFeatureExtractDict`

`includedAngle 150` on both STLs, `openEdges yes`, `nonManifoldEdges no`.
Replaces HELYX's `GeometryFeatureLines`/`StringFeatures`. Produces the
`.eMesh` files that `explicitFeatureSnap` uses to keep the blunt TE and the
endplate edges sharp.

Safe because both STLs are vertex-welded (1106 vertices for 1142 wing
triangles), so dihedral angles are well defined.

### `decomposeParDict`

`method scotch`, `numberOfSubdomains` overwritten by the run scripts from
`NP`. HELYX used `ptscotch` for the same reason: no geometric hints needed and
it balances a locally refined mesh well.

---

## 7.4 Physics and numerics

### `constant/turbulenceProperties`

`kOmegaSST`. HELYX used `kOmegaSSTawtSM`, which added:

| HELYX feature | status |
|---|---|
| adaptive wall treatment (`awt`) | **reproduced** via all-y⁺ wall functions |
| Menter–Smirnov curvature correction | **lost** — vortex cores diffuse faster |
| Rumsey separation fix (`SFRumsey`) | **lost** — separation onset may differ |
| `nuRamp*` startup ramping | **lost** — replaced by `potentialFoam` initialisation |
| `kProduction Menter2003` | standard in OpenFOAM's kOmegaSST |

The two losses are the main physics difference against the old results and
should be stated whenever the two are compared.

### `0.orig/*` boundary conditions

| HELYX type | native type | field |
|---|---|---|
| `wallVelocity` | `noSlip` | U on wing |
| `translatingWallVelocity` | `fixedValue $groundVelocity` | U on ground, plinth |
| `rotatingWallVelocity` | `rotatingWallVelocity` | U on wheel |
| `slip` | `slip` | U on side, sky |
| `symmetry` | `symmetry` | all, on the symmetry plane |
| `zeroGradient` | `zeroGradient` | p on walls |
| `turbulentIntensityKineticEnergyInlet` | same | k inlet |
| `turbulentMixingLengthFrequencyInlet` | same | omega inlet |
| `kqRWallFunction` | **`kLowReWallFunction`** | k on walls |
| `awtOmegaWallFunction` | **`omegaWallFunction`** | omega on walls |
| `awtNutWallFunction` | **`nutUSpaldingWallFunction`** | nut on walls |

The three wall functions are matched to the y⁺ ≈ 2.5 layer stack. They are
the all-y⁺ continuous variants and must change together with the layer
thickness. `kqRWallFunction` has no native counterpart.

### `fvSchemes`

HELYX ran a coupled solver (`helyxCoupled`, `AMGSM` on a `Up` block) with its
own scheme set. This is a segregated SIMPLEC run, so the scheme list is a
conventional steady external-aero one rather than a translation:

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

`residualControl` replaces the HELYX `convergence` block (moving average of
`all-cz` with a variation criterion). The native mechanism is residual-based
rather than force-based, which is why `collect_results.py` also reports the
**force spread** over the averaging window — a residual criterion alone can
declare success on a case whose forces are still swinging.

### `controlDict`

`application simpleFoam`, `startFrom latestTime`, `endTime $nIterations`,
`deltaT 1`, `purgeWrite 2`.

For a steady SIMPLE run "time" is the iteration counter. HELYX ran a
pseudo-transient `timedHelyxCoupled` with `deltaT 0.025` to `endTime 10`
(= 400 steps); iteration counts are not comparable between the two.

---

## 7.5 Function objects

| HELYX | native |
|---|---|
| `smDict::forces` with `groups { all wing wheel }` | three `forceCoeffs` objects in `system/forceCoeffs` |
| `monitors.csv`, `residuals.csv`, `extremeValues.csv` | `postProcessing/*/0/*.dat` + `results.json` |
| `additionalFields` + `post-c46-v12.1.xml` | `system/fieldDerived` |
| `pressureCoeff` | `pressure`, `mode staticCoeff` → `Cp` |
| `totalPressureCoeff` | `pressure`, `mode totalCoeff` → `CpT` |
| `vorticity-magnitude` | `vorticity` (vector; take the magnitude when plotting) |
| `skinFrictionCoefficient` | `wallShearStress` |
| `yPlus` | `yPlus` |
| `normalizedHelicity`, `helicitySignedNormalizedQ`, `k-factor` | no equivalent; `Q` substituted |

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
