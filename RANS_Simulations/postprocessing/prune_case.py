#!/usr/bin/env python3
"""
prune_case.py - Remove heavy data from a case after archiving.

This script removes the large mesh and solution data from an OpenFOAM case
while preserving:
- Case setup (0.orig/, constant/*Properties, system/, include/, All* scripts)
- results.json / results.txt and the log.* files
- postProcessing/ (forces, residuals, y+)
- The compact archive (if created)
- Images

Usage:
    python prune_case.py /path/to/case [--dry-run] [--force]
"""

import argparse
import shutil
import sys
from pathlib import Path


def get_case_size(case_dir: Path) -> int:
    """Get total size of case directory in bytes."""
    total = 0
    for item in case_dir.rglob('*'):
        if item.is_file():
            total += item.stat().st_size
    return total


def format_size(size_bytes: int) -> str:
    """Format size in human-readable form."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def prune_case(case_dir: Path, dry_run: bool = False, force: bool = False) -> int:
    """
    Prune heavy data from a case.
    
    Removes:
    - processor* directories (the decomposed mesh and solution)
    - constant/polyMesh (the reconstructed mesh)
    - numeric time directories (0.orig is not numeric, so it survives)
    - VTK directory, if one was produced

    Preserves:
    - 0.orig/, constant/*Properties, system/, include/, All* scripts
    - results.json, results.txt, geometry_used.txt, log.*
    - postProcessing/ (forces, residuals, y+)
    - archive/ (compact VTM files)
    - images/

    Note: constant/triSurface (the scaled STLs) is left in place. It is a few
    MB and Allmesh regenerates it anyway.
    """
    case_name = case_dir.name
    print(f"Pruning case: {case_name}")
    
    # Check for archive
    archive_dir = case_dir / "archive"
    if not archive_dir.exists() and not force:
        print("  WARNING: No archive found. Create archive first or use --force.")
        print("  Run: pvbatch render_archive.py", case_dir)
        return 1
    
    # Calculate initial size
    initial_size = get_case_size(case_dir)
    print(f"  Initial size: {format_size(initial_size)}")
    
    # Items to remove
    to_remove = []
    
    # Processor directories
    for proc_dir in case_dir.glob("processor*"):
        if proc_dir.is_dir():
            to_remove.append(proc_dir)
    
    # Serial mesh
    serial_mesh = case_dir / "constant" / "polyMesh"
    if serial_mesh.exists():
        to_remove.append(serial_mesh)
    
    # Time directories (except 0)
    for item in case_dir.iterdir():
        if item.is_dir():
            try:
                t = float(item.name)
                if t > 0:
                    to_remove.append(item)
            except ValueError:
                pass
    
    # VTK directory
    vtk_dir = case_dir / "VTK"
    if vtk_dir.exists():
        to_remove.append(vtk_dir)

    # Scaled STLs and extracted feature edges: ~27 MB per case, and Allmesh
    # rebuilds them from the geometry output in seconds.
    for sub in ("triSurface", "extendedFeatureEdgeMesh"):
        d = case_dir / "constant" / sub
        if d.exists():
            to_remove.append(d)
    
    # Calculate size to remove
    remove_size = 0
    for item in to_remove:
        if item.is_dir():
            for f in item.rglob('*'):
                if f.is_file():
                    remove_size += f.stat().st_size
        elif item.is_file():
            remove_size += item.stat().st_size
    
    print(f"  Will remove: {format_size(remove_size)} ({len(to_remove)} items)")
    
    if dry_run:
        print("  [DRY RUN] Would remove:")
        for item in to_remove:
            print(f"    - {item.relative_to(case_dir)}")
        return 0
    
    # Remove items
    for item in to_remove:
        print(f"  Removing: {item.relative_to(case_dir)}")
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    
    # Create pruned marker
    pruned_marker = case_dir / "PRUNED"
    with open(pruned_marker, 'w') as f:
        f.write(f"Case pruned on: {__import__('datetime').datetime.now().isoformat()}\n")
        f.write(f"Initial size: {format_size(initial_size)}\n")
        f.write(f"Removed: {format_size(remove_size)}\n")
    
    # Calculate final size
    final_size = get_case_size(case_dir)
    print(f"  Final size: {format_size(final_size)}")
    print(f"  Saved: {format_size(initial_size - final_size)}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Prune heavy data from OpenFOAM case"
    )
    parser.add_argument("case_dir", type=str, help="Path to case directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed")
    parser.add_argument("--force", action="store_true", help="Prune even without archive")
    
    args = parser.parse_args()
    
    case_dir = Path(args.case_dir).resolve()
    
    if not case_dir.exists():
        print(f"ERROR: Case directory not found: {case_dir}")
        return 1
    
    return prune_case(case_dir, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
