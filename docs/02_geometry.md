# 2. Geometry

The wing and wheel STLs are generated parametrically. The full geometric
definition — every dimension, every positioning rule — is in
[`../Diasinos_Geometry_Generator/GEOMETRY_SPECIFICATION.md`](../Diasinos_Geometry_Generator/GEOMETRY_SPECIFICATION.md).
This page is only about producing the files.

---

## 2.1 Coordinate system and units

```
x  streamwise, positive downstream.  Wheel centre at x = 0.
y  spanwise,   positive outboard.    Symmetry plane at y = 0.
z  vertical,   positive up.          Ground plane at z = 0.
```

**The generator writes millimetres.** Everything in the simulation is in
metres; `Allmesh` scales the STLs by 0.001 on the way in. Do not pre-scale
them yourself.

Reference chord **c = 75 mm**. Parameters are quoted normalised by it.

Baseline case extents, for orientation:

| | x [mm] | y [mm] | z [mm] |
|---|---|---|---|
| wing + endplate | −141.15 … −50.40 | −2.00 … 106.50 | 6.75 … 37.73 |
| wheel + plinth | −43.88 … 43.88 | 72.75 … 120.00 | −6.00 … 87.75 |

The wheel reaches **z = −6 mm**, below the ground plane. That is the plinth:
a collar that deliberately pierces the ground so the contact patch is a clean
cut rather than a tangential singularity. The domain starts at z = 0, so
snappyHexMesh trims it.

---

## 2.2 Parameter space

`Diasinos_Geometry_Generator/params.yaml`:

```yaml
spans:   [0.97, 1.06, 1.24, 1.42, 1.60]   # S/c  half-span to endplate outer edge
heights: [0.08, 0.13, 0.18, 0.28]         # h/c  ride height
angles:  [0, 2, 4, 6, 8, 10, 12]          # AOA  [deg]
widths:  [0.56, 0.63, 0.70]               # W/c  wheel width
```

5 × 4 × 7 × 3 = **420** combinations. Wings depend on S, h and AOA (420
files); wheels only on W (3 files).

The baseline, and the configuration the papers report:
**S/c 1.42, h/c 0.13, AOA 8°, W/c 0.63.**

File names, which the rest of the pipeline relies on:

```
output/wings/wing_S<span>_h<height>_AOA<aoa>.stl     e.g. wing_S1.42_h0.13_AOA8.stl
output/wheels/wheel_W<width>.stl                    e.g. wheel_W0.63.stl
```

---

## 2.3 Running the generator

The generator needs **Python ≥ 3.7** (it uses `dataclasses`) plus `numpy`,
`scipy`, `numpy-stl`, `pyyaml` and `matplotlib`. That is more than the
simulation pipeline needs, which is why it gets its own virtual environment.

> The simulation scripts themselves run on Python 3.6 with nothing installed.
> Only the geometry step has real dependencies.

```bash
cd Diasinos_Geometry_Generator

python3 -m venv .venv                      # needs python3 >= 3.7
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m geometry_generator.generate
```

That writes all 420 wings and 3 wheels into `output/`, plus
`output/combinations.csv` logging what was made. Expect a few minutes and
about 63 MB.

To generate a subset, point `--config` at a trimmed copy of `params.yaml`:

```bash
cp params.yaml /tmp/one.yaml
# edit the four lists down to a single value each, and set output_dir
.venv/bin/python -m geometry_generator.generate --config /tmp/one.yaml
```

`--preview` renders a matplotlib view instead of writing STLs, with
`--span/--height/--angle/--width` to pick the combination.

A `RuntimeWarning` about `geometry_generator.generate found in sys.modules` is
harmless — a `runpy` artifact of the package importing its own entry point.

### Reproducibility

Regenerating does **not** give byte-identical files: ASCII float formatting
shifts in the last digits between library versions. The geometry is
reproducible — regenerated vertices agree with the committed baseline to
within 3·10⁻¹⁴ mm, in identical order, with identical triangle counts per
region. Compare geometry numerically, never by checksum.

---

## 2.4 STL regions

Each STL carries named solids, and `snappyHexMeshDict` refers to them
directly to set refinement levels and patch names. **Renaming a solid in the
generator breaks the mesh setup.**

| `wing_*.stl` | triangles | | `wheel_*.stl` | triangles |
|---|---|---|---|---|
| `wing-suction` | 538 | | `wheel-tread` | 360 |
| `wing-pressure` | 530 | | `wheel-shoulders` | 17280 |
| `wing-TE` | 2 | | `wheel-sidewall` | 11160 |
| `wing-endplate_inner` | 4 | | `wheel-plinth` | 360 |
| `wing-endplate_outer` | 4 | | | |
| `wing-endplate_top` | 19 | | | |
| `wing-endplate_bottom` | 19 | | | |
| `wing-endplate_LE` | 24 | | | |
| `wing-endplate_TE` | 2 | | | |

(counts for the baseline case)

---

## 2.5 Known geometry issues

These are real. They are documented rather than silently patched, because
fixing them changes the geometry the existing results were produced on.

### The wing is prismatic, with only two spanwise stations

`wing-suction` has 538 triangles across **2** spanwise stations
(y = −2.0 and y = 105.0 mm). `surfaceCheck` therefore reports that 96 % of
the triangles have a quality below 0.05.

**This is not an error.** The wing has a constant section, and a two-station
extrusion represents that exactly. The triangles are slivers only in the
sense of having a high aspect ratio: 0.25 mm chordwise by 107 mm spanwise.
Vertices are welded (1106 vertices for 1142 triangles), so dihedral angles
are well defined and `surfaceFeatureExtract` behaves correctly.

### Two duplicate triangles on the endplate outer edge

`surfaceCheck` reports:

```
Surface has 2 illegal triangles.
  triangle 1090 has the same vertices as triangle 1091   (wing-endplate_top)
  triangle 1109 has the same vertices as triangle 1110   (wing-endplate_bottom)
```

Two coincident, oppositely oriented facets — a zero-thickness fin at
x ≈ −139.65 mm, y 103.5…106.5 mm. A defect in the endplate construction in
`wing_generator.py`. Two facets out of 1142; snappyHexMesh tolerates it.
`Allmesh` reports it and carries on deliberately, so that it does not block a
420-case campaign.

### The wheel tread is coarser than the target cell

`wheel_generator.py` uses `n_circ = 180`, i.e. 2° steps. At radius 43.875 mm
that is a **1.53 mm** circumferential facet. The mesh targets 0.293 mm at
level 6 — about five times finer — so the tread is resolved as facets rather
than as a cylinder.

Raising `n_circ` to ~900 would match the mesh. It also invalidates comparison
against anything already computed, so it is a deliberate decision, not a
cleanup.

### "Surface is not closed"

Expected. Both STLs consist of two disjoint parts (wing + endplate, wheel +
plinth), reported as `Number of unconnected parts : 2`. snappyHexMesh does
not need a closed surface here: refinement is driven by intersections and by
distance, and no `mode inside` region is attached to either body.

---

## 2.6 What the repository ships

Only the **baseline** geometry is committed
(`wing_S1.42_h0.13_AOA8.stl` + `wheel_W0.63.stl`, ~8 MB), so the repository
stays small and you can smoke-test without generating anything. Everything
else — all of `output/` — is gitignored and must be generated.

---

Next: [3. Meshing](03_meshing.md)
