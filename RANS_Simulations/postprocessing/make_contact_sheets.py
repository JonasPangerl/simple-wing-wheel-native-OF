#!/usr/bin/env python3
"""
make_contact_sheets.py - Create contact sheet images from rendered case images.

This script combines multiple rendered images into contact sheets for
easy comparison across cases or fields.

Usage:
    python make_contact_sheets.py /path/to/images [--output contact_sheet.png]
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL not available. Install with: pip install Pillow")


def find_images(images_dir: Path, pattern: str = "*.png") -> List[Path]:
    """Find all images matching pattern."""
    return sorted(images_dir.glob(pattern))


def create_contact_sheet(
    images: List[Path],
    output_file: Path,
    cols: int = 4,
    thumb_size: Tuple[int, int] = (480, 270),
    padding: int = 10,
    title: str = None
):
    """Create a contact sheet from multiple images."""
    if not PIL_AVAILABLE:
        print("ERROR: PIL not available")
        return 1
    
    if not images:
        print("No images to process")
        return 1
    
    # Calculate grid dimensions
    n_images = len(images)
    rows = (n_images + cols - 1) // cols
    
    # Calculate sheet size
    sheet_width = cols * thumb_size[0] + (cols + 1) * padding
    sheet_height = rows * thumb_size[1] + (rows + 1) * padding
    
    if title:
        sheet_height += 40  # Space for title
    
    # Create sheet
    sheet = Image.new('RGB', (sheet_width, sheet_height), 'white')
    draw = ImageDraw.Draw(sheet)
    
    # Add title
    y_offset = 0
    if title:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except:
            font = ImageFont.load_default()
        draw.text((padding, padding), title, fill='black', font=font)
        y_offset = 40
    
    # Add images
    for i, img_path in enumerate(images):
        row = i // cols
        col = i % cols
        
        x = padding + col * (thumb_size[0] + padding)
        y = y_offset + padding + row * (thumb_size[1] + padding)
        
        try:
            img = Image.open(img_path)
            img.thumbnail(thumb_size, Image.Resampling.LANCZOS)
            
            # Center in cell
            x_offset = (thumb_size[0] - img.width) // 2
            y_offset_img = (thumb_size[1] - img.height) // 2
            
            sheet.paste(img, (x + x_offset, y + y_offset_img))
            
            # Add label
            label = img_path.stem
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
            except:
                font = ImageFont.load_default()
            draw.text((x, y + thumb_size[1] - 15), label[:40], fill='black', font=font)
            
        except Exception as e:
            print(f"  Warning: Could not process {img_path}: {e}")
    
    # Save
    sheet.save(output_file)
    print(f"Created contact sheet: {output_file}")
    return 0


def create_field_comparison(images_dir: Path, output_dir: Path, field: str):
    """Create contact sheet comparing one field across all views."""
    images = find_images(images_dir, f"*_{field}.png")
    if images:
        output_file = output_dir / f"comparison_{field}.png"
        create_contact_sheet(images, output_file, title=f"Field: {field}")


def create_view_comparison(images_dir: Path, output_dir: Path, view: str):
    """Create contact sheet comparing one view across all fields."""
    images = find_images(images_dir, f"*_{view}_*.png")
    if images:
        output_file = output_dir / f"comparison_{view}.png"
        create_contact_sheet(images, output_file, title=f"View: {view}")


def main():
    parser = argparse.ArgumentParser(
        description="Create contact sheets from rendered images"
    )
    parser.add_argument("images_dir", type=str, help="Directory containing images")
    parser.add_argument("--output", "-o", type=str, help="Output directory")
    parser.add_argument("--by-field", action="store_true", help="Group by field")
    parser.add_argument("--by-view", action="store_true", help="Group by view")
    parser.add_argument("--all", action="store_true", help="Create all contact sheets")
    
    args = parser.parse_args()
    
    images_dir = Path(args.images_dir).resolve()
    output_dir = Path(args.output).resolve() if args.output else images_dir / "contact_sheets"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not images_dir.exists():
        print(f"ERROR: Images directory not found: {images_dir}")
        return 1
    
    # Find all images
    all_images = find_images(images_dir)
    print(f"Found {len(all_images)} images")
    
    if args.all or (not args.by_field and not args.by_view):
        # Create one big contact sheet
        output_file = output_dir / "contact_sheet_all.png"
        create_contact_sheet(all_images, output_file, title="All Images")
    
    if args.by_field or args.all:
        # Extract unique fields
        fields = set()
        for img in all_images:
            parts = img.stem.split('_')
            if len(parts) >= 3:
                fields.add(parts[-1])
        
        for field in fields:
            create_field_comparison(images_dir, output_dir, field)
    
    if args.by_view or args.all:
        # Extract unique views
        views = set()
        for img in all_images:
            parts = img.stem.split('_')
            if len(parts) >= 3:
                views.add(parts[-2])
        
        for view in views:
            create_view_comparison(images_dir, output_dir, view)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
