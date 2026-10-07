"""
Wing geometry generator.

Generates STL surfaces for:
- Suction surface (lower, generates downforce) - negative Z
- Pressure surface (upper) - positive Z
- Trailing edge (blunt face)
- Endplate (main body with rounded LE and chamfered TE)
- Endplate trailing edge

Coordinate system:
- X: streamwise (positive downstream), wheel center at x=0
- Y: spanwise (positive outboard from symmetry plane y=0)
- Z: vertical (positive up), ground at z=0
"""

import numpy as np
from typing import Dict, Tuple, Optional
from pathlib import Path

from .config import GeometryConfig
from .utils import (
    load_airfoil_coordinates,
    create_blunt_trailing_edge,
    save_ascii_stl,
    save_multi_solid_stl,
    rotate_points_2d,
)


class WingGenerator:
    """Generate wing geometry with separate named surfaces."""
    
    def __init__(self, config: GeometryConfig):
        self.config = config
        self._load_airfoil()
    
    def _load_airfoil(self) -> None:
        """Load and process airfoil coordinates."""
        # Load with smoothing applied to entire contour first
        # Use 300 points per surface for fine tessellation, especially at LE
        suction, pressure = load_airfoil_coordinates(self.config.airfoil_csv, num_points=300)
        
        # Apply blunt trailing edge
        self.suction_coords, self.pressure_coords, self.te_suction, self.te_pressure = \
            create_blunt_trailing_edge(suction, pressure, self.config.trailing_edge_thickness)
        
        self.chord = self.config.chord
    
    def generate_surfaces(
        self,
        span_c: float,
        height_c: float,
        aoa_deg: float
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Generate all wing surfaces for given parameters.
        
        Args:
            span_c: Wing half-span normalized by chord (S/c) - this is the endplate OUTER edge
            height_c: Ride height normalized by chord (h/c)
            aoa_deg: Angle of attack in degrees
            
        Returns:
            Dictionary mapping surface names to (vertices, faces) tuples
        """
        surfaces = {}
        
        # Convert to mm
        span_mm = span_c * self.chord  # Endplate outer edge position
        height_mm = height_c * self.chord
        
        # Wing tip is at the center of the endplate thickness (so wing and endplate overlap)
        ep_thickness = self.config.endplate_thickness * self.chord
        wing_tip_y = span_mm - ep_thickness / 2  # y_center of endplate
        
        # Calculate wing and endplate positions
        positions = self._calculate_positions(height_mm, aoa_deg)
        
        # Generate wing surfaces (tip at endplate center, not outer edge)
        surfaces['suction'] = self._generate_suction_surface(wing_tip_y, positions, aoa_deg)
        surfaces['pressure'] = self._generate_pressure_surface(wing_tip_y, positions, aoa_deg)
        surfaces['TE'] = self._generate_te_surface(wing_tip_y, positions, aoa_deg)
        
        # Generate endplate surfaces (uses span_mm = outer edge)
        endplate_surfaces = self._generate_endplate_surfaces(span_mm, positions)
        for name, surface_data in endplate_surfaces.items():
            surfaces[name] = surface_data
        
        return surfaces
    
    def _calculate_positions(self, height_mm: float, aoa_deg: float) -> dict:
        """
        Calculate all positioning based on the geometry specification.
        
        Reference positions (at AOA=0, wheel center at x=0):
        - Endplate LE x: -1.882c (including LE radius)
        - Wing rotation point x: -1.472c
        - Endplate TE x: -0.672c
        - Wing LE x: rotation_pt - 0.45c = -1.922c (at AOA=0)
        - Wing TE x: wing_LE + 1c = -0.922c (at AOA=0)
        
        Vertical positions:
        - Wing lowest point z: h (ride height, variable)
        - Endplate bottom z: h - 0.04c
        
        The wing rotates around the rotation point (x=-1.472c).
        At AOA=0, the rotation point is 0.45c behind the wing LE.
        After rotation, the wing's lowest point must be at height_mm.
        
        Returns dict with all calculated positions.
        """
        c = self.chord
        
        # Absolute x-positions from config (in mm)
        x_ep_le = self.config.endplate_le_x * c      # -1.882c
        x_ep_te = self.config.endplate_te_x * c      # -0.672c
        x_rot = self.config.wing_rotation_x * c       # -1.472c
        
        # Wing rotation point offset from LE (at AOA=0)
        rot_from_le = self.config.wing_rotation_from_le * c  # 0.45c
        
        # Wing LE and TE positions (at AOA=0, these are the reference positions)
        # At AOA=0: wing_LE_x = rotation_x - 0.45c
        x_wing_le_ref = x_rot - rot_from_le  # -1.922c at AOA=0
        x_wing_te_ref = x_wing_le_ref + c     # -0.922c at AOA=0
        
        # Endplate dimensions
        ep_length = x_ep_te - x_ep_le  # Should be ~1.21c
        ep_height = self.config.endplate_height * c  # 0.413c
        ep_thickness = self.config.endplate_thickness * c  # 0.04c
        ep_below_wing = self.config.endplate_below_wing * c  # 0.04c
        
        # Calculate vertical positions
        # The wing rotates around the rotation point
        # After rotation, the wing's lowest point must be at height_mm
        
        # Get wing profile in local coordinates (LE at origin)
        all_coords = np.vstack([self.suction_coords, self.pressure_coords])
        
        # Rotation point in local airfoil coords (0.45c from LE along chord)
        rot_local = np.array([rot_from_le, 0])
        
        # Rotate all points around rotation point
        # Positive AOA: TE goes up, LE goes down (increases downforce)
        rotated = rotate_points_2d(all_coords, aoa_deg, center=rot_local)
        
        # Find lowest point (most negative y in airfoil coords = lowest z in 3D)
        min_y_local = np.min(rotated[:, 1])
        
        # The rotation point z-position is set so that min_z = height_mm
        # In local coords after rotation: lowest point is at y = min_y_local
        # In 3D: z_lowest = z_rot + min_y_local = height_mm
        # So: z_rot = height_mm - min_y_local
        z_rot = height_mm - min_y_local
        
        # Endplate vertical positions
        # Endplate bottom is 0.04c below wing lowest point
        z_ep_bottom = height_mm - ep_below_wing
        z_ep_top = z_ep_bottom + ep_height
        
        return {
            'x_wing_le': x_wing_le_ref,  # Reference LE position (used for transform)
            'x_wing_te': x_wing_te_ref,  # Reference TE position
            'x_rot': x_rot,
            'z_rot': z_rot,
            'rot_from_le': rot_from_le,
            'x_ep_le': x_ep_le,
            'x_ep_te': x_ep_te,
            'z_ep_bottom': z_ep_bottom,
            'z_ep_top': z_ep_top,
            'ep_thickness': ep_thickness,
            'ep_length': abs(ep_length),  # Use absolute value
            'ep_height': ep_height,
        }
    
    def _transform_profile_to_3d(
        self,
        coords_2d: np.ndarray,
        y_pos: float,
        positions: dict,
        aoa_deg: float
    ) -> np.ndarray:
        """
        Transform 2D airfoil coordinates to 3D wing coordinates.
        
        Airfoil coords (from CSV, already in downforce config):
        - x: chordwise (0 at LE, positive towards TE)
        - y: vertical (negative = suction/down, positive = pressure/up)
        
        3D wing coords:
        - X: streamwise (negative upstream)
        - Y: spanwise (positive outboard)
        - Z: vertical (positive up)
        """
        # Rotation point in local airfoil coords
        rot_local = np.array([positions['rot_from_le'], 0])
        
        # Rotate by AOA around rotation point
        # Positive AOA: TE up, LE down
        rotated = rotate_points_2d(coords_2d, aoa_deg, center=rot_local)
        
        # Convert to 3D
        n_points = len(rotated)
        coords_3d = np.zeros((n_points, 3))
        
        # X: wing LE position + local x
        coords_3d[:, 0] = positions['x_wing_le'] + rotated[:, 0]
        # Y: spanwise position
        coords_3d[:, 1] = y_pos
        # Z: rotation point z + local y (after rotation)
        coords_3d[:, 2] = positions['z_rot'] + (rotated[:, 1] - 0)  # rot point is at y=0 in local
        
        return coords_3d
    
    def _generate_suction_surface(
        self,
        span_mm: float,
        positions: dict,
        aoa_deg: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Generate the suction (lower) surface of the wing."""
        # Extend root slightly past y=0 to ensure intersection with symmetry plane
        y_root = -2.0  # 2mm past symmetry plane
        
        profile_root = self._transform_profile_to_3d(self.suction_coords, y_root, positions, aoa_deg)
        profile_tip = self._transform_profile_to_3d(self.suction_coords, span_mm, positions, aoa_deg)
        
        n_points = len(self.suction_coords)
        vertices = np.vstack([profile_root, profile_tip])
        
        faces = []
        for i in range(n_points - 1):
            faces.append([i, n_points + i, n_points + i + 1])
            faces.append([i, n_points + i + 1, i + 1])
        
        return vertices, np.array(faces)
    
    def _generate_pressure_surface(
        self,
        span_mm: float,
        positions: dict,
        aoa_deg: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Generate the pressure (upper) surface of the wing."""
        # Extend root slightly past y=0 to ensure intersection with symmetry plane
        y_root = -2.0  # 2mm past symmetry plane
        
        profile_root = self._transform_profile_to_3d(self.pressure_coords, y_root, positions, aoa_deg)
        profile_tip = self._transform_profile_to_3d(self.pressure_coords, span_mm, positions, aoa_deg)
        
        n_points = len(self.pressure_coords)
        vertices = np.vstack([profile_root, profile_tip])
        
        faces = []
        for i in range(n_points - 1):
            faces.append([i, i + 1, n_points + i + 1])
            faces.append([i, n_points + i + 1, n_points + i])
        
        return vertices, np.array(faces)
    
    def _generate_te_surface(
        self,
        span_mm: float,
        positions: dict,
        aoa_deg: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Generate the blunt trailing edge surface."""
        # Extend root slightly past y=0 to ensure intersection with symmetry plane
        y_root = -2.0  # 2mm past symmetry plane
        
        te_suction_root = self._transform_profile_to_3d(
            self.te_suction.reshape(1, 2), y_root, positions, aoa_deg
        )[0]
        te_suction_tip = self._transform_profile_to_3d(
            self.te_suction.reshape(1, 2), span_mm, positions, aoa_deg
        )[0]
        te_pressure_root = self._transform_profile_to_3d(
            self.te_pressure.reshape(1, 2), y_root, positions, aoa_deg
        )[0]
        te_pressure_tip = self._transform_profile_to_3d(
            self.te_pressure.reshape(1, 2), span_mm, positions, aoa_deg
        )[0]
        
        vertices = np.array([
            te_suction_root,
            te_suction_tip,
            te_pressure_tip,
            te_pressure_root,
        ])
        
        faces = np.array([
            [0, 1, 2],
            [0, 2, 3]
        ])
        
        return vertices, faces
    
    def _generate_endplate_surfaces(
        self,
        span_mm: float,
        positions: dict
    ) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Generate endplate surfaces with rounded LE and chamfered TE.
        
        Surfaces are split for mesh refinement:
        - endplate_inner: Inner face (toward wing root)
        - endplate_outer: Outer face (toward wheel)
        - endplate_top: Top edge (including LE cap area)
        - endplate_bottom: Bottom edge (including LE cap area)
        - endplate_LE: Rounded leading edge (curved surface only)
        - endplate_TE: Trailing edge face
        """
        c = self.chord
        
        x_ep_le = positions['x_ep_le']
        x_ep_te = positions['x_ep_te']
        z_ep_bottom = positions['z_ep_bottom']
        z_ep_top = positions['z_ep_top']
        ep_thickness = positions['ep_thickness']
        
        # Chamfer starts 0.11c before TE
        chamfer_length = self.config.endplate_chamfer_length * c
        x_chamfer_start = x_ep_te - chamfer_length
        
        # LE radius
        le_radius = ep_thickness / 2
        x_flat_start = x_ep_le + le_radius
        
        # Y positions - S (span_mm) is the OUTER edge of the endplate (paper convention)
        y_outer = span_mm
        y_inner = span_mm - ep_thickness
        y_center = span_mm - ep_thickness / 2
        
        # Chamfer tapers thickness to thin edge
        chamfer_thickness_end = ep_thickness * 0.2  # Thin but not zero
        y_inner_te = y_center - chamfer_thickness_end / 2
        y_outer_te = y_center + chamfer_thickness_end / 2
        
        surfaces = {}
        
        # Number of points for LE curve
        n_le = 12
        le_angles = np.linspace(np.pi/2, -np.pi/2, n_le + 1)
        
        # ========== INNER FACE ==========
        # Main section + chamfer section
        v_inner = np.array([
            [x_flat_start, y_inner, z_ep_bottom],  # 0
            [x_chamfer_start, y_inner, z_ep_bottom],  # 1
            [x_chamfer_start, y_inner, z_ep_top],  # 2
            [x_flat_start, y_inner, z_ep_top],  # 3
            [x_ep_te, y_inner_te, z_ep_bottom],  # 4 (chamfer end)
            [x_ep_te, y_inner_te, z_ep_top],  # 5 (chamfer end)
        ])
        f_inner = np.array([
            [0, 2, 1], [0, 3, 2],  # Main section
            [1, 5, 4], [1, 2, 5],  # Chamfer section
        ])
        surfaces['endplate_inner'] = (v_inner, f_inner)
        
        # ========== OUTER FACE ==========
        v_outer = np.array([
            [x_flat_start, y_outer, z_ep_bottom],  # 0
            [x_chamfer_start, y_outer, z_ep_bottom],  # 1
            [x_chamfer_start, y_outer, z_ep_top],  # 2
            [x_flat_start, y_outer, z_ep_top],  # 3
            [x_ep_te, y_outer_te, z_ep_bottom],  # 4 (chamfer end)
            [x_ep_te, y_outer_te, z_ep_top],  # 5 (chamfer end)
        ])
        f_outer = np.array([
            [0, 1, 2], [0, 2, 3],  # Main section
            [1, 4, 5], [1, 5, 2],  # Chamfer section
        ])
        surfaces['endplate_outer'] = (v_outer, f_outer)
        
        # ========== TOP EDGE (including LE cap) ==========
        # This surface goes from the LE radius curve all the way to the TE
        vertices_top = []
        faces_top = []
        
        # LE curve at top (from inner to outer, following the radius)
        for angle in le_angles:
            y = y_center + le_radius * np.sin(angle)
            x = x_ep_le + le_radius * (1 - np.cos(angle))
            vertices_top.append([x, y, z_ep_top])
        
        # Add the flat section corners and chamfer end
        le_curve_end = len(vertices_top)  # n_le + 1 points
        vertices_top.append([x_flat_start, y_inner, z_ep_top])  # Inner edge at flat start
        vertices_top.append([x_chamfer_start, y_inner, z_ep_top])  # Inner edge at chamfer start
        vertices_top.append([x_ep_te, y_inner_te, z_ep_top])  # Inner edge at TE
        vertices_top.append([x_ep_te, y_outer_te, z_ep_top])  # Outer edge at TE
        vertices_top.append([x_chamfer_start, y_outer, z_ep_top])  # Outer edge at chamfer start
        vertices_top.append([x_flat_start, y_outer, z_ep_top])  # Outer edge at flat start
        
        # Indices for flat section vertices
        v_inner_flat = le_curve_end
        v_inner_chamfer = le_curve_end + 1
        v_inner_te = le_curve_end + 2
        v_outer_te = le_curve_end + 3
        v_outer_chamfer = le_curve_end + 4
        v_outer_flat = le_curve_end + 5
        
        # LE cap triangles (fan from center)
        # The LE curve goes from inner (angle=pi/2) to outer (angle=-pi/2)
        # First point (index 0) is at y_inner, last point (index n_le) is at y_outer
        center_top_idx = len(vertices_top)
        vertices_top.append([x_flat_start, y_center, z_ep_top])  # Center point for fan
        
        # Fan triangles for LE cap
        for i in range(n_le):
            faces_top.append([center_top_idx, i, i + 1])
        
        # Connect LE cap to flat section
        faces_top.append([center_top_idx, 0, v_inner_flat])  # Inner corner
        faces_top.append([center_top_idx, n_le, v_outer_flat])  # Outer corner
        faces_top.append([center_top_idx, v_inner_flat, v_outer_flat])  # Flat section near LE
        
        # Flat section triangles (from flat start to chamfer start)
        faces_top.append([v_inner_flat, v_inner_chamfer, v_outer_chamfer])
        faces_top.append([v_inner_flat, v_outer_chamfer, v_outer_flat])
        
        # Chamfer section triangles
        faces_top.append([v_inner_chamfer, v_inner_te, v_outer_te])
        faces_top.append([v_inner_chamfer, v_outer_te, v_outer_chamfer])
        
        surfaces['endplate_top'] = (np.array(vertices_top), np.array(faces_top))
        
        # ========== BOTTOM EDGE (including LE cap) ==========
        vertices_bottom = []
        faces_bottom = []
        
        # LE curve at bottom (from inner to outer, following the radius)
        for angle in le_angles:
            y = y_center + le_radius * np.sin(angle)
            x = x_ep_le + le_radius * (1 - np.cos(angle))
            vertices_bottom.append([x, y, z_ep_bottom])
        
        # Add the flat section corners and chamfer end
        le_curve_end_b = len(vertices_bottom)
        vertices_bottom.append([x_flat_start, y_inner, z_ep_bottom])
        vertices_bottom.append([x_chamfer_start, y_inner, z_ep_bottom])
        vertices_bottom.append([x_ep_te, y_inner_te, z_ep_bottom])
        vertices_bottom.append([x_ep_te, y_outer_te, z_ep_bottom])
        vertices_bottom.append([x_chamfer_start, y_outer, z_ep_bottom])
        vertices_bottom.append([x_flat_start, y_outer, z_ep_bottom])
        
        v_inner_flat_b = le_curve_end_b
        v_inner_chamfer_b = le_curve_end_b + 1
        v_inner_te_b = le_curve_end_b + 2
        v_outer_te_b = le_curve_end_b + 3
        v_outer_chamfer_b = le_curve_end_b + 4
        v_outer_flat_b = le_curve_end_b + 5
        
        center_bottom_idx = len(vertices_bottom)
        vertices_bottom.append([x_flat_start, y_center, z_ep_bottom])
        
        # Fan triangles for LE cap (reversed winding for bottom face)
        for i in range(n_le):
            faces_bottom.append([center_bottom_idx, i + 1, i])
        
        # Connect LE cap to flat section (reversed winding)
        faces_bottom.append([center_bottom_idx, v_inner_flat_b, 0])
        faces_bottom.append([center_bottom_idx, v_outer_flat_b, n_le])
        faces_bottom.append([center_bottom_idx, v_outer_flat_b, v_inner_flat_b])
        
        # Flat section triangles (reversed winding)
        faces_bottom.append([v_inner_flat_b, v_outer_chamfer_b, v_inner_chamfer_b])
        faces_bottom.append([v_inner_flat_b, v_outer_flat_b, v_outer_chamfer_b])
        
        # Chamfer section triangles (reversed winding)
        faces_bottom.append([v_inner_chamfer_b, v_outer_te_b, v_inner_te_b])
        faces_bottom.append([v_inner_chamfer_b, v_outer_chamfer_b, v_outer_te_b])
        
        surfaces['endplate_bottom'] = (np.array(vertices_bottom), np.array(faces_bottom))
        
        # ========== ROUNDED LEADING EDGE (curved surface only) ==========
        vertices_le = []
        faces_le = []
        
        # Bottom curve of LE
        le_bottom_start = 0
        for angle in le_angles:
            y = y_center + le_radius * np.sin(angle)
            x = x_ep_le + le_radius * (1 - np.cos(angle))
            vertices_le.append([x, y, z_ep_bottom])
        
        # Top curve of LE
        le_top_start = len(vertices_le)
        for angle in le_angles:
            y = y_center + le_radius * np.sin(angle)
            x = x_ep_le + le_radius * (1 - np.cos(angle))
            vertices_le.append([x, y, z_ep_top])
        
        # Curved surface (connecting bottom and top curves)
        for i in range(n_le):
            b0 = le_bottom_start + i
            b1 = le_bottom_start + i + 1
            t0 = le_top_start + i
            t1 = le_top_start + i + 1
            faces_le.append([b0, b1, t1])
            faces_le.append([b0, t1, t0])
        
        surfaces['endplate_LE'] = (np.array(vertices_le), np.array(faces_le))
        
        # ========== TRAILING EDGE FACE ==========
        v_te = np.array([
            [x_ep_te, y_inner_te, z_ep_bottom],
            [x_ep_te, y_outer_te, z_ep_bottom],
            [x_ep_te, y_outer_te, z_ep_top],
            [x_ep_te, y_inner_te, z_ep_top],
        ])
        f_te = np.array([[0, 1, 2], [0, 2, 3]])
        surfaces['endplate_TE'] = (v_te, f_te)
        
        return surfaces
    
    def save_surfaces(
        self,
        surfaces: Dict[str, Tuple[np.ndarray, np.ndarray]],
        output_dir: str,
        prefix: str = ""
    ) -> None:
        """Save all surfaces as a single ASCII STL file with multiple named solids."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"{prefix}wing.stl" if prefix else "wing.stl"
        filepath = output_path / filename
        
        save_multi_solid_stl(surfaces, str(filepath), name_prefix="wing-")
