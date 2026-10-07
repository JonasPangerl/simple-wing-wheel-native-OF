# ===========================================================================
# fig_results.py - solution figures: Cp, CpT, velocity, y+, Q
#
#   pvbatch --force-offscreen-rendering fig_results.py --case <dir> --out <dir>
#
# The derived fields (Cp, CpT, Q, vorticity, yPlus, wallShearStress) are
# written by the function objects in system/fieldDerived and system/yPlus,
# and only at WRITE TIMES. If the run has not reached one yet, every figure
# is skipped with a message rather than failing.
#
# COLOUR RANGES ARE FIXED, NOT AUTO-SCALED. The raw data on this mesh
# contains isolated extremes far outside the physical range - measured on the
# partly converged baseline: Cp down to -32, CpT up to 100, |U| up to 100 m/s
# against a 10 m/s freestream. Auto-scaling to those spikes makes every
# figure uniformly flat. The ranges below are the physically meaningful ones;
# anything outside saturates, which is exactly what you want to see.
# ===========================================================================

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import (new_view, look_at, save, hide_all, text_label,  # noqa: E402
                       open_foam_case, add_scalar_bar, ground_plane,
                       times_of, WHEEL)
from paraview.simple import *  # noqa: F401,F403,E402

# Near-field box the slices and isosurfaces are clipped to, metres
NEAR = dict(pos=(-0.20, 0.0, 0.0), length=(0.55, 0.165, 0.105))


def patches_matching(reader, prefixes):
    out = []
    for name in reader.MeshRegions.Available:
        if not name.startswith("patch/"):
            continue
        short = name[len("patch/"):]
        if any(short.startswith(p) for p in prefixes):
            out.append(name)
    return out


def clip_near(src, t, name):
    c = Clip(registrationName=name, Input=src)
    c.ClipType = "Box"
    c.Invert = 1
    c.ClipType.Position = list(NEAR["pos"])
    c.ClipType.Length = list(NEAR["length"])
    c.UpdatePipeline(t)
    return c


def colour_by(disp, view, field, assoc, rng, preset, title, fmt="%.2f",
              comp=None):
    if comp is None:
        ColorBy(disp, (assoc, field))
    else:
        ColorBy(disp, (assoc, field, comp))
    lut = GetColorTransferFunction(field)
    lut.ApplyPreset(preset, True)
    lut.RescaleTransferFunction(rng[0], rng[1])
    disp.SetScalarBarVisibility(view, True)
    add_scalar_bar(view, lut, title, fmt=fmt)
    return lut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    r = open_foam_case(args.case, decomposed=True, regions=["internalMesh"])
    avail = list(r.CellArrays.Available)
    print("cell arrays:", avail, flush=True)

    times = times_of(r)
    written = [t for t in times if t > 0.0]
    print("timesteps:", times, flush=True)
    if not written:
        print("no written time beyond 0 yet - nothing to plot")
        return 0
    tlast = max(written)
    print("using time %g" % tlast, flush=True)

    v = new_view(1600, 1000)
    v.ViewTime = tlast
    r.UpdatePipeline(tlast)

    wing_patches = patches_matching(r, ["wing-"])
    wheel_patches = patches_matching(r, ["wheel-"])
    body_patches = wing_patches + wheel_patches

    # ------------------------------------------------------------------
    # Surface fields on wing and wheel
    # ------------------------------------------------------------------
    if body_patches:
        rp = open_foam_case(args.case, decomposed=True, regions=body_patches)
        rp.UpdatePipeline(tlast)

        # --- Cp, suction side (from below) ---------------------------
        if "Cp" in avail:
            hide_all(v)
            d = Show(rp, v)
            d.Representation = "Surface"
            colour_by(d, v, "Cp", "CELLS", (-3.0, 1.0),
                      "Cool to Warm (Extended)", "Cp")
            look_at(v, (-0.048, 0.055, 0.025), (0.35, 0.40, 0.85),
                    (0, 0, 1), 0.075)
            text_label(v, "Cp, seen from below: wing suction side and the "
                          "underside of the wheel")
            save(v, args.out, "res_cp_wing")

            # --- Cp, pressure side (from above) ----------------------
            hide_all(v)
            d = Show(rp, v)
            d.Representation = "Surface"
            colour_by(d, v, "Cp", "CELLS", (-3.0, 1.0),
                      "Cool to Warm (Extended)", "Cp")
            look_at(v, (-0.048, 0.055, 0.025), (0.40, 0.45, -0.80),
                    (0, 0, 1), 0.075)
            text_label(v, "Cp, seen from above: wing pressure side, wheel "
                          "stagnation region")
            save(v, args.out, "res_cp_wing_top")

        # --- y+ ------------------------------------------------------
        if "yPlus" in avail:
            hide_all(v)
            d = Show(rp, v)
            d.Representation = "Surface"
            colour_by(d, v, "yPlus", "CELLS", (0.0, 10.0),
                      "Viridis (matplotlib)", "y+", fmt="%.1f")
            look_at(v, (-0.045, 0.055, 0.028), (0.45, 0.50, -0.74),
                    (0, 0, 1), 0.080)
            text_label(v, "y+ on wing and wheel.  the layer stack targets "
                          "y+ ~ 2.5")
            save(v, args.out, "res_yplus")

        # --- wall shear stress ---------------------------------------
        if "wallShearStress" in avail:
            hide_all(v)
            d = Show(rp, v)
            d.Representation = "Surface"
            colour_by(d, v, "wallShearStress", "CELLS", (0.0, 0.6),
                      "Viridis (matplotlib)", "|tau_w| / rho  [m2/s2]",
                      fmt="%.2f", comp="Magnitude")
            look_at(v, (-0.048, 0.055, 0.025), (0.35, 0.40, 0.85),
                    (0, 0, 1), 0.075)
            text_label(v, "wall shear stress magnitude, suction side.  "
                          "dark bands are separation lines")
            save(v, args.out, "res_tau")

    # ------------------------------------------------------------------
    # CpT on streamwise slices, clipped to the near field
    # ------------------------------------------------------------------
    if "CpT" in avail:
        hide_all(v)
        near = clip_near(r, tlast, "near_cpt")
        xs = [-0.02, 0.02, 0.06, 0.12]
        for i, x in enumerate(xs):
            s = Slice(registrationName="cpt_%d" % i, Input=near)
            s.SliceType = "Plane"
            s.SliceType.Origin = [x, 0, 0]
            s.SliceType.Normal = [1, 0, 0]
            s.Triangulatetheslice = 0
            s.UpdatePipeline(tlast)
            d = Show(s, v)
            d.Representation = "Surface"
            # Total pressure coefficient is ~1 in the freestream with this
            # definition, and drops in wakes and vortex cores.
            # Viridis, not a diverging map: the freestream sits at ~1 and
            # reads as light yellow, losses go dark. A diverging map puts
            # the freestream at one saturated end and hides the structure.
            colour_by(d, v, "CpT", "CELLS", (0.0, 1.05),
                      "Viridis (matplotlib)", "CpT")
            if i < len(xs) - 1:
                d.SetScalarBarVisibility(v, False)
        ground_plane(v, x=(-0.05, 0.16), y=(0.0, 0.18), opacity=0.18)
        look_at(v, (0.045, 0.075, 0.040), (0.80, 0.38, -0.46), (0, 0, 1),
                0.090)
        text_label(v, "CpT on slices at x = -20, 20, 60, 120 mm.  "
                      "low = total pressure loss")
        save(v, args.out, "res_cpt_slice")

    # ------------------------------------------------------------------
    # Velocity magnitude on the wheel-centre plane
    # ------------------------------------------------------------------
    hide_all(v)
    sy = Slice(registrationName="uslice", Input=r)
    sy.SliceType = "Plane"
    sy.SliceType.Origin = [0, WHEEL["y"], 0]
    sy.SliceType.Normal = [0, 1, 0]
    sy.Triangulatetheslice = 0
    sy.UpdatePipeline(tlast)
    d = Show(sy, v)
    d.Representation = "Surface"
    colour_by(d, v, "U", "CELLS", (0.0, 16.0), "Viridis (matplotlib)",
              "|U|  [m/s]", fmt="%.0f", comp="Magnitude")
    look_at(v, (0.02, WHEEL["y"], 0.055), (0, 1, 0), (0, 0, 1), 0.075)
    text_label(v, "|U| on the wheel-centre plane.  freestream 10 m/s; "
                  "anything at the top of the scale is an overshoot")
    save(v, args.out, "res_umag")

    # ------------------------------------------------------------------
    # Q isosurface
    # ------------------------------------------------------------------
    if "Q" in avail:
        hide_all(v)
        near = clip_near(r, tlast, "near_q")
        iso = Contour(registrationName="qiso", Input=near)
        iso.ContourBy = ["POINTS", "Q"]
        # (U/c)^2 = (10/0.075)^2 = 1.8e4 is the scale of the mean shear;
        # vortex cores here sit a few orders above it.
        iso.Isosurfaces = [5.0e6]
        iso.ComputeNormals = 1
        iso.UpdatePipeline(tlast)

        d = Show(iso, v)
        d.Representation = "Surface"
        if "vorticity" in avail:
            colour_by(d, v, "vorticity", "POINTS", (-4000.0, 4000.0),
                      "Cool to Warm (Extended)", "vorticity_x  [1/s]",
                      fmt="%.0f", comp="X")
        else:
            d.DiffuseColor = [0.35, 0.55, 0.85]
        ground_plane(v, x=(-0.16, 0.12), y=(0.0, 0.17), opacity=0.20)
        look_at(v, (-0.01, 0.065, 0.030), (0.60, 0.52, -0.60), (0, 0, 1),
                0.082)
        text_label(v, "Q = 5e6 isosurface, coloured by streamwise vorticity")
        save(v, args.out, "res_q")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
