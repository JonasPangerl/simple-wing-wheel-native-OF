# ===========================================================================
# fig_geometry.py - geometry and domain figures for the report
#
#   pvbatch --force-offscreen-rendering fig_geometry.py \
#       --stl-dir <Diasinos_Geometry_Generator/output> --out <figures>
#
# Needs only the STLs, so it can run before any mesh exists.
# ===========================================================================

import argparse
import gzip
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pv_common import (REGION_COLOURS, DOMAIN,  # noqa: E402
                       new_view, look_at, save, hide_all, text_label,
                       ground_plane, ground_slab, symmetry_plane, legend)
from paraview.simple import *  # noqa: F401,F403,E402


def unpack(path, tmpdir):
    """ParaView's STL reader cannot read .gz; OpenFOAM can. Unpack if needed."""
    if not path.endswith(".gz"):
        return path
    out = os.path.join(tmpdir, os.path.basename(path)[:-3])
    with gzip.open(path, "rb") as fi, open(out, "wb") as fo:
        shutil.copyfileobj(fi, fo)
    return out


def find_stl(stl_dir, sub, stem):
    for cand in (os.path.join(stl_dir, sub, stem),
                 os.path.join(stl_dir, sub, stem + ".gz")):
        if os.path.isfile(cand):
            return cand
    raise SystemExit("ERROR: not found: %s/%s/%s[.gz]" % (stl_dir, sub, stem))


def load_regions(path, tmpdir):
    """One source per STL solid, so each region can get its own colour.

    ParaView's STL reader collapses all solids into one block, so the file is
    split by hand. mm -> m happens here too.
    """
    path = unpack(path, tmpdir)

    blocks, cur = {}, None
    with open(path) as fh:
        for line in fh:
            s = line.strip()
            if s.startswith("solid"):
                cur = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else "solid"
                blocks[cur] = []
            elif s.startswith("endsolid"):
                cur = None
            elif cur is not None:
                blocks[cur].append(line)

    sources = {}
    for name, lines in blocks.items():
        if not lines:
            continue
        frag = os.path.join(tmpdir, name.replace("/", "_") + ".stl")
        with open(frag, "w") as fo:
            fo.write("solid %s\n" % name)
            fo.writelines(lines)
            fo.write("endsolid %s\n" % name)

        rd = STLReader(registrationName="stl_" + name, FileNames=[frag])
        tr = Transform(registrationName="tr_" + name, Input=rd)
        tr.Transform = "Transform"
        tr.Transform.Scale = [0.001, 0.001, 0.001]   # mm -> m
        sources[name] = tr

    return sources


def show_all(sources, view, opacity=1.0, edges=False):
    disp = {}
    for name, src in sources.items():
        d = Show(src, view)
        d.Representation = "Surface With Edges" if edges else "Surface"
        d.DiffuseColor = REGION_COLOURS.get(name, [0.6, 0.6, 0.6])
        d.Opacity = opacity
        d.Specular = 0.15
        if edges:
            d.EdgeColor = [0.1, 0.1, 0.1]
            d.LineWidth = 1.0
        disp[name] = d
    return disp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stl-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--wing", default="wing_S1.42_h0.13_AOA8.stl")
    ap.add_argument("--wheel", default="wheel_W0.63.stl")
    args = ap.parse_args()

    tmpdir = tempfile.mkdtemp(prefix="fig_geom_")
    try:
        wing_src = load_regions(find_stl(args.stl_dir, "wings", args.wing), tmpdir)
        wheel_src = load_regions(find_stl(args.stl_dir, "wheels", args.wheel), tmpdir)
        allsrc = dict(wing_src)
        allsrc.update(wheel_src)
        print("regions: %d wing, %d wheel" % (len(wing_src), len(wheel_src)))

        v = new_view(1500, 950)

        wing_key = [
            ("wing-suction",         REGION_COLOURS["wing-suction"]),
            ("wing-pressure",        REGION_COLOURS["wing-pressure"]),
            ("wing-TE  (blunt, 0.5 mm)", REGION_COLOURS["wing-TE"]),
            ("wing-endplate_inner",  REGION_COLOURS["wing-endplate_inner"]),
            ("wing-endplate_outer",  REGION_COLOURS["wing-endplate_outer"]),
            ("wing-endplate_top",    REGION_COLOURS["wing-endplate_top"]),
            ("wing-endplate_bottom", REGION_COLOURS["wing-endplate_bottom"]),
            ("wing-endplate_LE",     REGION_COLOURS["wing-endplate_LE"]),
            ("wing-endplate_TE",     REGION_COLOURS["wing-endplate_TE"]),
        ]
        wheel_key = [
            ("wheel-tread",     REGION_COLOURS["wheel-tread"]),
            ("wheel-shoulders", REGION_COLOURS["wheel-shoulders"]),
            ("wheel-sidewall",  REGION_COLOURS["wheel-sidewall"]),
            ("wheel-plinth  (cuts the ground)", REGION_COLOURS["wheel-plinth"]),
        ]

        # --- 1. overview, isometric ---------------------------------------
        hide_all(v)
        ground_plane(v)
        show_all(allsrc, v)
        look_at(v, (-0.048, 0.058, 0.030), (0.60, 0.58, -0.55), (0, 0, 1), 0.070)
        legend(v, [("wing + endplate", REGION_COLOURS["wing-suction"]),
                   ("wheel", REGION_COLOURS["wheel-tread"]),
                   ("plinth (cuts the ground)", REGION_COLOURS["wheel-plinth"]),
                   ("ground z = 0, belt at 10 m/s", [0.42, 0.42, 0.45])],
               pos=(0.015, 0.96))
        save(v, args.out, "geom_overview")

        # --- 2. plan view, shows the spanwise overlap ---------------------
        hide_all(v)
        ground_plane(v, opacity=0.18)
        show_all(allsrc, v)
        look_at(v, (-0.048, 0.059, 0.02), (0, 0, -1), (1, 0, 0), 0.062)
        text_label(v, "plan view:  x right-to-left, y up.  y = 0 is the symmetry plane",
                   pos=(0.03, 0.035))
        save(v, args.out, "geom_plan")

        # --- 3. front view, ride height and the endplate-wheel gap -------
        hide_all(v)
        ground_slab(v)
        show_all(allsrc, v)
        look_at(v, (-0.045, 0.055, 0.042), (1, 0, 0), (0, 0, 1), 0.060)
        text_label(v, "front view, looking downstream.  h/c = 0.13, S/c = 1.42, W/c = 0.63",
                   pos=(0.03, 0.035))
        save(v, args.out, "geom_front")

        # --- 4. wing regions, close -------------------------------------
        hide_all(v)
        show_all(wing_src, v)
        look_at(v, (-0.096, 0.052, 0.022), (0.55, 0.65, -0.52), (0, 0, 1), 0.048)
        legend(v, wing_key)
        save(v, args.out, "geom_wing_regions")

        # --- 5. wheel regions, close ------------------------------------
        hide_all(v)
        ground_plane(v, x=(-0.06, 0.06), y=(0.06, 0.13), opacity=0.30)
        show_all(wheel_src, v)
        look_at(v, (0.0, 0.096, 0.040), (0.55, 0.62, -0.50), (0, 0, 1), 0.040)
        legend(v, wheel_key)
        save(v, args.out, "geom_wheel_regions")

        # --- 6. domain -----------------------------------------------------
        hide_all(v)
        box = Box(registrationName="domain")
        box.XLength = DOMAIN["xmax"] - DOMAIN["xmin"]
        box.YLength = DOMAIN["ymax"] - DOMAIN["ymin"]
        box.ZLength = DOMAIN["zmax"] - DOMAIN["zmin"]
        box.Center = [0.5 * (DOMAIN["xmin"] + DOMAIN["xmax"]),
                      0.5 * (DOMAIN["ymin"] + DOMAIN["ymax"]),
                      0.5 * (DOMAIN["zmin"] + DOMAIN["zmax"])]
        bd = Show(box, v)
        bd.Representation = "Outline"
        bd.AmbientColor = [0.1, 0.1, 0.1]
        bd.LineWidth = 2.0
        ground_plane(v, x=(DOMAIN["xmin"], DOMAIN["xmax"]),
                     y=(DOMAIN["ymin"], DOMAIN["ymax"]), opacity=0.25)
        symmetry_plane(v, x=(DOMAIN["xmin"], DOMAIN["xmax"]),
                       z=(0.0, DOMAIN["zmax"]), opacity=0.14)
        show_all(allsrc, v)
        look_at(v, (0.15, 0.30, 0.22), (0.55, 0.62, -0.42), (0, 0, 1), 0.78)
        text_label(v, "domain 1.894 x 0.675 x 0.638 m  =  25.3c x 9c x 8.5c")
        text_label(v, "grey = ground (moving wall)   yellow = symmetry plane y=0",
                   pos=(0.02, 0.905))
        save(v, args.out, "geom_domain")

        print("done")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
