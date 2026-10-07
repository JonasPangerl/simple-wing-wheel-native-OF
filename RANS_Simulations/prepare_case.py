#!/usr/bin/env python3
"""
prepare_case.py - create a runnable case directory from _template/

    python3 prepare_case.py --span 1.42 --height 0.13 --aoa 8 --width 0.63

What it does:
  1. checks that the wing and wheel STL for that combination exist
  2. copies _template/ to S<span>_h<height>_AOA<aoa>_W<width>/
  3. rewrites the GEOMETRY block of include/caseParameters in the copy

That is all. It does not run OpenFOAM and it does not touch the geometry;
the STLs are scaled from mm to m by Allmesh, inside the case.

Standard library only, and deliberately written for Python 3.6, which is
still what /usr/bin/python3 is on a RHEL/Rocky 8 cluster.
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

if sys.version_info < (3, 6):
    sys.exit("prepare_case.py needs Python 3.6 or newer")

TEMPLATE_DIR = "_template"
GEOM_SUBDIR = Path("Diasinos_Geometry_Generator") / "output"

# Only these keys are rewritten in include/caseParameters
GEOMETRY_KEYS = ("caseName", "spanC", "heightC", "aoaDeg", "widthC",
                 "wingSTL", "wheelSTL")


def case_name(span, height, aoa, width):
    """Directory name for a parameter combination.

    Must stay byte-identical to the Case_Name column in
    campaign/WingWheel_RunMatrix.csv, which build_matrix.py generates with
    exactly this format.
    """
    return "S{:.2f}_h{:.2f}_AOA{:g}_W{:.2f}".format(span, height, aoa, width)


def stl_names(span, height, aoa, width):
    """File names the geometry generator writes for this combination."""
    wing = "wing_S{:.2f}_h{:.2f}_AOA{:g}.stl".format(span, height, aoa)
    wheel = "wheel_W{:.2f}.stl".format(width)
    return wing, wheel


def patch_case_parameters(path, values):
    """Rewrite the GEOMETRY entries in include/caseParameters.

    Only the keys in `values` are touched; comments, layout and every
    physical setting in the file are left exactly as they are. A key that
    cannot be found is a hard error rather than a silent no-op, because the
    alternative is a case that runs with the template's parameters.
    """
    text = path.read_text()

    for key in GEOMETRY_KEYS:
        value = values[key]
        # 'key   <anything>;' at the start of a line, preserving indentation,
        # the gap after the key, and any trailing // comment.
        pattern = re.compile(
            r"^(?P<indent>[ \t]*)" + re.escape(key)
            + r"(?P<gap>[ \t]+)[^;\n]*;(?P<tail>[^\n]*)$",
            re.MULTILINE,
        )

        def _sub(m, v=value, k=key):
            return "{}{}{}{};{}".format(
                m.group("indent"), k, m.group("gap"), v, m.group("tail")
            )

        text, n = pattern.subn(_sub, text, count=1)
        if n != 1:
            sys.exit(
                "ERROR: could not find key '{}' in {}\n"
                "       The template's include/caseParameters has been changed\n"
                "       in a way prepare_case.py does not understand.".format(
                    key, path)
            )

    path.write_text(text)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--span", type=float, required=True,
                    help="S/c, wing half-span to the endplate outer edge")
    ap.add_argument("--height", type=float, required=True,
                    help="h/c, ride height")
    ap.add_argument("--aoa", type=float, required=True,
                    help="angle of attack [deg]")
    ap.add_argument("--width", type=float, required=True,
                    help="W/c, wheel width")
    ap.add_argument("--name", help="override the case directory name")
    ap.add_argument("--force", action="store_true",
                    help="delete an existing case directory first")
    ap.add_argument("--quiet", action="store_true",
                    help="print only the created path, for use by scripts")
    args = ap.parse_args()

    sims_dir = Path(__file__).resolve().parent
    project_root = sims_dir.parent

    template = sims_dir / TEMPLATE_DIR
    if not (template / "include" / "caseParameters").is_file():
        sys.exit("ERROR: template looks broken: {}".format(template))

    name = args.name or case_name(args.span, args.height, args.aoa, args.width)
    case_dir = sims_dir / name

    # --- geometry must exist before we create anything ---------------------
    wing_stl, wheel_stl = stl_names(args.span, args.height, args.aoa, args.width)
    geom = project_root / GEOM_SUBDIR
    wing_path = geom / "wings" / wing_stl
    wheel_path = geom / "wheels" / wheel_stl

    missing = [p for p in (wing_path, wheel_path) if not p.is_file()]
    if missing:
        sys.stderr.write("ERROR: geometry not found:\n")
        for p in missing:
            sys.stderr.write("         {}\n".format(p))
        sys.stderr.write(
            "\n       Generate it first:\n"
            "         cd {}\n"
            "         python3 -m geometry_generator.generate\n"
            "\n       See docs/02_geometry.md.\n".format(
                project_root / "Diasinos_Geometry_Generator")
        )
        return 1

    # --- create the case ---------------------------------------------------
    if case_dir.exists():
        if not args.force:
            sys.stderr.write(
                "ERROR: {} already exists. Use --force to replace it.\n".format(
                    case_dir)
            )
            return 1
        shutil.rmtree(str(case_dir))

    # Ignore anything a previous run might have left inside the template
    shutil.copytree(
        str(template),
        str(case_dir),
        ignore=shutil.ignore_patterns(
            "processor*", "postProcessing", "log.*", "results.*",
            ".stage_*", ".solve_result", "images",
            "polyMesh", "triSurface", "extendedFeatureEdgeMesh",
        ),
    )

    patch_case_parameters(
        case_dir / "include" / "caseParameters",
        {
            "caseName": '"{}"'.format(name),
            "spanC": "{:g}".format(args.span),
            "heightC": "{:g}".format(args.height),
            "aoaDeg": "{:g}".format(args.aoa),
            "widthC": "{:g}".format(args.width),
            "wingSTL": '"{}"'.format(wing_stl),
            "wheelSTL": '"{}"'.format(wheel_stl),
        },
    )

    if args.quiet:
        # stdout contract for the campaign runner: the path, nothing else
        print(case_dir)
    else:
        print("Created {}".format(case_dir))
        print("  S/c {}   h/c {}   AOA {:g} deg   W/c {}".format(
            args.span, args.height, args.aoa, args.width))
        print("  wing  {}".format(wing_stl))
        print("  wheel {}".format(wheel_stl))
        print()
        print("Run it with:")
        print("  cd RANS_Simulations/{}".format(name))
        print("  ./Allrun")

    return 0


if __name__ == "__main__":
    sys.exit(main())
