"""
Utility functions for geometry generation.

Includes:
- Airfoil coordinate loading and processing
- Blunt trailing edge modification
- STL writing utilities
- Coordinate transformations
"""

import numpy as np
from pathlib import Path
from typing import Tuple, List, Dict, Optional
import csv


def load_airfoil_coordinates(csv_path: str, num_points: int = 300) -> Tuple[np.ndarray, np.ndarray]:
    """
    Load airfoil coordinates from CSV file, smooth the entire contour, then split.
    
    The CSV format from the provided file has:
    - Header info (Name, Chord, etc.)
    - "Airfoil surface" section with X(mm), Y(mm) coordinates
    - Data goes: TE (upper/pressure) -> LE -> TE (lower/suction)
    
    The CSV is already in downforce configuration:
    - First half (TE to LE): negative Y = suction side (pointing down)
    - Second half (LE to TE): positive Y = pressure side (pointing up)
    
    Processing:
    1. Load entire contour as one continuous curve
    2. Smooth the entire contour with spline interpolation
    3. Split at leading edge into suction and pressure surfaces
    
    Args:
        csv_path: Path to CSV file
        num_points: Number of points per surface after splitting (default 300 for fine tessellation)
    
    Returns:
        suction_coords: Array of (x, y) for suction surface (lower, negative y), LE to TE
        pressure_coords: Array of (x, y) for pressure surface (upper, positive y), LE to TE
    """
    x_coords = []
    y_coords = []
    
    with open(csv_path, 'r') as f:
        reader = csv.reader(f)
        in_airfoil_section = False
        
        for row in reader:
            if len(row) < 2:
                continue
            
            if row[0].strip() == "Airfoil surface":
                in_airfoil_section = True
                continue
            if row[0].strip() == "Camber line":
                in_airfoil_section = False
                continue
            if row[0].strip() == "X(mm)":
                continue
                
            if in_airfoil_section:
                try:
                    x = float(row[0])
                    y = float(row[1])
                    x_coords.append(x)
                    y_coords.append(y)
                except (ValueError, IndexError):
                    continue
    
    raw_coords = np.column_stack([x_coords, y_coords])
    
    # Smooth the ENTIRE contour first (this ensures C2 continuity at LE)
    smoothed_contour = _smooth_closed_contour(raw_coords, num_points * 2)
    
    # Find the leading edge (minimum x) on the smoothed contour
    le_idx = np.argmin(smoothed_contour[:, 0])
    
    # Split into suction and pressure
    # CSV order: TE(suction/neg-y) -> LE -> TE(pressure/pos-y)
    # So first half is suction (negative y), second half is pressure (positive y)
    suction_raw = smoothed_contour[:le_idx + 1]  # TE -> LE
    pressure_raw = smoothed_contour[le_idx:]      # LE -> TE
    
    # Reverse suction to go LE -> TE (same direction as pressure)
    suction_coords = suction_raw[::-1]
    pressure_coords = pressure_raw
    
    return suction_coords, pressure_coords


def _smooth_closed_contour(coords: np.ndarray, num_points: int) -> np.ndarray:
    """
    Smooth an airfoil contour using periodic spline interpolation.
    Uses cosine spacing to cluster points at leading edge for better resolution.
    
    Args:
        coords: Nx2 array of (x, y) coordinates forming a closed-ish contour
        num_points: Total number of output points
        
    Returns:
        Smoothed coordinates with cosine spacing (more points at LE)
    """
    from scipy.interpolate import splprep, splev
    
    # The contour goes TE -> LE -> TE, so it's nearly closed
    # We'll use a non-periodic spline but with careful handling
    
    if len(coords) < 4:
        return coords
    
    try:
        # Parametric spline - s=0 for interpolation (passes through all points)
        # k=3 for cubic spline (C2 continuous)
        tck, u = splprep([coords[:, 0], coords[:, 1]], s=0, k=3, per=False)
        
        # Cosine spacing: clusters points at both ends (TE) and middle (LE)
        # For airfoil: u=0 is TE(suction), u=0.5 is LE, u=1 is TE(pressure)
        theta = np.linspace(0, np.pi, num_points)
        u_new = 0.5 * (1 - np.cos(theta))  # 0 -> 1 with clustering at ends
        
        x_new, y_new = splev(u_new, tck)
        return np.column_stack([x_new, y_new])
        
    except Exception as e:
        print(f"Spline smoothing failed: {e}, using linear interpolation")
        # Fallback to linear if spline fails
        from scipy.interpolate import interp1d
        t = np.linspace(0, 1, len(coords))
        t_new = np.linspace(0, 1, num_points)
        x_interp = interp1d(t, coords[:, 0], kind='linear')
        y_interp = interp1d(t, coords[:, 1], kind='linear')
        return np.column_stack([x_interp(t_new), y_interp(t_new)])


def create_blunt_trailing_edge(
    suction_coords: np.ndarray,
    pressure_coords: np.ndarray,
    thickness_mm: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Modify airfoil coordinates to have a blunt trailing edge.
    
    Both surfaces go from LE (x=0) to TE (x=chord).
    Suction surface has negative y, pressure surface has positive y.
    
    Args:
        suction_coords: Suction surface coordinates (LE to TE), negative y
        pressure_coords: Pressure surface coordinates (LE to TE), positive y
        thickness_mm: Desired trailing edge thickness in mm
        
    Returns:
        new_suction: Modified suction surface coordinates
        new_pressure: Modified pressure surface coordinates
        te_suction_point: Suction side TE endpoint (x, y)
        te_pressure_point: Pressure side TE endpoint (x, y)
    """
    from scipy.interpolate import interp1d
    
    # Find the chord length (max x)
    chord = max(suction_coords[-1, 0], pressure_coords[-1, 0])
    
    # Create interpolation functions
    suction_interp = interp1d(suction_coords[:, 0], suction_coords[:, 1], 
                              kind='linear', fill_value='extrapolate')
    pressure_interp = interp1d(pressure_coords[:, 0], pressure_coords[:, 1],
                               kind='linear', fill_value='extrapolate')
    
    # Find where to cut to achieve desired TE thickness
    # Search from TE backwards
    x_search = np.linspace(chord * 0.90, chord, 200)
    
    cut_x = chord * 0.98  # Default
    for x in x_search[::-1]:  # Go from TE towards LE
        y_pressure = pressure_interp(x)
        y_suction = suction_interp(x)
        thickness = y_pressure - y_suction  # pressure is positive, suction is negative
        
        if thickness >= thickness_mm:
            cut_x = x
            break
    
    # Get the y values at cut position
    te_pressure_y = pressure_interp(cut_x)
    te_suction_y = suction_interp(cut_x)
    
    # Adjust to exact thickness by moving points symmetrically
    current_thickness = te_pressure_y - te_suction_y
    if current_thickness > 0:
        adjustment = (thickness_mm - current_thickness) / 2
        te_pressure_y += adjustment
        te_suction_y -= adjustment
    
    # Filter coordinates to only include points up to cut position
    new_suction = suction_coords[suction_coords[:, 0] <= cut_x].copy()
    new_pressure = pressure_coords[pressure_coords[:, 0] <= cut_x].copy()
    
    # Create TE points
    te_suction_point = np.array([cut_x, te_suction_y])
    te_pressure_point = np.array([cut_x, te_pressure_y])
    
    # Ensure the last point is the TE point
    if len(new_suction) == 0 or new_suction[-1, 0] < cut_x - 0.01:
        new_suction = np.vstack([new_suction, te_suction_point])
    else:
        new_suction[-1] = te_suction_point
        
    if len(new_pressure) == 0 or new_pressure[-1, 0] < cut_x - 0.01:
        new_pressure = np.vstack([new_pressure, te_pressure_point])
    else:
        new_pressure[-1] = te_pressure_point
    
    return new_suction, new_pressure, te_suction_point, te_pressure_point


def save_ascii_stl(vertices: np.ndarray, faces: np.ndarray, 
                   filepath: str, solid_name: str = "solid") -> None:
    """
    Save mesh as ASCII STL file with named solid.
    
    Args:
        vertices: Nx3 array of vertex coordinates
        faces: Mx3 array of face indices (triangles)
        filepath: Output file path
        solid_name: Name for the solid in STL file
    """
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w') as f:
        f.write(f"solid {solid_name}\n")
        
        for face in faces:
            # Get vertices for this face
            v0 = vertices[face[0]]
            v1 = vertices[face[1]]
            v2 = vertices[face[2]]
            
            # Calculate normal
            edge1 = v1 - v0
            edge2 = v2 - v0
            normal = np.cross(edge1, edge2)
            norm_length = np.linalg.norm(normal)
            if norm_length > 0:
                normal = normal / norm_length
            else:
                normal = np.array([0, 0, 1])
            
            f.write(f" facet normal {normal[0]} {normal[1]} {normal[2]}\n")
            f.write("  outer loop\n")
            f.write(f"   vertex {v0[0]} {v0[1]} {v0[2]}\n")
            f.write(f"   vertex {v1[0]} {v1[1]} {v1[2]}\n")
            f.write(f"   vertex {v2[0]} {v2[1]} {v2[2]}\n")
            f.write("  endloop\n")
            f.write(" endfacet\n")
        
        f.write(f"endsolid {solid_name}\n")


def save_multi_solid_stl(
    surfaces: Dict[str, Tuple[np.ndarray, np.ndarray]],
    filepath: str,
    name_prefix: str = ""
) -> None:
    """
    Save multiple surfaces as named solids in a single ASCII STL file.
    
    Args:
        surfaces: Dictionary of surface_name -> (vertices, faces)
        filepath: Output file path
        name_prefix: Prefix for solid names (e.g., "wing-" or "wheel-")
    """
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w') as f:
        for surface_name, (vertices, faces) in surfaces.items():
            if len(vertices) == 0 or len(faces) == 0:
                continue
                
            solid_name = f"{name_prefix}{surface_name}" if name_prefix else surface_name
            f.write(f"solid {solid_name}\n")
            
            for face in faces:
                # Get vertices for this face
                v0 = vertices[face[0]]
                v1 = vertices[face[1]]
                v2 = vertices[face[2]]
                
                # Calculate normal
                edge1 = v1 - v0
                edge2 = v2 - v0
                normal = np.cross(edge1, edge2)
                norm_length = np.linalg.norm(normal)
                if norm_length > 0:
                    normal = normal / norm_length
                else:
                    normal = np.array([0, 0, 1])
                
                f.write(f" facet normal {normal[0]} {normal[1]} {normal[2]}\n")
                f.write("  outer loop\n")
                f.write(f"   vertex {v0[0]} {v0[1]} {v0[2]}\n")
                f.write(f"   vertex {v1[0]} {v1[1]} {v1[2]}\n")
                f.write(f"   vertex {v2[0]} {v2[1]} {v2[2]}\n")
                f.write("  endloop\n")
                f.write(" endfacet\n")
            
            f.write(f"endsolid {solid_name}\n")


def rotate_points_2d(points: np.ndarray, angle_deg: float, 
                     center: np.ndarray = None) -> np.ndarray:
    """
    Rotate 2D points around a center point.
    
    Args:
        points: Nx2 array of (x, y) coordinates
        angle_deg: Rotation angle in degrees (positive = counterclockwise)
        center: Center of rotation (default: origin)
        
    Returns:
        Rotated points
    """
    if center is None:
        center = np.array([0, 0])
    
    angle_rad = np.radians(angle_deg)
    cos_a = np.cos(angle_rad)
    sin_a = np.sin(angle_rad)
    
    # Translate to origin
    translated = points - center
    
    # Rotate
    rotated = np.zeros_like(translated)
    rotated[:, 0] = translated[:, 0] * cos_a - translated[:, 1] * sin_a
    rotated[:, 1] = translated[:, 0] * sin_a + translated[:, 1] * cos_a
    
    # Translate back
    return rotated + center


def transform_mesh(vertices: np.ndarray, 
                   rotation_deg: float = 0,
                   rotation_axis: str = 'y',
                   rotation_center: np.ndarray = None,
                   translation: np.ndarray = None) -> np.ndarray:
    """
    Apply rotation and translation to 3D mesh vertices.
    
    Args:
        vertices: Nx3 array of vertex coordinates
        rotation_deg: Rotation angle in degrees
        rotation_axis: Axis to rotate around ('x', 'y', or 'z')
        rotation_center: Center of rotation (default: origin)
        translation: Translation vector [dx, dy, dz]
        
    Returns:
        Transformed vertices
    """
    result = vertices.copy()
    
    if rotation_center is None:
        rotation_center = np.array([0, 0, 0])
    
    if rotation_deg != 0:
        angle_rad = np.radians(rotation_deg)
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)
        
        # Translate to rotation center
        result = result - rotation_center
        
        # Build rotation matrix
        if rotation_axis == 'x':
            rot_matrix = np.array([
                [1, 0, 0],
                [0, cos_a, -sin_a],
                [0, sin_a, cos_a]
            ])
        elif rotation_axis == 'y':
            rot_matrix = np.array([
                [cos_a, 0, sin_a],
                [0, 1, 0],
                [-sin_a, 0, cos_a]
            ])
        else:  # z
            rot_matrix = np.array([
                [cos_a, -sin_a, 0],
                [sin_a, cos_a, 0],
                [0, 0, 1]
            ])
        
        result = result @ rot_matrix.T
        
        # Translate back
        result = result + rotation_center
    
    if translation is not None:
        result = result + translation
    
    return result


def create_triangulated_quad(p0: np.ndarray, p1: np.ndarray, 
                             p2: np.ndarray, p3: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create two triangles from four corner points (quad).
    
    Points should be in order: p0 -> p1 -> p2 -> p3 (counterclockwise for outward normal)
    
    Returns:
        vertices: 4x3 array
        faces: 2x3 array of indices
    """
    vertices = np.array([p0, p1, p2, p3])
    faces = np.array([
        [0, 1, 2],
        [0, 2, 3]
    ])
    return vertices, faces


def extrude_profile_to_surface(
    profile_2d: np.ndarray,
    y_start: float,
    y_end: float,
    close_ends: bool = False
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Extrude a 2D profile (x, z) along the y-axis to create a 3D surface.
    
    Args:
        profile_2d: Nx2 array of (x, z) coordinates
        y_start: Starting y position
        y_end: Ending y position
        close_ends: Whether to close the ends with caps
        
    Returns:
        vertices: Mx3 array of vertex coordinates
        faces: Kx3 array of face indices
    """
    n_points = len(profile_2d)
    
    # Create vertices at both y positions
    vertices_start = np.column_stack([
        profile_2d[:, 0],
        np.full(n_points, y_start),
        profile_2d[:, 1]
    ])
    
    vertices_end = np.column_stack([
        profile_2d[:, 0],
        np.full(n_points, y_end),
        profile_2d[:, 1]
    ])
    
    vertices = np.vstack([vertices_start, vertices_end])
    
    # Create faces connecting the two profiles
    faces = []
    for i in range(n_points - 1):
        # Two triangles per quad
        # Bottom-left, bottom-right, top-right
        faces.append([i, i + 1, n_points + i + 1])
        # Bottom-left, top-right, top-left
        faces.append([i, n_points + i + 1, n_points + i])
    
    faces = np.array(faces)
    
    return vertices, faces
