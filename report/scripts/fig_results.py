# ===========================================================================
# fig_results.py - solution figures: Cp, CpT, y+, Q
#
#   pvbatch --force-offscreen-rendering fig_results.py --case <dir> --out <dir>
#
# The derived fields (Cp, CpT, Q, vorticity, yPlus, wallShearStress) are
# written by the function objects in system/fieldDerived and system/yPlus,
# and only at WRITE TIMES. If the run has not reached one yet, the
# corresponding figure is skipped with a message rather than failing.
# ===========================================================================

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import (new_view, look_at, save, hide_all, text_label,  # noqa: E402
                       open_foam_case, add_scalar_bar, ground_plane,
                       WHEEL)
from paraview.simple import *  # noqa: F401,F403,E402


def patches_matching(reader, prefixes):
    """Available mesh regions whose patch name starts with one of prefixes."""
    out = []
    for name in reader.MeshRegions.Available:
        if not name.startswith("patch/"):
            continue
        short = name[len("patch/"):]
        if any(short.startswith(p) for p in prefixes):
            out.append(name)
    return out


def colour_by(disp, view, field, assoc, rng, preset, title, fmt="%.2f"):
    ColorBy(disp, (assoc, field))
    lut = GetColorTransferFunction(field)
    lut.ApplyPreset(preset, True)
    if rng is not None:
        lut.RescaleTransferFunction(rng[0], rng[1])
    else:
        disp.RescaleTransferFunctionToDataRange(True, False)
    disp.SetScalarBarVisibility(view, True)
    add_scalar_bar(view, lut, title, fmt=fmt)
    return lut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    # Open with every patch, so surface fields can be drawn
    r = open_foam_case(args.case, decomposed=True, regions=["internalMesh"])
    avail_regions = list(r.MeshRegions.Available)
    avail_cells = list(r.CellArrays.Available)
    print("cell arrays:", avail_cells, flush=True)

    times = r.TimestepValues
    print("timesteps:", times, flush=True)
    if not times:
        print("no written time yet - nothing to plot")
        return 0
    tlast = max(times) if isinstance(times, (list, tuple)) else float(times)

    v = new_view(1600, 1000)
    scene = GetAnimationScene()
    scene.UpdateAnimationUsingDataTimeSteps()
    v.ViewTime = tlast
    print("using time %g" % tlast, flush=True)

    wing_patches = patches_matching(r, ["wing-"])
    wheel_patches = patches_matching(r, ["wheel-"])

    # ------------------------------------------------------------------
    # 1. Cp on the wing, seen from below (suction side)
    # ------------------------------------------------------------------
    if "Cp" in avail_cells and wing_patches:
        rp = open_foam_case(args.case, decomposed=True,
                            regions=wing_patches + wheel_patches)
        rp.UpdatePipeline(tlast)
        hide_all(v)
        d = Show(rp, v)
        d.Representation = "Surface"
        colour_by(d, v, "Cp", "CELLS", (-3.0, 1.0),
                  "Cool to Warm (Extended)", "Cp")
        look_at(v, (-0.055, 0.055, 0.020), (0.45, 0.50, 0.74), (0, 0, 1), 0.075)
        text_label(v, "Cp, view from below-upstream (suction side)")
        save(v, args.out, "res_cp_wing")

        # y+ on the same surfaces
        if "yPlus" in avail_cells:
            hide_all(v)
            d = Show(rp, v)
            d.Representation = "Surface"
            colour_by(d, v, "yPlus", "CELLS", (0.0, 10.0),
                      "Viridis (matplotlib)", "y+", fmt="%.1f")
            look_at(v, (-0.045, 0.058, 0.030), (0.50, 0.55, -0.67), (0, 0, 1),
                    0.072)
            text_label(v, "y+ on wing and wheel.  layer stack targets y+ ~ 2.5")
            save(v, args.out, "res_yplus")
    else:
        print("Cp or wing patches unavailable - skipping surface figures")

    # ------------------------------------------------------------------
    # 2. CpT on streamwise slices
    # ------------------------------------------------------------------
    if "CpT" in avail_cells:
        hide_all(v)
        xs = [-0.02, 0.02, 0.06, 0.12]
        for i, x in enumerate(xs):
            s = Slice(registrationName="cpt_%d" % i, Input=r)
            s.SliceType = "Plane"
            s.SliceType.Origin = [x, 0, 0]
            s.SliceType.Normal = [1, 0, 0]
            s.Triangulatetheslice = 0
            s.UpdatePipeline(tlast)
            d = Show(s, v)
            d.Representation = "Surface"
            lut = colour_by(d, v, "CpT", "CELLS", (-1.0, 0.6),
                            "Cool to Warm (Extended)", "CpT")
            if i < len(xs) - 1:
                d.SetScalarBarVisibility(v, False)
        look_at(v, (0.05, 0.06, 0.035), (0.72, 0.42, -0.55), (0, 0, 1), 0.085)
        text_label(v, "CpT on slices at x = -20, 20, 60, 120 mm")
        save(v, args.out, "res_cpt_slice")
    else:
        print("CpT unavailable - skipping slice figure")

    # ------------------------------------------------------------------
    # 3. Q isosurface, coloured by streamwise vorticity
    # ------------------------------------------------------------------
    if "Q" in avail_cells:
        hide_all(v)
        clip = Clip(registrationName="qbox", Input=r)
        clip.ClipType = "Box"
        clip.Invert = 1
        clip.ClipType.Position = [-0.16, 0.0, 0.0]
        clip.ClipType.Length = [0.36, 0.16, 0.12]
        clip.UpdatePipeline(tlast)

        iso = Contour(registrationName="qiso", Input=clip)
        iso.ContourBy = ["POINTS", "Q"]
        iso.Isosurfaces = [2.0e5]
        iso.ComputeNormals = 1
        iso.UpdatePipeline(tlast)

        d = Show(iso, v)
        d.Representation = "Surface"
        if "vorticity" in avail_cells:
            ColorBy(d, ("POINTS", "vorticity", "X"))
            lut = GetColorTransferFunction("vorticity")
            lut.ApplyPreset("Cool to Warm (Extended)", True)
            lut.RescaleTransferFunction(-4000.0, 4000.0)
            d.SetScalarBarVisibility(v, True)
            add_scalar_bar(v, lut, "vorticity_x [1/s]", fmt="%.0f")
        else:
            d.DiffuseColor = [0.35, 0.55, 0.85]

        ground_plane(v, opacity=0.20)
        look_at(v, (-0.02, 0.06, 0.028), (0.60, 0.55, -0.58), (0, 0, 1), 0.085)
        text_label(v, "Q = 2e5 isosurface, coloured by streamwise vorticity")
        save(v, args.out, "res_q")
    else:
        print("Q unavailable - skipping isosurface figure")

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
