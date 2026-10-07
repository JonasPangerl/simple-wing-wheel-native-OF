# ===========================================================================
# pv_common.py - shared helpers for the report figure scripts
#
# Run under pvbatch (ParaView's Python 3.10), never under the system python.
#
#   pvbatch --force-offscreen-rendering fig_geometry.py --case <dir> --out <dir>
# ===========================================================================

import os
from paraview.simple import *  # noqa: F401,F403

# --- geometry landmarks, metres --------------------------------------------
# Baseline case S1.42_h0.13_AOA8_W0.63. Used to aim the cameras.
CHORD = 0.075

DOMAIN = dict(xmin=-0.7125, xmax=1.18125,
              ymin=0.0,     ymax=0.675,
              zmin=0.0,     zmax=0.6375)

WHEEL = dict(x=0.0, y=0.096375, z=0.043875, r=0.043875,
             ymin=0.07275, ymax=0.120)

WING = dict(xmin=-0.14115, xmax=-0.0504,
            ymin=-0.002,   ymax=0.1065,
            zmin=0.00675,  zmax=0.037725)

# --- STL region colours ----------------------------------------------------
# One hue family per component so the two bodies read apart at a glance.
REGION_COLOURS = {
    # wing: blues
    "wing-suction":         [0.16, 0.44, 0.75],
    "wing-pressure":        [0.40, 0.72, 0.95],
    "wing-TE":              [0.95, 0.35, 0.20],   # highlight: the blunt TE
    "wing-endplate_inner":  [0.30, 0.55, 0.62],
    "wing-endplate_outer":  [0.45, 0.70, 0.76],
    "wing-endplate_top":    [0.36, 0.58, 0.66],
    "wing-endplate_bottom": [0.18, 0.38, 0.45],
    "wing-endplate_LE":     [0.28, 0.70, 0.80],
    "wing-endplate_TE":     [0.99, 0.60, 0.35],   # highlight
    # wheel: warm greys and greens
    "wheel-tread":          [0.35, 0.60, 0.35],
    "wheel-shoulders":      [0.62, 0.80, 0.38],
    "wheel-sidewall":       [0.48, 0.66, 0.40],
    "wheel-plinth":         [0.85, 0.45, 0.60],   # highlight: contact patch
}

BG = [1.0, 1.0, 1.0]


def new_view(width=1600, height=1000, parallel=True):
    v = GetActiveViewOrCreate("RenderView")
    v.ViewSize = [width, height]
    v.UseColorPaletteForBackground = 0
    v.Background = BG
    v.OrientationAxesVisibility = 1
    v.OrientationAxesLabelColor = [0.1, 0.1, 0.1]
    v.CameraParallelProjection = 1 if parallel else 0
    return v


def look_at(view, focal, direction, up, scale):
    """Aim a parallel-projection camera.

    focal     point to look at
    direction unit vector the camera looks ALONG
    up        view-up vector
    scale     half-height of the visible region, in metres
    """
    d = 10.0 * max(scale, 1e-3)
    view.CameraFocalPoint = list(focal)
    view.CameraPosition = [focal[i] - direction[i] * d for i in range(3)]
    view.CameraViewUp = list(up)
    view.CameraParallelScale = scale
    Render(view)


def save(view, out_dir, name, width=None, height=None):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".png")
    res = [width or view.ViewSize[0], height or view.ViewSize[1]]
    SaveScreenshot(path, view, ImageResolution=res,
                   TransparentBackground=0)
    print("  wrote %s" % path, flush=True)
    return path


def hide_all(view):
    for src in GetSources().values():
        try:
            Hide(src, view)
        except Exception:
            pass


def add_scalar_bar(view, lut, title, fmt="%.2f"):
    bar = GetScalarBar(lut, view)
    bar.Title = title
    bar.ComponentTitle = ""
    bar.TitleColor = [0, 0, 0]
    bar.LabelColor = [0, 0, 0]
    bar.TitleFontSize = 18
    bar.LabelFontSize = 15
    bar.RangeLabelFormat = fmt
    bar.LabelFormat = fmt
    bar.ScalarBarLength = 0.33
    bar.ScalarBarThickness = 14
    bar.Orientation = "Vertical"
    bar.WindowLocation = "Lower Right Corner"
    return bar


def text_label(view, text, pos=(0.02, 0.94), size=16):
    t = Text(registrationName="lbl_" + text[:12])
    t.Text = text
    d = Show(t, view)
    d.Color = [0, 0, 0]
    d.FontSize = size
    d.WindowLocation = "Any Location"
    d.Position = list(pos)
    return t, d


def ground_plane(view, x=(-0.17, 0.075), y=(0.0, 0.135), opacity=0.35):
    """A grey plane at z = 0, so the reader can see what 'ground effect' means.

    Without it the wheel and wing appear to float and the ride height is
    impossible to judge.
    """
    p = Plane(registrationName="ground_ref")
    p.Origin = [x[0], y[0], 0.0]
    p.Point1 = [x[1], y[0], 0.0]
    p.Point2 = [x[0], y[1], 0.0]
    p.XResolution = 1
    p.YResolution = 1
    d = Show(p, view)
    d.Representation = "Surface"
    d.DiffuseColor = [0.55, 0.55, 0.58]
    d.Opacity = opacity
    d.Specular = 0.0
    return p, d


def ground_slab(view, x=(-0.17, 0.075), y=(-0.005, 0.135), t=0.0012):
    """A thin ground slab, for views that look along the ground plane.

    A zero-thickness Plane seen edge-on renders as nothing useful, so the
    front and side views need an object with thickness instead.
    """
    b = Box(registrationName="ground_slab")
    b.XLength = x[1] - x[0]
    b.YLength = y[1] - y[0]
    b.ZLength = t
    b.Center = [0.5 * (x[0] + x[1]), 0.5 * (y[0] + y[1]), -0.5 * t]
    d = Show(b, view)
    d.Representation = "Surface"
    d.DiffuseColor = [0.40, 0.40, 0.43]
    d.Specular = 0.0
    return b, d


def symmetry_plane(view, x=(-0.20, 0.15), z=(0.0, 0.07), opacity=0.18):
    """A plane at y = 0, marking the half-model symmetry boundary."""
    p = Plane(registrationName="symm_ref")
    p.Origin = [x[0], 0.0, z[0]]
    p.Point1 = [x[1], 0.0, z[0]]
    p.Point2 = [x[0], 0.0, z[1]]
    d = Show(p, view)
    d.Representation = "Surface"
    d.DiffuseColor = [0.85, 0.75, 0.35]
    d.Opacity = opacity
    d.Specular = 0.0
    return p, d


def legend(view, entries, pos=(0.015, 0.97), dy=0.026, size=14):
    """Colour legend built from stacked Text sources.

    ParaView has no categorical legend across several sources, and these
    figures deliberately use one source per STL region so each can be
    coloured separately. Writing the key by hand is the simple way out.

    entries: list of (label, rgb)
    """
    out = []
    for i, (label, rgb) in enumerate(entries):
        t = Text(registrationName="leg_%d_%s" % (i, label[:10]))
        t.Text = label
        d = Show(t, view)
        d.Color = rgb
        d.FontSize = size
        d.WindowLocation = "Any Location"
        d.Position = [pos[0], pos[1] - i * dy]
        out.append((t, d))
    return out


def open_foam_case(case_dir, decomposed=True, regions=("internalMesh",),
                   cell_arrays=None):
    """Open <case>/case.foam.

    Reading the DECOMPOSED case avoids reconstructPar, which for a 20 M cell
    mesh writes tens of GB just to make a picture.
    """
    foam = os.path.join(case_dir, "case.foam")
    if not os.path.isfile(foam):
        open(foam, "a").close()

    r = OpenFOAMReader(registrationName="case", FileName=foam)
    r.CaseType = "Decomposed Case" if decomposed else "Reconstructed Case"
    r.MeshRegions = list(regions)
    if cell_arrays is not None:
        r.CellArrays = list(cell_arrays)
    r.Createcelltopointfiltereddata = 1
    r.UpdatePipeline()
    return r


def available(reader):
    """Print what the reader offers - patch names and fields."""
    print("MeshRegions:")
    for n in reader.MeshRegions.Available:
        print("   ", n)
    print("CellArrays:")
    for n in reader.CellArrays.Available:
        print("   ", n)


def latest_time(reader):
    ts = reader.TimestepValues
    if not ts:
        return 0.0
    try:
        return max(ts)
    except TypeError:
        return float(ts)
