#!/usr/bin/env python3
"""
render_archive.py - Create compact VTM archive from OpenFOAM case.

This script extracts key data from an OpenFOAM case and saves it as
a compact VTM (VTK MultiBlock) archive that can be used for post-hoc
visualization even after the full case data is pruned.

The archive includes:
- Surface mesh with all fields
- Key slice planes
- Vortex isosurfaces

Usage:
    pvbatch render_archive.py /path/to/case [--output archive.vtm]
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from paraview.simple import *
    PARAVIEW_AVAILABLE = True
except ImportError:
    PARAVIEW_AVAILABLE = False

import yaml


def load_views_config(config_dir: Path):
    """Load views configuration for slice definitions."""
    views_file = config_dir / "views.yaml"
    if views_file.exists():
        with open(views_file) as f:
            return yaml.safe_load(f)
    return {}


def create_archive(case_dir: Path, output_file: Path, config_dir: Path):
    """Create VTM archive from OpenFOAM case."""
    if not PARAVIEW_AVAILABLE:
        print("ERROR: ParaView not available. Run with: pvbatch render_archive.py ...")
        return 1
    
    case_name = case_dir.name
    print(f"Creating archive for: {case_name}")
    
    # Find .foam file
    foam_files = list(case_dir.glob("*.foam"))
    if not foam_files:
        foam_file = case_dir / "case.foam"
        foam_file.touch()
    else:
        foam_file = foam_files[0]
    
    print(f"  Loading: {foam_file}")
    
    # Read the OpenFOAM case
    reader = OpenFOAMReader(FileName=str(foam_file))
    reader.CaseType = 'Decomposed Case'
    reader.MeshRegions = ['internalMesh']
    reader.CellArrays = list(reader.CellArrays)
    reader.PointArrays = list(reader.PointArrays)
    reader.UpdatePipeline()
    
    # Get latest time
    times = reader.TimestepValues
    if times:
        latest_time = max(times)
        print(f"  Latest time: {latest_time}")
        reader.UpdatePipeline(latest_time)
    
    # Create a group to hold all data
    group = GroupDatasets()
    
    # 1. Extract surface mesh
    print("  Extracting surface mesh...")
    surface = ExtractSurface(Input=reader)
    surface.UpdatePipeline()
    
    # 2. Create key slices
    views_config = load_views_config(config_dir)
    slices = []
    
    for slice_dir, slice_list in views_config.get('slices', {}).items():
        for slice_config in slice_list:
            slice_name = slice_config['name']
            print(f"  Creating slice: {slice_name}")
            
            slice_filter = Slice(Input=reader)
            slice_filter.SliceType = 'Plane'
            slice_filter.SliceType.Origin = slice_config['origin']
            slice_filter.SliceType.Normal = slice_config['normal']
            slice_filter.UpdatePipeline()
            slices.append(slice_filter)
    
    # 3. Create vortex isosurface (Q-criterion or helicity)
    print("  Creating vortex isosurface...")
    
    # Check for available vortex identification fields
    point_arrays = [reader.PointData.GetArrayName(i) for i in range(reader.PointData.GetNumberOfArrays())]
    
    vortex_iso = None
    if 'helicitySignedNormalizedQ' in point_arrays:
        contour = Contour(Input=reader)
        contour.ContourBy = ['POINTS', 'helicitySignedNormalizedQ']
        contour.Isosurfaces = [0.5, -0.5]
        contour.UpdatePipeline()
        vortex_iso = contour
    elif 'normalizedHelicity' in point_arrays:
        contour = Contour(Input=reader)
        contour.ContourBy = ['POINTS', 'normalizedHelicity']
        contour.Isosurfaces = [0.7, -0.7]
        contour.UpdatePipeline()
        vortex_iso = contour
    
    # Save as VTM (multiblock)
    print(f"  Saving archive: {output_file}")
    
    # Save surface
    surface_file = output_file.parent / f"{output_file.stem}_surface.vtp"
    SaveData(str(surface_file), surface)
    
    # Save slices
    for i, slice_filter in enumerate(slices):
        slice_file = output_file.parent / f"{output_file.stem}_slice_{i:02d}.vtp"
        SaveData(str(slice_file), slice_filter)
    
    # Save vortex isosurface
    if vortex_iso:
        vortex_file = output_file.parent / f"{output_file.stem}_vortex.vtp"
        SaveData(str(vortex_file), vortex_iso)
    
    # Create manifest
    manifest_file = output_file.parent / f"{output_file.stem}_manifest.txt"
    with open(manifest_file, 'w') as f:
        f.write(f"# Archive manifest for {case_name}\n")
        f.write(f"case_name: {case_name}\n")
        f.write(f"time: {latest_time if times else 'N/A'}\n")
        f.write(f"surface: {surface_file.name}\n")
        for i, _ in enumerate(slices):
            f.write(f"slice_{i:02d}: {output_file.stem}_slice_{i:02d}.vtp\n")
        if vortex_iso:
            f.write(f"vortex: {output_file.stem}_vortex.vtp\n")
    
    print(f"Archive created: {output_file.parent}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Create compact VTM archive from OpenFOAM case"
    )
    parser.add_argument("case_dir", type=str, help="Path to OpenFOAM case directory")
    parser.add_argument("--output", "-o", type=str, help="Output VTM file path")
    parser.add_argument("--config", "-c", type=str, help="Configuration directory")
    
    args = parser.parse_args()
    
    case_dir = Path(args.case_dir).resolve()
    
    if args.output:
        output_file = Path(args.output).resolve()
    else:
        output_file = case_dir / "archive" / f"{case_dir.name}.vtm"
    
    if args.config:
        config_dir = Path(args.config).resolve()
    else:
        config_dir = Path(__file__).parent.resolve()
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    return create_archive(case_dir, output_file, config_dir)


if __name__ == "__main__":
    sys.exit(main())
