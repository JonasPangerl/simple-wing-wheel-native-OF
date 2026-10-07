#!/usr/bin/env python3
"""
build_matrix.py - generate the campaign run matrix as CSV

    python3 build_matrix.py                 # write WingWheel_RunMatrix.csv
    python3 build_matrix.py --enable-reference
    python3 build_matrix.py --enable-all

Writes one row per parameter combination (5 spans x 4 heights x 7 angles
x 3 widths = 420 cases), with the derived geometry columns and the two
enable flags that run_campaign.py reads.

Existing enable flags are PRESERVED when the file is regenerated, so you can
re-run this after changing the parameter lists without losing your selection.

Standard library only. The previous version produced a styled .xlsx via
openpyxl; that dependency is gone on purpose, because the point of this repo
is that it runs on a cluster with nothing but python3 and OpenFOAM.
"""

import argparse
import csv
import itertools
import os
import sys
from datetime import datetime

if sys.version_info < (3, 6):
    sys.exit("build_matrix.py needs Python 3.6 or newer")

# --- parameter space (must match Diasinos_Geometry_Generator/params.yaml) ---
SPANS = [0.97, 1.06, 1.24, 1.42, 1.60]
HEIGHTS = [0.08, 0.13, 0.18, 0.28]
ANGLES = [0, 2, 4, 6, 8, 10, 12]
WIDTHS = [0.56, 0.63, 0.70]

# --- fixed geometry, normalised by chord c = 75 mm -------------------------
WHEEL_TRACK_OUTER = 1.6     # T/c, outer face of the wheel
ENDPLATE_THICKNESS = 0.04   # t_ep/c

# --- the configuration the Diasinos papers report --------------------------
REF = dict(span=1.42, height=0.13, aoa=8, width=0.63)

OUTPUT = "WingWheel_RunMatrix.csv"

COLUMNS = [
    "Case_Name", "Is_Reference",
    "S_c", "h_c", "AOA_deg", "W_c",
    "Gap_c", "Interaction", "EP_Bottom_c",
    "Wing_STL", "Wheel_STL",
    "Enable_Mesh", "Enable_Solve",
    "Notes",
]


def compute_gap(span, width):
    """Gap from the endplate outer edge to the wheel inner face, in chords.

    Gap = (T - W) - S, where T is the wheel outer-face position and W the
    wheel width, so (T - W) is the wheel inner face.

    Negative means the endplate reaches outboard past the wheel inner face,
    i.e. wing and wheel overlap in the spanwise sense.
    """
    wheel_inner = WHEEL_TRACK_OUTER - width
    return wheel_inner - span


def classify_interaction(gap):
    """Bucket the configuration by how wing and wheel line up spanwise."""
    if gap > 0.05:
        return "inboard"
    if gap > -0.05:
        return "aligned"
    if gap > -0.15:
        return "outboard_weak"
    return "outboard_strong"


def endplate_bottom(height):
    """Endplate bottom edge height above the ground, in chords.

    From GEOMETRY_SPECIFICATION.md: the ride height h is the lowest point of
    the wing, and the endplate reaches 0.04c below that. The ride height is
    applied after the AOA rotation, so this does not depend on AOA.
    """
    return height - ENDPLATE_THICKNESS


def case_name(span, height, aoa, width):
    """Must match prepare_case.py:case_name() byte for byte."""
    return "S{:.2f}_h{:.2f}_AOA{:g}_W{:.2f}".format(span, height, aoa, width)


def is_reference(span, height, aoa, width):
    return (abs(span - REF["span"]) < 1e-6
            and abs(height - REF["height"]) < 1e-6
            and abs(aoa - REF["aoa"]) < 1e-6
            and abs(width - REF["width"]) < 1e-6)


def read_existing_flags(path):
    """Existing Enable_Mesh/Enable_Solve/Notes, keyed by case name."""
    if not os.path.isfile(path):
        return {}

    keep = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            name = row.get("Case_Name")
            if name:
                keep[name] = (
                    row.get("Enable_Mesh", "False"),
                    row.get("Enable_Solve", "False"),
                    row.get("Notes", ""),
                )
    return keep


def build_rows(enable_mode, existing):
    rows = []
    for span, height, aoa, width in itertools.product(
            SPANS, HEIGHTS, ANGLES, WIDTHS):

        name = case_name(span, height, aoa, width)
        gap = compute_gap(span, width)
        ref = is_reference(span, height, aoa, width)

        if name in existing:
            en_mesh, en_solve, notes = existing[name]
        else:
            en_mesh = en_solve = "False"
            notes = ""

        if enable_mode == "all":
            en_mesh = en_solve = "True"
        elif enable_mode == "reference" and ref:
            en_mesh = en_solve = "True"

        rows.append({
            "Case_Name": name,
            "Is_Reference": "True" if ref else "False",
            "S_c": "{:.2f}".format(span),
            "h_c": "{:.2f}".format(height),
            "AOA_deg": "{:g}".format(aoa),
            "W_c": "{:.2f}".format(width),
            "Gap_c": "{:.3f}".format(gap),
            "Interaction": classify_interaction(gap),
            "EP_Bottom_c": "{:.3f}".format(endplate_bottom(height)),
            "Wing_STL": "wing_S{:.2f}_h{:.2f}_AOA{:g}.stl".format(span, height, aoa),
            "Wheel_STL": "wheel_W{:.2f}.stl".format(width),
            "Enable_Mesh": en_mesh,
            "Enable_Solve": en_solve,
            "Notes": notes,
        })

    return rows


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--enable-all", action="store_true",
                       help="set Enable_Mesh and Enable_Solve on every row")
    group.add_argument("--enable-reference", action="store_true",
                       help="enable only the Diasinos reference configuration")
    ap.add_argument("--output", default=OUTPUT)
    args = ap.parse_args()

    enable_mode = None
    if args.enable_all:
        enable_mode = "all"
    elif args.enable_reference:
        enable_mode = "reference"

    here = os.path.dirname(os.path.abspath(__file__))
    out_path = args.output if os.path.isabs(args.output) \
        else os.path.join(here, args.output)

    existing = read_existing_flags(out_path)
    rows = build_rows(enable_mode, existing)

    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    n_mesh = sum(1 for r in rows if r["Enable_Mesh"] == "True")
    n_solve = sum(1 for r in rows if r["Enable_Solve"] == "True")

    print("Wrote {} ({} rows)".format(out_path, len(rows)))
    print("  generated:      {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print("  Enable_Mesh:    {}".format(n_mesh))
    print("  Enable_Solve:   {}".format(n_solve))
    if existing:
        print("  preserved flags for {} existing rows".format(len(existing)))

    by_kind = {}
    for r in rows:
        by_kind[r["Interaction"]] = by_kind.get(r["Interaction"], 0) + 1
    print("  interaction types:")
    for kind in sorted(by_kind):
        print("    {:<18} {}".format(kind, by_kind[kind]))

    if not n_mesh:
        print("\nNothing is enabled yet. Enable the reference case with:")
        print("  python3 build_matrix.py --enable-reference")

    return 0


if __name__ == "__main__":
    sys.exit(main())
