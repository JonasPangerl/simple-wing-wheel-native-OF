#!/usr/bin/env python3
"""
refinement_boxes_stl.py - write the snappyHexMesh refinement boxes as STLs

    python3 refinement_boxes_stl.py [--output DIR]

Produces one STL per box plus a combined file, so the refinement zones can be
loaded into ParaView as wireframes and checked against the geometry. Nothing
in the simulation pipeline reads these; it is a visual check only.

IMPORTANT: this list must stay in step with the `geometry` section of
RANS_Simulations/_template/system/snappyHexMeshDict. It is duplicated rather
than parsed, so if you move a box there, move it here too.

Boxes are written here in MILLIMETRES and converted to metres on output,
matching the mm values in the original HELYX volRef list.
"""

import argparse
from pathlib import Path


# (name, level, min_corner_mm, max_corner_mm)
REFINEMENT_BOXES = [
    ("L2-farfield",             2, (-300,   0,   0),   (600, 300, 250)),
    ("L3-body",                 3, (-200,   0,   0),   (350, 200, 150)),
    ("L4-neargeom",             4, (-160,   0,   0),   (200, 150, 120)),
    ("L4-wake",                 4, (  40,   0,   0),   (300, 170, 130)),
    ("L5-gap-underwing",        5, (-150,  60,   0),   ( 60, 130,  60)),
    ("L5-vortex-inboard",       5, (-100,  20,   0),   (200, 110,  50)),
    ("L5-vortex-outboard",      5, (-100, 100,   0),   (200, 145,  50)),
    # These two replace the per-region distance refinement that HELYX applied
    # to wing-ep-bottom and wheel-plinth, which snappyHexMesh cannot express.
    # They are positioned for the BASELINE geometry and do not follow the
    # parameters - see docs/07_case_reference.md.
    ("L6-endplate-bottom-edge", 6, (-145,  95,   4),   (-48, 112,  16)),
    ("L7-contact-patch",        7, ( -50,  70,   0),   ( 50, 122,   8)),
]


def generate_box_stl(name: str, min_corner: tuple, max_corner: tuple) -> str:
    """Generate ASCII STL for a box."""
    x0, y0, z0 = min_corner
    x1, y1, z1 = max_corner
    
    # Convert mm to m for consistency with OpenFOAM
    x0, y0, z0 = x0/1000, y0/1000, z0/1000
    x1, y1, z1 = x1/1000, y1/1000, z1/1000
    
    # 8 vertices of the box
    vertices = [
        (x0, y0, z0),  # 0: min corner
        (x1, y0, z0),  # 1
        (x1, y1, z0),  # 2
        (x0, y1, z0),  # 3
        (x0, y0, z1),  # 4
        (x1, y0, z1),  # 5
        (x1, y1, z1),  # 6
        (x0, y1, z1),  # 7: max corner
    ]
    
    # 12 triangles (2 per face)
    triangles = [
        # Bottom (z = z0), normal (0, 0, -1)
        (0, 2, 1, (0, 0, -1)),
        (0, 3, 2, (0, 0, -1)),
        # Top (z = z1), normal (0, 0, 1)
        (4, 5, 6, (0, 0, 1)),
        (4, 6, 7, (0, 0, 1)),
        # Front (y = y0), normal (0, -1, 0)
        (0, 1, 5, (0, -1, 0)),
        (0, 5, 4, (0, -1, 0)),
        # Back (y = y1), normal (0, 1, 0)
        (2, 3, 7, (0, 1, 0)),
        (2, 7, 6, (0, 1, 0)),
        # Left (x = x0), normal (-1, 0, 0)
        (0, 4, 7, (-1, 0, 0)),
        (0, 7, 3, (-1, 0, 0)),
        # Right (x = x1), normal (1, 0, 0)
        (1, 2, 6, (1, 0, 0)),
        (1, 6, 5, (1, 0, 0)),
    ]
    
    lines = [f"solid {name}"]
    
    for v0, v1, v2, normal in triangles:
        nx, ny, nz = normal
        p0 = vertices[v0]
        p1 = vertices[v1]
        p2 = vertices[v2]
        
        lines.append(f"  facet normal {nx} {ny} {nz}")
        lines.append("    outer loop")
        lines.append(f"      vertex {p0[0]} {p0[1]} {p0[2]}")
        lines.append(f"      vertex {p1[0]} {p1[1]} {p1[2]}")
        lines.append(f"      vertex {p2[0]} {p2[1]} {p2[2]}")
        lines.append("    endloop")
        lines.append("  endfacet")
    
    lines.append(f"endsolid {name}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate STL files for refinement boxes"
    )
    parser.add_argument("--output", "-o", type=str, default="refinement_boxes",
                        help="Output directory for STL files")
    
    args = parser.parse_args()
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating refinement box STLs in: {output_dir}")
    
    # Generate individual STL files
    for name, level, min_corner, max_corner in REFINEMENT_BOXES:
        stl_content = generate_box_stl(name, min_corner, max_corner)
        stl_file = output_dir / f"{name}.stl"
        
        with open(stl_file, 'w') as f:
            f.write(stl_content)
        
        print(f"  Created: {stl_file.name} (Level {level})")
    
    # Generate combined STL with all boxes
    combined_file = output_dir / "all_refinement_boxes.stl"
    with open(combined_file, 'w') as f:
        for name, level, min_corner, max_corner in REFINEMENT_BOXES:
            stl_content = generate_box_stl(f"{name}_L{level}", min_corner, max_corner)
            f.write(stl_content)
            f.write("\n")
    
    print(f"\n  Combined: {combined_file.name}")
    print(f"\nTotal: {len(REFINEMENT_BOXES)} refinement boxes")
    print("\nTo visualize in ParaView:")
    print(f"  1. Open ParaView")
    print(f"  2. File -> Open -> {output_dir / 'all_refinement_boxes.stl'}")
    print(f"  3. Apply, then set Representation to 'Wireframe'")


if __name__ == "__main__":
    main()
