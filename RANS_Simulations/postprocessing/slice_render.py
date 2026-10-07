#!/usr/bin/env pvbatch
# ============================================================================
# slice_render.py - batch slice rendering for the wing/wheel RANS campaign
#
# Renders evenly spaced slices in any combination of x/y/z, one PNG per
# (direction, position, field), with fixed colour limits so images are directly
# comparable across cases.
#
# Run with pvbatch (see run_slices.sh for the cluster module setup):
#   pvbatch slice_render.py --case <caseDir> [options]
#
# All coordinates are in metres, matching the solver mesh.
# ============================================================================

import argparse
import os
import re
import sys

# ----------------------------------------------------------------------------
# Config loading.
#
# ParaView ships its own Python which frequently has no PyYAML. Rather than
# make the whole pipeline depend on a module that may not exist on the cluster,
# fall back to a small parser that handles the subset of YAML used by
# slices.yaml (nested maps, lists of scalars, lists of maps, comments).
# ----------------------------------------------------------------------------

def _coerce(text):
    """Convert a YAML scalar to a Python value."""
    t = text.strip()
    if t == "" or t == "null" or t == "~":
        return None
    if t.lower() in ("true", "yes"):
        return True
    if t.lower() in ("false", "no"):
        return False
    # Inline list, e.g. [-0.005, 0.18] or [CpT, Cp]
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        if not inner:
            return []
        return [_coerce(p) for p in inner.split(",")]
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        return t[1:-1]
    try:
        if re.match(r"^[+-]?\d+$", t):
            return int(t)
        return float(t)
    except ValueError:
        return t


def _strip_comment(line):
    """Remove a trailing comment, respecting quotes."""
    out = []
    quote = None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
            out.append(ch)
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def _tokenize(text):
    """Return [(indent, body)] for all significant lines."""
    out = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        out.append((len(line) - len(line.lstrip()), line.strip()))
    return out


def _parse_block(toks, i, indent):
    """Recursive descent over the indentation-based subset of YAML used by
    slices.yaml. Returns (value, next_index). Lookahead on the first line of a
    block decides whether it is a sequence or a mapping, which avoids the
    ambiguity that a single-pass stack parser cannot resolve."""
    if i >= len(toks):
        return None, i

    if toks[i][1].startswith("- "):
        seq = []
        while i < len(toks) and toks[i][0] == indent and toks[i][1].startswith("- "):
            item = toks[i][1][2:].strip()
            i += 1
            if ":" in item and not item.startswith("["):
                # List of maps: the inline pair is the map's first entry, and
                # any deeper-indented lines that follow belong to it too.
                key, _, val = item.partition(":")
                entry = {key.strip(): _coerce(val)}
                if i < len(toks) and toks[i][0] > indent and not toks[i][1].startswith("- "):
                    nested, i = _parse_block(toks, i, toks[i][0])
                    if isinstance(nested, dict):
                        entry.update(nested)
                seq.append(entry)
            else:
                seq.append(_coerce(item))
        return seq, i

    mapping = {}
    while i < len(toks) and toks[i][0] == indent:
        body = toks[i][1]
        if ":" not in body:
            i += 1
            continue
        key, _, value = body.partition(":")
        key = key.strip()
        value = value.strip()
        i += 1
        if value == "":
            if i < len(toks) and toks[i][0] > indent:
                mapping[key], i = _parse_block(toks, i, toks[i][0])
            else:
                mapping[key] = None
        else:
            mapping[key] = _coerce(value)
    return mapping, i


def _parse_simple_yaml(text):
    toks = _tokenize(text)
    if not toks:
        return {}
    value, _ = _parse_block(toks, 0, toks[0][0])
    return value


def load_config(path):
    with open(path, "r") as fh:
        text = fh.read()
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        sys.stderr.write(
            "[info] PyYAML not available in this ParaView build; "
            "using built-in fallback parser.\n")
        return _parse_simple_yaml(text)


# ----------------------------------------------------------------------------
# Geometry helpers
# ----------------------------------------------------------------------------

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
NORMALS = {"x": [1.0, 0.0, 0.0], "y": [0.0, 1.0, 0.0], "z": [0.0, 0.0, 1.0]}

# For each slice normal: which axis is horizontal and which is vertical in the
# resulting image. Must match the camera_dir/view_up pairs in slices.yaml.
IN_PLANE = {"x": ("y", "z"), "y": ("x", "z"), "z": ("x", "y")}


def slice_positions(spacing, start, end):
    """Inclusive positions from start to end. Built by integer multiplication
    rather than repeated addition so that floating-point error cannot drift and
    so a case with a different range still lands on identical coordinates."""
    if spacing <= 0:
        raise ValueError("spacing must be > 0")
    n = int(round((end - start) / spacing))
    return [start + i * spacing for i in range(n + 1)]


def fit_frame(frame_h, frame_v, res_w, res_h):
    """Return (centre_h, centre_v, parallel_scale) for a parallel projection
    that shows at least the requested frame at the fixed image aspect ratio.

    ParaView's ParallelScale is the HALF-HEIGHT of the viewport in world units.
    The frame is expanded, never cropped: if the frame is proportionally wider
    than the image, the visible height grows to compensate. Every image
    therefore uses the same scale for a given direction, which keeps features
    comparable between slices."""
    h_lo, h_hi = float(frame_h[0]), float(frame_h[1])
    v_lo, v_hi = float(frame_v[0]), float(frame_v[1])
    width = h_hi - h_lo
    height = v_hi - v_lo
    if width <= 0 or height <= 0:
        raise ValueError("frame must have positive extent: h=%r v=%r"
                         % (frame_h, frame_v))

    img_aspect = float(res_w) / float(res_h)
    frame_aspect = width / height

    if frame_aspect > img_aspect:
        # Frame is wider than the image: height must grow.
        half_height = (width / img_aspect) / 2.0
    else:
        half_height = height / 2.0

    return (h_lo + width / 2.0, v_lo + height / 2.0, half_height)


# ----------------------------------------------------------------------------
# ParaView pipeline
# ----------------------------------------------------------------------------

def find_foam_file(case_dir):
    """Locate the .foam entry point, creating one if absent."""
    for name in sorted(os.listdir(case_dir)):
        if name.endswith(".foam"):
            return os.path.join(case_dir, name)
    created = os.path.join(case_dir, "case.foam")
    open(created, "a").close()
    sys.stderr.write("[info] created %s\n" % created)
    return created


def build_pipeline(cfg, case_dir, requested_arrays):
    """Open the case and return (source, reader).

    The solver leaves data DECOMPOSED in processor*/ and no reconstructPar is
    run, so the reader must be told to read the decomposed case; the default
    would look for reconstructed time directories and silently yield nothing."""
    from paraview.simple import (OpenFOAMReader, MergeBlocks, CellDatatoPointData,
                                 UpdatePipeline)

    foam_file = find_foam_file(case_dir)
    reader = OpenFOAMReader(FileName=foam_file)
    reader.CaseType = "Decomposed Case"
    reader.MeshRegions = ["internalMesh"]

    # Read only what is needed; loading all 21 fields wastes a lot of memory on
    # an 18.8 M cell mesh.
    reader.UpdatePipelineInformation()
    available = [a.Name for a in reader.CellData]
    wanted = [a for a in requested_arrays if a in available]
    missing = [a for a in requested_arrays if a not in available]
    if missing:
        sys.stderr.write("[warn] fields not in dataset, skipped: %s\n"
                         % ", ".join(missing))
    if not wanted:
        raise SystemExit("ERROR: none of the requested fields exist. "
                         "Available: %s" % ", ".join(sorted(available)))
    reader.CellArrays = wanted

    src = reader
    if cfg["data"].get("merge_blocks", True):
        # Removes seams between the 20 processor partitions before interpolation.
        src = MergeBlocks(Input=src)
    if cfg["data"].get("cell_to_point", True):
        # Cell -> point interpolation: this is what makes the images smooth
        # instead of showing blocky per-cell values.
        src = CellDatatoPointData(Input=src)
        src.ProcessAllArrays = 1

    UpdatePipeline(proxy=src)
    return src, reader, wanted


def select_time(reader, cfg):
    """Return the time value to render."""
    times = list(reader.TimestepValues) if reader.TimestepValues else [0.0]
    want = cfg["data"].get("time", "latest")
    if want in (None, "latest", "last"):
        return times[-1], times
    target = float(want)
    # Nearest available, so a slightly-off request still works.
    return min(times, key=lambda t: abs(t - target)), times


def make_lut(field, cfg):
    """Colour lookup table with FIXED limits. Identical limits across cases are
    what make the images comparable, so rescaling to the local data range is
    deliberately never done."""
    from paraview.simple import GetColorTransferFunction
    lut = GetColorTransferFunction(field["array"])
    lut.ApplyPreset(field.get("colormap", "Turbo"), True)
    lo, hi = float(field["range"][0]), float(field["range"][1])
    lut.RescaleTransferFunction(lo, hi)
    lut.NanColor = [0.65, 0.65, 0.65]
    lut.NanOpacity = 1.0
    return lut


def render_direction(cfg, src, direction, fields, out_dir, time_value,
                     dry_run=False, limit=None, positions_override=None):
    """Render every enabled field at every slice position for one direction."""
    from paraview.simple import (Slice, Show, Hide, GetActiveViewOrCreate,
                                 SaveScreenshot, ColorBy, Delete, Render)
    import paraview.simple as pvs

    # ParaView resets the camera on the FIRST render of a view, which silently
    # discarded our camera and produced one wrongly-framed image per direction
    # (the whole domain cross-section shown as a small square). This is the
    # documented way to switch that behaviour off; ParaView's own exported
    # Python scripts call it for the same reason.
    try:
        pvs._DisableFirstRenderCameraReset()
    except Exception:
        pass

    dc = cfg["directions"][direction]
    res = cfg["image"]["resolution"]
    res_w, res_h = int(res[0]), int(res[1])
    bg = cfg["image"]["background"]

    positions = (positions_override if positions_override is not None
                 else slice_positions(dc["spacing"], dc["start"], dc["end"]))
    if limit:
        positions = positions[:limit]

    frame = dc["frame"]
    centre_h, centre_v, scale = fit_frame(frame["horizontal"], frame["vertical"],
                                          res_w, res_h)

    # Explicit camera override. If parallel_scale (and optionally center) are
    # given in slices.yaml, they win over the computed frame. This is the route
    # for reproducing a view dialled in by hand in the ParaView GUI: read the
    # numbers out with dump_camera.py and paste them in.
    if dc.get("parallel_scale"):
        scale = float(dc["parallel_scale"])
    if dc.get("center"):
        centre_h = float(dc["center"][0])
        centre_v = float(dc["center"][1])

    axis = AXIS_INDEX[direction]
    h_axis, v_axis = IN_PLANE[direction]

    view = GetActiveViewOrCreate("RenderView")
    view.ViewSize = [res_w, res_h]
    view.Background = [float(c) for c in bg]
    # A single flat background colour, not ParaView's default gradient.
    try:
        view.UseColorPaletteForBackground = 0
        view.BackgroundColorMode = "Single Color"
    except Exception:
        pass
    view.OrientationAxesVisibility = 0 if not cfg["image"].get("show_orientation_axes") else 1
    view.CenterAxesVisibility = 0
    view.UseLight = 0          # flat colours, no shading gradient across the slice

    axis = AXIS_INDEX[direction]
    h_axis, v_axis = IN_PLANE[direction]
    cam_dir = [float(v) for v in dc["camera_dir"]]
    view_up = [float(v) for v in dc["view_up"]]

    slc = Slice(Input=src)
    slc.SliceType = "Plane"
    slc.SliceType.Normal = NORMALS[direction]
    slc.Triangulatetheslice = 0

    # Show ONCE, outside the loop. Show() triggers an automatic ResetCamera, so
    # any camera set before it is discarded -- that is why an earlier version
    # rendered the whole domain as a small square instead of the requested
    # frame. The camera is therefore applied after Show and re-applied for every
    # slice, since ParaView may reset it again whenever the input bounds change.
    disp = Show(slc, view)
    disp.Representation = "Surface"

    # Belt and braces: absorb any camera reset that still happens on the first
    # render into a throwaway frame, before the first image is saved.
    Render(view)

    def apply_camera(pos):
        focal = [0.0, 0.0, 0.0]
        focal[axis] = pos
        focal[AXIS_INDEX[h_axis]] = centre_h
        focal[AXIS_INDEX[v_axis]] = centre_v
        view.CameraFocalPoint = focal
        # 1 m stand-off; irrelevant for a parallel projection but must be non-zero.
        view.CameraPosition = [focal[i] - cam_dir[i] * 1.0 for i in range(3)]
        view.CameraViewUp = view_up
        view.CameraParallelProjection = 1
        view.CameraParallelScale = scale

    written = []
    for pos in positions:
        origin = [0.0, 0.0, 0.0]
        origin[axis] = pos
        slc.SliceType.Origin = origin

        for field in fields:
            array = field["array"]
            comp = field.get("component", None)
            if comp is None:
                ColorBy(disp, ("POINTS", array))
            elif int(comp) < 0:
                ColorBy(disp, ("POINTS", array, "Magnitude"))
            else:
                ColorBy(disp, ("POINTS", array, "XYZ"[int(comp)]))

            lut = make_lut(field, cfg)
            disp.LookupTable = lut
            disp.SetScalarBarVisibility(view, False)

            name = "%s_%s%+.4f.png" % (field["key"], direction, pos)
            path = os.path.join(out_dir, field["key"], name)
            if dry_run:
                written.append(path)
                continue
            d = os.path.dirname(path)
            if not os.path.isdir(d):
                os.makedirs(d)
            # Camera last, immediately before rendering, so nothing can undo it.
            apply_camera(pos)
            Render(view)
            SaveScreenshot(path, view,
                           ImageResolution=[res_w, res_h],
                           TransparentBackground=0)
            written.append(path)
            sys.stdout.write("  %s\n" % os.path.relpath(path, out_dir))
            sys.stdout.flush()

    Hide(slc, view)
    Delete(slc)
    return written, (centre_h, centre_v, scale)


def report_ranges(src, fields, time_value):
    """Print the ACTUAL data range of each field so the fixed limits in
    slices.yaml can be chosen from evidence rather than guessed."""
    from paraview.simple import UpdatePipeline
    UpdatePipeline(time=time_value, proxy=src)
    info = src.GetPointDataInformation()
    print("")
    print("Actual data ranges at t = %g (point data, after cell-to-point):" % time_value)
    print("  %-34s %-14s %-14s %s" % ("field", "min", "max", "configured range"))
    for field in fields:
        arr = info.GetArray(field["array"])
        if arr is None:
            print("  %-34s (not present)" % field["array"])
            continue
        comp = field.get("component", None)
        idx = -1 if comp is None or int(comp) < 0 else int(comp)
        if arr.GetNumberOfComponents() == 1:
            idx = 0
        rng = arr.GetRange(idx)
        print("  %-34s %-14.5g %-14.5g %s" % (field["key"], rng[0], rng[1],
                                              field["range"]))
    print("")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(
        description="Batch slice rendering for the wing/wheel RANS campaign.")
    ap.add_argument("--case", required=True, help="case directory")
    ap.add_argument("--config", default=os.path.join(here, "slices.yaml"))
    ap.add_argument("--out", default=None,
                    help="output directory (default: <case>/images/slices)")
    ap.add_argument("--dirs", default=None,
                    help="override enabled directions, e.g. x or xz")
    ap.add_argument("--fields", default=None,
                    help="comma-separated field keys to render (default: all)")
    ap.add_argument("--quick", action="store_true",
                    help="render only quick_fields from the config")
    ap.add_argument("--spacing", type=float, default=None,
                    help="override slice spacing in metres for all directions")
    ap.add_argument("--positions", default=None,
                    help="explicit positions in metres, e.g. -0.05,0.0,0.05. "
                         "Handy for checking the framing on a few examples.")
    ap.add_argument("--preview", action="store_true",
                    help="render 3 representative slices per direction only")
    ap.add_argument("--limit", type=int, default=None,
                    help="render at most N slice positions per direction")
    ap.add_argument("--report-ranges", action="store_true",
                    help="print actual data ranges and exit without rendering")
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be produced without rendering")
    args = ap.parse_args()

    cfg = load_config(args.config)
    case_dir = os.path.abspath(args.case)
    if not os.path.isdir(case_dir):
        raise SystemExit("ERROR: no such case directory: %s" % case_dir)
    out_dir = os.path.abspath(args.out) if args.out \
        else os.path.join(case_dir, "images", "slices")

    # --- select fields ---
    all_fields = cfg["fields"]
    by_key = dict((f["key"], f) for f in all_fields)
    if args.fields:
        keys = [k.strip() for k in args.fields.split(",") if k.strip()]
    elif args.quick:
        keys = list(cfg.get("quick_fields") or [all_fields[0]["key"]])
    else:
        keys = [f["key"] for f in all_fields]
    unknown = [k for k in keys if k not in by_key]
    if unknown:
        raise SystemExit("ERROR: unknown field key(s): %s\nAvailable: %s"
                         % (", ".join(unknown), ", ".join(by_key)))
    fields = [by_key[k] for k in keys]

    # --- select directions ---
    if args.dirs:
        dirs = [d for d in "xyz" if d in args.dirs.lower()]
    else:
        dirs = [d for d in "xyz" if cfg["directions"].get(d, {}).get("enabled")]
    if not dirs:
        raise SystemExit("ERROR: no slice directions enabled.")

    if args.spacing:
        for d in dirs:
            cfg["directions"][d]["spacing"] = args.spacing

    explicit = None
    if args.positions:
        explicit = [float(p) for p in args.positions.split(",") if p.strip()]

    print("=" * 68)
    print("Slice rendering")
    print("=" * 68)
    print("  case       : %s" % case_dir)
    print("  out        : %s" % out_dir)
    print("  directions : %s" % ", ".join(dirs))
    print("  fields     : %s" % ", ".join(keys))
    print("  resolution : %dx%d" % tuple(cfg["image"]["resolution"]))

    total = 0
    for d in dirs:
        dc = cfg["directions"][d]
        if explicit is not None:
            n = len(explicit)
        elif args.preview:
            n = 3
        else:
            n = len(slice_positions(dc["spacing"], dc["start"], dc["end"]))
            if args.limit:
                n = min(n, args.limit)
        total += n * len(fields)
        print("  %s: %d positions x %d fields = %d images"
              % (d, n, len(fields), n * len(fields)))
    print("  TOTAL      : %d images" % total)
    print("")

    if args.dry_run and not args.report_ranges:
        print("(dry run, nothing rendered)")
        return

    arrays = sorted(set(f["array"] for f in fields))
    src, reader, loaded = build_pipeline(cfg, case_dir, arrays)
    time_value, times = select_time(reader, cfg)
    print("  times available : %s" % ", ".join("%g" % t for t in times))
    print("  rendering time  : %g" % time_value)

    from paraview.simple import UpdatePipeline
    UpdatePipeline(time=time_value, proxy=src)

    if args.report_ranges:
        report_ranges(src, fields, time_value)
        return

    for d in dirs:
        dc = cfg["directions"][d]
        pos = explicit
        if pos is None and args.preview:
            # Three positions spread across the range: start, middle, end.
            p = slice_positions(dc["spacing"], dc["start"], dc["end"])
            pos = [p[0], p[len(p) // 2], p[-1]]
        print("")
        print("--- %s-normal slices ---" % d)
        written, frame = render_direction(
            cfg, src, d, fields, out_dir, time_value,
            dry_run=args.dry_run, limit=args.limit, positions_override=pos)
        print("  centre=(%.4f, %.4f)  ParallelScale=%.5f  -> %d images"
              % (frame[0], frame[1], frame[2], len(written)))

    print("")
    print("Done. Images in %s" % out_dir)


if __name__ == "__main__":
    main()
