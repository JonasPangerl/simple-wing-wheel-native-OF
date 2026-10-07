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

# Taken from the STL, not estimated: region centroids of the baseline wing.
WING_TE = (-0.063223, 0.024329)        # (x, z) of the blunt trailing edge
WING_LE_X = -0.136397
WING_SECTION_Z = (0.009750, 0.024580)


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
    # Disable scalar colouring. ColorBy(d, None) is rejected by ParaView
    # 5.13 ("invalid association string NONE"); setting ColorArrayName
    # directly is the way that works.
    d.ColorArrayName = [None, '']
    d.SetScalarBarVisibility(view, False)
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
    look_at(v, (0.0, Y_WHEEL, 0.072), (0, 1, 0), (0, 0, 1), 0.080)
    text_label(v, "mesh, spanwise slice through the wheel centre (y = 96.4 mm)")
    save(v, args.out, "mesh_slice_y_overview")

    # Zoom: the wing-wheel gap region
    hide_all(v)
    show_mesh(sy, v, lw=0.7)
    look_at(v, (-0.052, Y_WHEEL, 0.026), (0, 1, 0), (0, 0, 1), 0.026)
    text_label(v, "wing trailing edge to wheel front, same slice")
    save(v, args.out, "mesh_slice_y_gap")

    # =====================================================================
    # 2. Wheel layers: close-ups on the same slice
    # =====================================================================
    # Top of the tread, where layers should be cleanest
    hide_all(v)
    show_mesh(sy, v, lw=1.1)
    # Offset the focal point into the fluid: everything below the tread is
    # solid wheel and renders as empty white.
    look_at(v, (0.0, Y_WHEEL, WHEEL["z"] + WHEEL["r"] + 0.0021),
            (0, 1, 0), (0, 0, 1), 0.0035)
    text_label(v, "wheel tread, top.  7 mm tall view.  "
                  "4 layers requested, 3.6 built, 63 % of the asked thickness")
    save(v, args.out, "mesh_layers_tread")

    # Front of the tread, stagnation side
    hide_all(v)
    show_mesh(sy, v, lw=1.1)
    look_at(v, (-WHEEL["r"] - 0.0021, Y_WHEEL, WHEEL["z"]),
            (0, 1, 0), (0, 0, 1), 0.0035)
    text_label(v, "wheel tread, upstream face.  7 mm tall view")
    save(v, args.out, "mesh_layers_tread_front")

    # Contact patch
    hide_all(v)
    show_mesh(sy, v, lw=1.1)
    # Zoomed out: the centre of the contact region is solid plinth, so a
    # tight view there is mostly empty.
    # One side only: at the wheel centre the whole region |x| < 18 mm is
    # solid plinth and wheel, so a symmetric view is half empty.
    look_at(v, (-0.014, Y_WHEEL, 0.0035), (0, 1, 0), (0, 0, 1), 0.007)
    text_label(v, "contact patch, upstream side, 14 mm tall view.  the gap "
                  "closes onto the plinth, which has no layers")
    save(v, args.out, "mesh_layers_contact")

    # =====================================================================
    # 3. Wheel shoulder: slice through the wheel axis (x = 0)
    # =====================================================================
    print("slice x = 0 (wheel axis)", flush=True)
    sx = mesh_slice(r, (X_AXIS, 0, 0), (1, 0, 0), "slice_x")

    hide_all(v)
    show_mesh(sx, v, lw=0.5)
    # Looking along +x: image-right is -y, so y grows to the left
    look_at(v, (X_AXIS, 0.066, 0.046), (1, 0, 0), (0, 0, 1), 0.068)
    text_label(v, "mesh, x = 0 through the wheel axis")
    save(v, args.out, "mesh_slice_x_overview")

    hide_all(v)
    show_mesh(sx, v, lw=1.1)
    look_at(v, (X_AXIS, WHEEL["ymin"] + 0.004, WHEEL["z"] + WHEEL["r"] - 0.004),
            (1, 0, 0), (0, 0, 1), 0.008)
    text_label(v, "wheel shoulder, inboard.  R_shoulder = 5.0 mm")
    save(v, args.out, "mesh_layers_shoulder")

    # =====================================================================
    # 3b. Streamwise stations through the wing - the endplate vortex region
    # =====================================================================
    # x = -95 mm cuts the wing and the full endplate; x = -48 mm sits just
    # behind the endplate trailing edge (-50.4 mm), where the bottom-edge
    # vortex is shed. These are the views that show whether the distance
    # refinement on the shedding edge is doing its job.
    for xst, tag, note in (
        (-0.095, "wing_mid", "x = -95 mm, through the wing and endplate"),
        (-0.048, "ep_wake", "x = -48 mm, just behind the endplate trailing "
                            "edge - the vortex is shed here"),
    ):
        s = mesh_slice(r, (xst, 0, 0), (1, 0, 0), "slice_x_%s" % tag)
        hide_all(v)
        show_mesh(s, v, lw=0.6)
        look_at(v, (xst, 0.062, 0.028), (1, 0, 0), (0, 0, 1), 0.032)
        text_label(v, "mesh, %s.  looking downstream, y grows to the left"
                   % note)
        save(v, args.out, "mesh_slice_x_" + tag)

    # =====================================================================
    # 4. Wing trailing edge, the blunt 0.5 mm one
    # =====================================================================
    print("slice y = 0.05 (wing mid-span)", flush=True)
    sw = mesh_slice(r, (0, 0.05, 0), (0, 1, 0), "slice_wing")

    hide_all(v)
    show_mesh(sw, v, lw=0.6)
    look_at(v, (0.5 * (WING_LE_X + WING_TE[0]), 0.05,
                0.5 * (WING_SECTION_Z[0] + WING_SECTION_Z[1])),
            (0, 1, 0), (0, 0, 1), 0.028)
    text_label(v, "wing section at y = 50 mm, inverted NACA 4412.  "
                  "suction side is the lower one")
    save(v, args.out, "mesh_wing_section")

    hide_all(v)
    show_mesh(sw, v, lw=1.2)
    look_at(v, (WING_TE[0] + 0.0010, 0.05, WING_TE[1]),
            (0, 1, 0), (0, 0, 1), 0.0022)
    text_label(v, "blunt trailing edge, 0.5 mm thick, 4.4 mm tall view.  "
                  "no prism layers here")
    save(v, args.out, "mesh_wing_te")

    # =====================================================================
    # 5. Ground plane mesh, z-normal slice just above the belt
    # =====================================================================
    print("slice z = 0.001", flush=True)
    sz = mesh_slice(r, (0, 0, 0.0012), (0, 0, 1), "slice_z")

    hide_all(v)
    show_mesh(sz, v, lw=0.4)
    look_at(v, (-0.030, 0.062, 0.0012), (0, 0, -1), (1, 0, 0), 0.072)
    text_label(v, "mesh 1.2 mm above the ground, plan view")
    save(v, args.out, "mesh_slice_z")

    print("done")


if __name__ == "__main__":
    main()
