# 4. Solving

```bash
cd RANS_Simulations/S1.42_h0.13_AOA8_W0.63
./Allsolve
```

Steady incompressible RANS with `simpleFoam` (SIMPLEC), kOmegaSST. Up to 2000
iterations, stopping early when the residual targets are met.

---

## 4.1 What `./Allsolve` does

| Step | Tool | Why |
|---|---|---|
| copy `0.orig` → `processor*/0` | (built in) | fresh initial fields |
| check boundary conditions | `patchSummary` | catches an unhandled patch *before* spending compute |
| potential-flow start | `potentialFoam -writephi` | divergence-free initial field |
| solve | `simpleFoam` | |

Options:

```bash
./Allsolve --continue       # resume from the latest time, do not reset
./Allsolve --no-potential   # skip the potential-flow initialisation
```

`startFrom` is `latestTime` in `controlDict`, so an interrupted run continues
by re-running with `--continue`.

`potentialFoam` builds its own `Phi` field (`READ_IF_PRESENT`) and infers the
boundary types from `p`, so there is no `0/Phi` to maintain. It is worth a few
hundred SIMPLE iterations on a case like this.

---

## 4.2 The physics

From `include/caseParameters` — the one place these numbers live:

| | value | |
|---|---|---|
| freestream | 10 m/s, +x | |
| chord | 0.075 m | `cRef` |
| ρ | 1.1629 kg/m³ | air at 288.16 K |
| ν | 1.60278·10⁻⁵ m²/s | |
| Re_c | 46 795 | `UInf·cRef/nuInf` |
| inlet TI | 0.15 % | `turbI` |
| mixing length | 0.03 m | `turbL` |
| k inlet | 3.375·10⁻⁴ | `1.5·(UInf·turbI)²` |
| ω inlet | 1.118 | `√k/(Cμ^0.25·turbL)` |

`p` is **kinematic** (m²/s²) — `simpleFoam` is incompressible. Multiply by
`rhoInf` for Pa.

---

## 4.3 Boundary conditions

Patch **groups** carry the conditions, not individual patch names.
`snappyHexMeshDict` assigns every STL region to a group, so adding a surface
means adding it to a group rather than editing five field files.

| group | members |
|---|---|
| `wingGroup` | all nine `wing-*` patches |
| `wheelGroup` | all four `wheel-*` patches (force integration) |
| `wheelRotating` | `wheel-tread`, `-shoulders`, `-sidewall` |
| `wheelGround` | `wheel-plinth` |

| patch/group | U | p | k / ω / νt |
|---|---|---|---|
| `inlet` | `fixedValue (10 0 0)` | `zeroGradient` | turbulent inlet / `calculated` |
| `outlet` | `pressureInletOutletVelocity` | `fixedValue 0` | `inletOutlet` / `calculated` |
| `symmetry` | `symmetry` | `symmetry` | `symmetry` |
| `side`, `sky` | `slip` | `slip` | `slip` / `calculated` |
| `ground` | `fixedValue (10 0 0)` | `zeroGradient` | wall functions |
| `wingGroup` | `noSlip` | `zeroGradient` | wall functions |
| `wheelRotating` | `rotatingWallVelocity` | `zeroGradient` | wall functions |
| `wheelGround` | `fixedValue (10 0 0)` | `zeroGradient` | wall functions |

### Moving ground

The belt translates downstream at the freestream speed, so the ground is at
rest relative to the air far from the model — the standard rolling-road
arrangement.

### Rotating wheel

```
wheelOmega   -227.92        // rad/s
wheelAxis    (0 1 0)
wheelOrigin  (0 0 0.043875) // R = 0.585c, so the wheel touches z = 0
```

`rotatingWallVelocity` imposes the tangential surface velocity ω×r without
moving the mesh — correct for steady RANS.

**The sign is not arbitrary.** The contact point must move with the belt:

```
v_x(contact) = -omega_y · R  =  +UInf
omega_y = -UInf / R = -10 / 0.043875 = -227.92 rad/s
```

Flip it and the wheel spins backwards, which changes the wake entirely while
still converging happily.

The plinth is in `wheelGround`, not `wheelRotating`: it is the collar through
the ground plane and moves with the belt.

---

## 4.4 Turbulence and the wall treatment

`constant/turbulenceProperties`: plain **kOmegaSST**.

Native OpenFOAM offers no curvature correction and no separation fix for
kOmegaSST, so two limitations come with it:

- **no curvature correction** → endplate and wheel vortex cores diffuse
  somewhat faster
- **no separation fix** → separation onset on the suction side may differ

The near-wall treatment is handled by the wall functions below.

### Wall functions

The layer stack targets y⁺ ≈ 2.5 — the buffer layer, where pure log-law wall
functions are invalid and pure low-Re resolution is not available either. The
all-y⁺ continuous variants are therefore mandatory, not stylistic:

| field | type |
|---|---|
| `nut` | `nutUSpaldingWallFunction` |
| `k` | `kLowReWallFunction` |
| `omega` | `omegaWallFunction` |

`nutUSpaldingWallFunction` uses Spalding's single continuous law, valid from
y⁺ < 1 into the log layer, and works on velocity relative to the wall — which
matters here, with a moving belt and a spinning wheel.

`kLowReWallFunction` is the all-y⁺ choice for `k`: it blends the viscous and
log-layer forms, where OpenFOAM's `kqRWallFunction` is a plain zero-gradient
condition that leaves the near-wall `k` profile to the mesh — fine at log-law
y⁺, not at 2.5.

**If you change the layer thickness, revisit these.** They are a matched pair.

---

## 4.5 Numerics

`system/fvSchemes`:

```
div(phi,U)      bounded Gauss linearUpwindV grad(U);   // 2nd order
turbulence      bounded Gauss upwind;                  // 1st order, deliberate
grad(U)         cellLimited Gauss linear 1;
```

Turbulence transport is first-order on purpose: second-order k/ω transport is
the usual reason residuals stall on a mesh like this, and the effect on the
integrated forces is small. The `V` variant of `linearUpwind` limits the
velocity vector as a whole, which behaves better in vortex cores than
limiting each component.

`system/fvSolution`:

```
SIMPLE { consistent yes; }          // SIMPLEC
relaxationFactors { U 0.9; "(k|omega)" 0.7; }
residualControl { p 1e-5; U 1e-5; "(k|omega)" 1e-4; }
```

`residualControl` is what makes a 420-case campaign affordable: most cases
converge well before `endTime`.

---

## 4.6 Did it converge?

```bash
./Allpost --summary
cat results.txt
```

Three things to look at, in order:

1. **`residualControl` satisfied?** `results.txt` says `converged` or
   `NOT converged`. `simpleFoam` prints `solution converged` when it stops
   early.
2. **Force spread.** `results.txt` reports the peak-to-peak spread of CL·A
   over the last 50 iterations as a percentage. A "converged" residual with a
   force still swinging by several percent means an unsteady flow being
   forced into a steady solve — likely at high AOA or low ride height.
3. **y⁺.** Target ≈ 2.5. Values well above 30 mean the wall functions are
   being used outside their design range and the near-wall solution is not
   trustworthy.

Live monitoring, from another shell:

```bash
tail -f log.simpleFoam | grep -E 'Time =|Ux|p,'
```

The residual history is also written as fields (`writeResidualFields true`),
so a stalled case can be opened in ParaView to see *where* it will not settle
— usually far more informative than the global residual.

---

## 4.7 If it diverges

In the order worth trying:

1. Drop relaxation: `U 0.7`, `k`/`omega` 0.5.
2. First-order momentum for the first few hundred iterations:
   `div(phi,U) bounded Gauss upwind;` then switch back and `--continue`.
3. Check the mesh. `minTetQuality -1e30` (see
   [03_meshing.md](03_meshing.md#35-mesh-quality-limits)) permits some
   genuinely poor cells. `checkMesh` plus the residual fields will show
   whether divergence is localised at the contact patch or the blunt TE.
4. Confirm `patchSummary` resolved every patch — an unhandled patch silently
   falling back to a default is a classic cause.

---

Next: [5. Post-processing](05_postprocessing.md)
