# ===========================================================================
# fig_mesh.py - mesh figures: refinement, slices, and layer close-ups
#
#   pvbatch --force-offscreen-rendering fig_mesh.py --case <dir> --out <dir>
#
# Reads the DECOMPOSED case, so no reconstructPar is needed.
# ===========================================================================

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import (new_view, look_at, save, hide_all, text_label,  # noqa: E402
                       open_foam_case, add_scalar_bar, WHEEL, DOMAIN)
from paraview.simple import *  # noqa: F401,F403,E402

# Spanwise station through the middle of the wheel, and the wheel axis plane
Y_WHEEL = WHEEL["y"]
X_AXIS = 0.0


def mesh_slice(reader, origin, normal, name):
    s = Slice(registrationName=name, Input=reader)
    s.SliceType = "Plane"
    s.SliceType.Origin = list(origin)
    s.SliceType.Normal = list(normal)
    s.Triangulatetheslice = 0          # keep the cut faces as polygons
    s.UpdatePipeline()
    return s


def show_mesh(src, view, fill=(0.88, 0.90, 0.93), edge=(0.10, 0.12, 0.15),
              lw=1.0):
    d = Show(src, view)
    d.Representation = "Surface With Edges"
    d.DiffuseColor = list(fill)
    d.EdgeColor = list(edge)
    d.LineWidth = lw
    d.Specular = 0.0
    ColorBy(d, None)
    return d


def show_patch_field(src, view, field, rng, title, preset="Viridis (matplotlib)"):
    d = Show(src, view)
    d.Representation = "Surface"
    ColorBy(d, ("CELLS", field))
    lut = GetColorTransferFunction(field)
    lut.ApplyPreset(preset, True)
    lut.RescaleTransferFunction(rng[0], rng[1])
    d.SetScalarBarVisibility(view, True)
    add_scalar_bar(view, lut, title, fmt="%.3g")
    return d, lut


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    print("opening case (decomposed) ...", flush=True)
    r = open_foam_case(args.case, decomposed=True, regions=["internalMesh"])
    print("  available cell arrays:", list(r.CellArrays.Available), flush=True)

    v = new_view(1600, 1000)

    # =====================================================================
    # 1. Refinement overview: spanwise slice through the wheel centre
    # =====================================================================
    print("slice y = %.6f (wheel centre)" % Y_WHEEL, flush=True)
    sy = mesh_slice(r, (0, Y_WHEEL, 0), (0, 1, 0), "slice_y")

    hide_all(v)
    show_mesh(sy, v, lw=0.4)
    # Looking along -y, so x to the right and z up
    look_at(v, (-0.02, Y_WHEEL, 0.045), (0, 1, 0), (0, 0, 1), 0.105)
    text_label(v, "mesh, spanwise slice through the wheel centre (y = 96.4 mm)")
    save(v, args.out, "mesh_slice_y_overview")

    # Zoom: the wing-wheel gap region
    hide_all(v)
    show_mesh(sy, v, lw=0.7)
    look_at(v, (-0.055, Y_WHEEL, 0.022), (0, 1, 0), (0, 0, 1), 0.030)
    text_label(v, "wing trailing edge to wheel front, same slice")
    save(v, args.out, "mesh_slice_y_gap")

    # =====================================================================
    # 2. Wheel layers: close-ups on the same slice
    # =====================================================================
    # Top of the tread, where layers should be cleanest
    hide_all(v)
    show_mesh(sy, v, lw=1.1)
    look_at(v, (0.0, Y_WHEEL, WHEEL["z"] + WHEEL["r"]), (0, 1, 0), (0, 0, 1),
            0.0045)
    text_label(v, "wheel tread, top.  4 layers requested, first 0.14 mm")
    save(v, args.out, "mesh_layers_tread")

    # Front of the tread, stagnation side
    hide_all(v)
    show_mesh(sy, v, lw=1.1)
    look_at(v, (-WHEEL["r"], Y_WHEEL, WHEEL["z"]), (0, 1, 0), (0, 0, 1), 0.0045)
    text_label(v, "wheel tread, upstream face")
    save(v, args.out, "mesh_layers_tread_front")

    # Contact patch
    hide_all(v)
    show_mesh(sy, v, lw=1.1)
    look_at(v, (0.0, Y_WHEEL, 0.002), (0, 1, 0), (0, 0, 1), 0.006)
    text_label(v, "contact patch.  plinth cuts the ground at z = 0")
    save(v, args.out, "mesh_layers_contact")

    # =====================================================================
    # 3. Wheel shoulder: slice through the wheel axis (x = 0)
    # =====================================================================
    print("slice x = 0 (wheel axis)", flush=True)
    sx = mesh_slice(r, (X_AXIS, 0, 0), (1, 0, 0), "slice_x")

    hide_all(v)
    show_mesh(sx, v, lw=0.5)
    # Looking along +x: image-right is -y, so y grows to the left
    look_at(v, (X_AXIS, 0.075, 0.045), (1, 0, 0), (0, 0, 1), 0.065)
    text_label(v, "mesh, x = 0 through the wheel axis")
    save(v, args.out, "mesh_slice_x_overview")

    hide_all(v)
    show_mesh(sx, v, lw=1.1)
    look_at(v, (X_AXIS, WHEEL["ymin"] + 0.004, WHEEL["z"] + WHEEL["r"] - 0.004),
            (1, 0, 0), (0, 0, 1), 0.008)
    text_label(v, "wheel shoulder, inboard.  R_shoulder = 5.0 mm")
    save(v, args.out, "mesh_layers_shoulder")

    # =====================================================================
    # 4. Wing trailing edge, the blunt 0.5 mm one
    # =====================================================================
    print("slice y = 0.05 (wing mid-span)", flush=True)
    sw = mesh_slice(r, (0, 0.05, 0), (0, 1, 0), "slice_wing")

    hide_all(v)
    show_mesh(sw, v, lw=0.6)
    look_at(v, (-0.098, 0.05, 0.022), (0, 1, 0), (0, 0, 1), 0.030)
    text_label(v, "wing section at y = 50 mm, inverted NACA 4412")
    save(v, args.out, "mesh_wing_section")

    hide_all(v)
    show_mesh(sw, v, lw=1.2)
    look_at(v, (-0.0516, 0.05, 0.0145), (0, 1, 0), (0, 0, 1), 0.0035)
    text_label(v, "blunt trailing edge, 0.5 mm.  no prism layers here")
    save(v, args.out, "mesh_wing_te")

    # =====================================================================
    # 5. Ground plane mesh, z-normal slice just above the belt
    # =====================================================================
    print("slice z = 0.001", flush=True)
    sz = mesh_slice(r, (0, 0, 0.0012), (0, 0, 1), "slice_z")

    hide_all(v)
    show_mesh(sz, v, lw=0.4)
    look_at(v, (-0.04, 0.06, 0.0012), (0, 0, -1), (1, 0, 0), 0.085)
    text_label(v, "mesh 1.2 mm above the ground, plan view")
    save(v, args.out, "mesh_slice_z")

    print("done")


if __name__ == "__main__":
    main()
