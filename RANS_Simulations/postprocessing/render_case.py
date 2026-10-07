#!/usr/bin/env python3
"""
render_case.py - ParaView batch rendering script for wing+wheel RANS cases.

This script uses pvbatch to render images from OpenFOAM cases.
It reads the .foam file directly (no VTK conversion needed).

Usage:
    pvbatch render_case.py /path/to/case [--output /path/to/images]
    
Requirements:
    - ParaView with pvbatch
    - PyYAML for configuration files
"""

import argparse
import os
import sys
from pathlib import Path

# ParaView imports (only available when run with pvbatch)
try:
    from paraview.simple import *
    PARAVIEW_AVAILABLE = True
except ImportError:
    PARAVIEW_AVAILABLE = False
    print("Warning: ParaView not available. Run with pvbatch.")

import yaml


def load_config(config_dir: Path):
    """Load views and colormaps configuration."""
    views_file = config_dir / "views.yaml"
    colormaps_file = config_dir / "colormaps.yaml"
    
    with open(views_file) as f:
        views_config = yaml.safe_load(f)
    
    with open(colormaps_file) as f:
        colormaps_config = yaml.safe_load(f)
    
    return views_config, colormaps_config


def find_foam_file(case_dir: Path) -> Path:
    """Find the .foam file in the case directory."""
    foam_files = list(case_dir.glob("*.foam"))
    if foam_files:
        return foam_files[0]
    
    # Create one if it doesn't exist
    foam_file = case_dir / "case.foam"
    foam_file.touch()
    return foam_file


def setup_colormap(display, field_config):
    """Configure colormap for a display."""
    if 'range' in field_config:
        display.RescaleTransferFunctionToDataRange(False)
        lut = GetColorTransferFunction(display.ColorArrayName[1])
        lut.RescaleTransferFunction(field_config['range'][0], field_config['range'][1])
    
    if 'colormap' in field_config:
        lut = GetColorTransferFunction(display.ColorArrayName[1])
        lut.ApplyPreset(field_config['colormap'], True)


def setup_camera(view, camera_config):
    """Configure camera position and orientation."""
    view.CameraPosition = camera_config['camera_position']
    view.CameraFocalPoint = camera_config['focal_point']
    view.CameraViewUp = camera_config['view_up']
    
    if 'parallel_scale' in camera_config:
        view.CameraParallelScale = camera_config['parallel_scale']
        view.CameraParallelProjection = 1


def render_surface_views(reader, views_config, colormaps_config, output_dir: Path, case_name: str):
    """Render surface views with different fields."""
    print("Rendering surface views...")
    
    # Get the render view
    render_view = GetActiveViewOrCreate('RenderView')
    
    # Set background color
    bg_color = views_config.get('output', {}).get('background', [1, 1, 1])
    render_view.Background = bg_color
    
    # Set resolution
    resolution = views_config.get('output', {}).get('resolution', [1920, 1080])
    render_view.ViewSize = resolution
    
    # Show the reader
    display = Show(reader, render_view)
    display.Representation = 'Surface'
    
    # Get available fields
    point_data = reader.PointData
    cell_data = reader.CellData
    
    available_fields = []
    for i in range(point_data.GetNumberOfArrays()):
        available_fields.append(point_data.GetArrayName(i))
    for i in range(cell_data.GetNumberOfArrays()):
        available_fields.append(cell_data.GetArrayName(i))
    
    print(f"  Available fields: {available_fields}")
    
    # Render each view with each field
    for view_name, view_config in views_config.get('views', {}).items():
        setup_camera(render_view, view_config)
        
        for field_name, field_config in colormaps_config.get('fields', {}).items():
            if field_name not in available_fields:
                continue
            
            print(f"  Rendering {view_name} / {field_name}")
            
            # Color by field
            ColorBy(display, ('POINTS', field_name))
            setup_colormap(display, field_config)
            
            # Show color bar
            display.SetScalarBarVisibility(render_view, True)
            
            # Render
            Render()
            
            # Save screenshot
            output_file = output_dir / f"{case_name}_{view_name}_{field_name}.png"
            SaveScreenshot(str(output_file), render_view)
    
    Hide(reader, render_view)


def render_slice_views(reader, views_config, colormaps_config, output_dir: Path, case_name: str):
    """Render slice views."""
    print("Rendering slice views...")
    
    render_view = GetActiveViewOrCreate('RenderView')
    
    # Set background and resolution
    bg_color = views_config.get('output', {}).get('background', [1, 1, 1])
    render_view.Background = bg_color
    resolution = views_config.get('output', {}).get('resolution', [1920, 1080])
    render_view.ViewSize = resolution
    
    # Default field for slices
    default_field = colormaps_config.get('slice', {}).get('default_field', 'totalPressureCoeff')
    
    # Process each slice direction
    for slice_dir, slices in views_config.get('slices', {}).items():
        for slice_config in slices:
            slice_name = slice_config['name'].replace('=', '').replace('.', 'p')
            
            print(f"  Creating slice: {slice_name}")
            
            # Create slice
            slice_filter = Slice(Input=reader)
            slice_filter.SliceType = 'Plane'
            slice_filter.SliceType.Origin = slice_config['origin']
            slice_filter.SliceType.Normal = slice_config['normal']
            
            # Show slice
            slice_display = Show(slice_filter, render_view)
            slice_display.Representation = 'Surface'
            
            # Color by default field
            if default_field in [reader.PointData.GetArrayName(i) for i in range(reader.PointData.GetNumberOfArrays())]:
                ColorBy(slice_display, ('POINTS', default_field))
                if default_field in colormaps_config.get('fields', {}):
                    setup_colormap(slice_display, colormaps_config['fields'][default_field])
            
            # Set appropriate camera for slice direction
            if 'y' in slice_dir:
                # Side view for y-slices
                render_view.CameraPosition = [0.0, 0.5, 0.05]
                render_view.CameraFocalPoint = [0.0, 0.0, 0.05]
                render_view.CameraViewUp = [0.0, 0.0, 1.0]
            elif 'z' in slice_dir:
                # Top view for z-slices
                render_view.CameraPosition = [0.0, 0.1, 0.5]
                render_view.CameraFocalPoint = [0.0, 0.1, 0.0]
                render_view.CameraViewUp = [0.0, 1.0, 0.0]
            elif 'x' in slice_dir:
                # Front view for x-slices
                render_view.CameraPosition = [-0.5, 0.1, 0.05]
                render_view.CameraFocalPoint = [0.0, 0.1, 0.05]
                render_view.CameraViewUp = [0.0, 0.0, 1.0]
            
            render_view.CameraParallelScale = 0.2
            render_view.CameraParallelProjection = 1
            
            # Render and save
            Render()
            output_file = output_dir / f"{case_name}_slice_{slice_name}_{default_field}.png"
            SaveScreenshot(str(output_file), render_view)
            
            # Clean up
            Delete(slice_filter)
            del slice_filter


def render_case(case_dir: Path, output_dir: Path, config_dir: Path):
    """Main rendering function."""
    if not PARAVIEW_AVAILABLE:
        print("ERROR: ParaView not available. Run with: pvbatch render_case.py ...")
        return 1
    
    case_name = case_dir.name
    print(f"Rendering case: {case_name}")
    print(f"  Case directory: {case_dir}")
    print(f"  Output directory: {output_dir}")
    
    # Load configuration
    views_config, colormaps_config = load_config(config_dir)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find and load the .foam file
    foam_file = find_foam_file(case_dir)
    print(f"  Loading: {foam_file}")
    
    # Read the OpenFOAM case
    reader = OpenFOAMReader(FileName=str(foam_file))
    reader.CaseType = 'Decomposed Case'
    reader.MeshRegions = ['internalMesh']
    reader.CellArrays = list(reader.CellArrays)
    reader.PointArrays = list(reader.PointArrays)
    
    # Update to latest time
    reader.UpdatePipeline()
    
    # Get available times
    times = reader.TimestepValues
    if times:
        latest_time = max(times)
        print(f"  Latest time: {latest_time}")
        reader.UpdatePipeline(latest_time)
    
    # Render surface views
    render_surface_views(reader, views_config, colormaps_config, output_dir, case_name)
    
    # Render slice views
    render_slice_views(reader, views_config, colormaps_config, output_dir, case_name)
    
    print(f"Rendering complete. Images saved to: {output_dir}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Render ParaView images from OpenFOAM case"
    )
    parser.add_argument("case_dir", type=str, help="Path to OpenFOAM case directory")
    parser.add_argument("--output", "-o", type=str, help="Output directory for images")
    parser.add_argument("--config", "-c", type=str, help="Configuration directory")
    
    args = parser.parse_args()
    
    case_dir = Path(args.case_dir).resolve()
    
    if args.output:
        output_dir = Path(args.output).resolve()
    else:
        output_dir = case_dir / "images"
    
    if args.config:
        config_dir = Path(args.config).resolve()
    else:
        # Default to postprocessing directory
        config_dir = Path(__file__).parent.resolve()
    
    if not case_dir.exists():
        print(f"ERROR: Case directory not found: {case_dir}")
        return 1
    
    return render_case(case_dir, output_dir, config_dir)


if __name__ == "__main__":
    sys.exit(main())
