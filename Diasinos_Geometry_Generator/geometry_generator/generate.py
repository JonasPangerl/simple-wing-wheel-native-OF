"""
Main generation script for wing and wheel STL files.

Supports:
- Config file input (YAML)
- Parameter sweep (all combinations)
- Preview mode
- Batch generation
"""

import argparse
import itertools
import csv
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np

from .config import GeometryConfig
from .wing_generator import WingGenerator
from .wheel_generator import WheelGenerator


def generate_from_config(config_path: str, preview_only: bool = False) -> None:
    """
    Generate all geometry combinations from a config file.
    
    Args:
        config_path: Path to YAML config file
        preview_only: If True, only preview first combination
    """
    config = GeometryConfig.from_yaml(config_path)
    
    if preview_only:
        # Preview first combination
        preview_geometry(
            span=config.spans[0],
            height=config.heights[0],
            angle=config.angles[0],
            width=config.widths[0],
            config=config
        )
        return
    
    generate_all_combinations(
        spans=config.spans,
        heights=config.heights,
        angles=config.angles,
        widths=config.widths,
        config=config
    )


def generate_all_combinations(
    spans: List[float],
    heights: List[float],
    angles: List[float],
    widths: List[float],
    config: Optional[GeometryConfig] = None
) -> None:
    """
    Generate STL files for all parameter combinations.
    
    Args:
        spans: List of S/c values
        heights: List of h/c values
        angles: List of AOA values in degrees
        widths: List of W/c values
        config: Optional GeometryConfig (uses defaults if None)
    """
    if config is None:
        config = GeometryConfig()
    
    output_dir = Path(config.output_dir)
    wings_dir = output_dir / "wings"
    wheels_dir = output_dir / "wheels"
    
    # Create output directories
    wings_dir.mkdir(parents=True, exist_ok=True)
    wheels_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize generators
    wing_gen = WingGenerator(config)
    wheel_gen = WheelGenerator(config)
    
    # Track generated combinations
    combinations = []
    
    # Generate wing combinations (S x h x AOA)
    print(f"Generating wing geometries...")
    wing_combos = list(itertools.product(spans, heights, angles))
    total_wings = len(wing_combos)
    
    for i, (span, height, angle) in enumerate(wing_combos, 1):
        print(f"  Wing {i}/{total_wings}: S={span:.2f}, h={height:.2f}, AOA={angle:.1f}")
        
        # Generate surfaces
        surfaces = wing_gen.generate_surfaces(span, height, angle)
        
        # Create filename for this combination
        filename = f"wing_S{span:.2f}_h{height:.2f}_AOA{angle:.0f}.stl"
        filepath = wings_dir / filename
        
        # Save as single STL with multiple named solids
        from .utils import save_multi_solid_stl
        save_multi_solid_stl(surfaces, str(filepath), name_prefix="wing-")
        
        combinations.append({
            'type': 'wing',
            'span': span,
            'height': height,
            'angle': angle,
            'file': str(filepath)
        })
    
    # Generate wheel combinations (only W varies)
    print(f"\nGenerating wheel geometries...")
    total_wheels = len(widths)
    
    for i, width in enumerate(widths, 1):
        print(f"  Wheel {i}/{total_wheels}: W={width:.2f}")
        
        # Generate surfaces
        surfaces = wheel_gen.generate_surfaces(width)
        
        # Create filename for this combination
        filename = f"wheel_W{width:.2f}.stl"
        filepath = wheels_dir / filename
        
        # Save as single STL with multiple named solids
        from .utils import save_multi_solid_stl
        save_multi_solid_stl(surfaces, str(filepath), name_prefix="wheel-")
        
        combinations.append({
            'type': 'wheel',
            'width': width,
            'file': str(filepath)
        })
    
    # Write combinations log
    log_path = output_dir / "combinations.csv"
    write_combinations_log(combinations, str(log_path))
    
    print(f"\nGeneration complete!")
    print(f"  Wings: {total_wings} combinations")
    print(f"  Wheels: {total_wheels} combinations")
    print(f"  Output: {output_dir}")
    print(f"  Log: {log_path}")


def write_combinations_log(combinations: List[Dict], filepath: str) -> None:
    """Write combinations to CSV log file."""
    with open(filepath, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow(['type', 'span_c', 'height_c', 'angle_deg', 'width_c', 'file'])
        
        # Write data
        for combo in combinations:
            writer.writerow([
                combo.get('type', ''),
                combo.get('span', ''),
                combo.get('height', ''),
                combo.get('angle', ''),
                combo.get('width', ''),
                combo.get('file', '')
            ])


def preview_geometry(
    span: float = 1.42,
    height: float = 0.13,
    angle: float = 8.0,
    width: float = 0.63,
    config: Optional[GeometryConfig] = None
) -> None:
    """
    Preview geometry with matplotlib 3D visualization.
    
    Args:
        span: S/c value
        height: h/c value
        angle: AOA in degrees
        width: W/c value
        config: Optional GeometryConfig
    """
    from .preview import preview_wing_wheel
    
    if config is None:
        config = GeometryConfig()
    
    preview_wing_wheel(span, height, angle, width, config)


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Generate wing and wheel STL geometries for CFD"
    )
    
    parser.add_argument(
        '--config', '-c',
        type=str,
        default='params.yaml',
        help='Path to YAML config file (default: params.yaml)'
    )
    
    parser.add_argument(
        '--preview', '-p',
        action='store_true',
        help='Preview geometry before generating'
    )
    
    # Individual parameter overrides for preview
    parser.add_argument('--span', type=float, help='Wing span S/c for preview')
    parser.add_argument('--height', type=float, help='Ride height h/c for preview')
    parser.add_argument('--angle', type=float, help='Angle of attack for preview')
    parser.add_argument('--width', type=float, help='Wheel width W/c for preview')
    
    args = parser.parse_args()
    
    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        config = GeometryConfig.from_yaml(str(config_path))
    else:
        print(f"Config file not found: {config_path}")
        print("Using default configuration...")
        config = GeometryConfig()
    
    if args.preview:
        # Preview mode
        span = args.span if args.span is not None else config.spans[0]
        height = args.height if args.height is not None else config.heights[0]
        angle = args.angle if args.angle is not None else config.angles[0]
        width = args.width if args.width is not None else config.widths[0]
        
        print(f"Previewing: S={span:.2f}, h={height:.2f}, AOA={angle:.1f}, W={width:.2f}")
        preview_geometry(span, height, angle, width, config)
    else:
        # Generate all combinations
        generate_all_combinations(
            spans=config.spans,
            heights=config.heights,
            angles=config.angles,
            widths=config.widths,
            config=config
        )


if __name__ == "__main__":
    main()
