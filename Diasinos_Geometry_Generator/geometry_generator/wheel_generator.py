"""
Wheel geometry generator.

Generates STL surfaces for:
- Tread (outer circumferential surface)
- Shoulders (rounded transitions on both sides)
- Sidewall (flat side faces)
- Plinth (contact patch curtain extending below ground)
"""

import numpy as np
from typing import Dict, Tuple, List
from pathlib import Path

from .config import GeometryConfig
from .utils import save_ascii_stl, save_multi_solid_stl


class WheelGenerator:
    """Generate wheel geometry with separate named surfaces."""
    
    def __init__(self, config: GeometryConfig):
        self.config = config
    
    def generate_surfaces(self, width_c: float) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """
        Generate all wheel surfaces for given width.
        
        The wheel is positioned with:
        - Center at x=0
        - Center at y=T (wheel track)
        - Center at z=radius (so bottom touches ground at z=0)
        
        Args:
            width_c: Wheel width normalized by chord (W/c)
            
        Returns:
            Dictionary mapping surface names to (vertices, faces) tuples
        """
        surfaces = {}
        
        # Get dimensions in mm
        radius = self.config.wheel_radius * self.config.chord
        width = width_c * self.config.chord
        shoulder_radius = self.config.wheel_shoulder_radius * self.config.chord
        
        # Wheel center position
        # T (wheel_track_outer) is the distance from centerline to OUTER surface
        # So wheel center y = T - W/2
        y_outer = self.config.wheel_track_outer * self.config.chord
        y_center = y_outer - width / 2
        z_center = radius  # Center is at radius height (bottom at z=0)
        x_center = 0.0     # Wheel center at x=0
        
        # Generate each surface
        surfaces['tread'] = self._generate_tread(
            radius, width, shoulder_radius, x_center, y_center, z_center
        )
        surfaces['shoulders'] = self._generate_shoulders(
            radius, width, shoulder_radius, x_center, y_center, z_center
        )
        surfaces['sidewall'] = self._generate_sidewalls(
            radius, width, shoulder_radius, x_center, y_center, z_center
        )
        surfaces['plinth'] = self._generate_plinth(
            radius, width, shoulder_radius, x_center, y_center, z_center
        )
        
        return surfaces
    
    def _generate_tread(
        self,
        radius: float,
        width: float,
        shoulder_radius: float,
        x_center: float,
        y_center: float,
        z_center: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate the tread surface (outer circumference).
        
        The tread is the flat outer portion between the two shoulders.
        """
        # Tread width (excluding shoulders)
        tread_width = width - 2 * shoulder_radius
        
        # Y positions for tread edges
        y_inner = y_center - tread_width / 2
        y_outer = y_center + tread_width / 2
        
        # Circumferential segments. Must be fine enough that the facet is
        # not coarser than the CFD cell, or snappyHexMesh snaps to the
        # facets and the prism layers get squeezed. See config.py.
        n_circ = self.config.wheel_circumferential_segments
        
        # Generate circumferential points
        angles = np.linspace(0, 2 * np.pi, n_circ + 1)[:-1]  # Exclude duplicate at 2*pi
        
        # Vertices at inner and outer edges of tread
        vertices_inner = np.zeros((n_circ, 3))
        vertices_outer = np.zeros((n_circ, 3))
        
        for i, angle in enumerate(angles):
            x = x_center + radius * np.sin(angle)
            z = z_center + radius * np.cos(angle)
            
            vertices_inner[i] = [x, y_inner, z]
            vertices_outer[i] = [x, y_outer, z]
        
        vertices = np.vstack([vertices_inner, vertices_outer])
        
        # Create faces (quads as triangle pairs)
        faces = []
        for i in range(n_circ):
            i_next = (i + 1) % n_circ
            
            # Inner edge index: i
            # Outer edge index: i + n_circ
            v0 = i
            v1 = i_next
            v2 = i_next + n_circ
            v3 = i + n_circ
            
            # Two triangles per quad (normal pointing outward)
            faces.append([v0, v3, v2])
            faces.append([v0, v2, v1])
        
        return vertices, np.array(faces)
    
    def _generate_shoulders(
        self,
        radius: float,
        width: float,
        shoulder_radius: float,
        x_center: float,
        y_center: float,
        z_center: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate the shoulder surfaces (rounded transitions).
        
        Each shoulder is a quarter-torus connecting the tread to the sidewall.
        """
        # Tread width
        tread_width = width - 2 * shoulder_radius
        
        # Shoulder center positions (y)
        y_shoulder_inner = y_center - tread_width / 2
        y_shoulder_outer = y_center + tread_width / 2
        
        # Number of segments (see config.py for how these are chosen)
        n_circ = self.config.wheel_circumferential_segments
        n_shoulder = self.config.wheel_shoulder_segments
        
        # Generate angles
        circ_angles = np.linspace(0, 2 * np.pi, n_circ + 1)[:-1]
        shoulder_angles = np.linspace(0, np.pi / 2, n_shoulder + 1)  # 0 to 90 degrees
        
        all_vertices = []
        all_faces = []
        vertex_offset = 0
        
        # Generate both shoulders (inner and outer)
        for side in ['inner', 'outer']:
            if side == 'inner':
                y_shoulder_center = y_shoulder_inner
                y_direction = -1  # Shoulder curves inward (negative y)
            else:
                y_shoulder_center = y_shoulder_outer
                y_direction = 1   # Shoulder curves outward (positive y)
            
            # Generate vertices
            vertices = []
            for i, circ_angle in enumerate(circ_angles):
                # Direction from wheel center at this circumferential position
                dir_x = np.sin(circ_angle)
                dir_z = np.cos(circ_angle)
                
                for j, sh_angle in enumerate(shoulder_angles):
                    # Shoulder curve: starts at tread (sh_angle=0) and curves to sidewall (sh_angle=90)
                    # At sh_angle=0: point is at full radius, at tread edge
                    # At sh_angle=90: point is at (radius - shoulder_radius), at sidewall edge
                    
                    r_local = radius - shoulder_radius * (1 - np.cos(sh_angle))
                    y_offset = shoulder_radius * np.sin(sh_angle) * y_direction
                    
                    x = x_center + r_local * dir_x
                    z = z_center + r_local * dir_z
                    y = y_shoulder_center + y_offset
                    
                    vertices.append([x, y, z])
            
            vertices = np.array(vertices)
            
            # Create faces
            faces = []
            for i in range(n_circ):
                i_next = (i + 1) % n_circ
                
                for j in range(n_shoulder):
                    # Vertex indices in the grid
                    v00 = i * (n_shoulder + 1) + j
                    v01 = i * (n_shoulder + 1) + j + 1
                    v10 = i_next * (n_shoulder + 1) + j
                    v11 = i_next * (n_shoulder + 1) + j + 1
                    
                    # Adjust for vertex offset
                    v00 += vertex_offset
                    v01 += vertex_offset
                    v10 += vertex_offset
                    v11 += vertex_offset
                    
                    # Two triangles per quad
                    if side == 'inner':
                        # Normal pointing outward (away from wheel center)
                        faces.append([v00, v01, v11])
                        faces.append([v00, v11, v10])
                    else:
                        # Normal pointing outward
                        faces.append([v00, v11, v01])
                        faces.append([v00, v10, v11])
            
            all_vertices.append(vertices)
            all_faces.extend(faces)
            vertex_offset += len(vertices)
        
        combined_vertices = np.vstack(all_vertices)
        return combined_vertices, np.array(all_faces)
    
    def _generate_sidewalls(
        self,
        radius: float,
        width: float,
        shoulder_radius: float,
        x_center: float,
        y_center: float,
        z_center: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate the sidewall surfaces (flat side faces).
        
        The sidewalls are flat circular discs on each side of the wheel,
        from the shoulder inner edge to the center (fully closed, no hole).
        """
        # Sidewall outer radius (where shoulder ends)
        r_outer = radius - shoulder_radius
        
        # Y positions
        y_inner = y_center - width / 2
        y_outer = y_center + width / 2
        
        # Number of segments - must match the tread tessellation
        n_circ = self.config.wheel_circumferential_segments
        n_radial = 16  # More radial segments for better mesh
        
        circ_angles = np.linspace(0, 2 * np.pi, n_circ + 1)[:-1]
        # Radii from center (0) to outer edge - closed disc, no hole
        radii = np.linspace(0, r_outer, n_radial + 1)
        
        all_vertices = []
        all_faces = []
        vertex_offset = 0
        
        for side in ['inner', 'outer']:
            y_pos = y_inner if side == 'inner' else y_outer
            
            # Generate vertices - start with center point
            vertices = []
            
            # Center point first
            vertices.append([x_center, y_pos, z_center])
            
            # Then concentric rings from inner to outer
            for r in radii[1:]:  # Skip r=0, we already have center
                for angle in circ_angles:
                    x = x_center + r * np.sin(angle)
                    z = z_center + r * np.cos(angle)
                    vertices.append([x, y_pos, z])
            
            vertices = np.array(vertices)
            
            # Create faces
            faces = []
            
            # Center fan triangles (connecting center to first ring)
            center_idx = vertex_offset
            for j in range(n_circ):
                j_next = (j + 1) % n_circ
                v1 = vertex_offset + 1 + j  # First ring
                v2 = vertex_offset + 1 + j_next
                
                if side == 'inner':
                    # Normal pointing -y (inboard)
                    faces.append([center_idx, v2, v1])
                else:
                    # Normal pointing +y (outboard)
                    faces.append([center_idx, v1, v2])
            
            # Ring-to-ring quads
            for i in range(n_radial - 1):  # -1 because we handle center separately
                for j in range(n_circ):
                    j_next = (j + 1) % n_circ
                    
                    # Vertex indices (offset by 1 for center point)
                    v00 = vertex_offset + 1 + i * n_circ + j
                    v01 = vertex_offset + 1 + i * n_circ + j_next
                    v10 = vertex_offset + 1 + (i + 1) * n_circ + j
                    v11 = vertex_offset + 1 + (i + 1) * n_circ + j_next
                    
                    # Two triangles per quad
                    if side == 'inner':
                        # Normal pointing -y (inboard)
                        faces.append([v00, v10, v11])
                        faces.append([v00, v11, v01])
                    else:
                        # Normal pointing +y (outboard)
                        faces.append([v00, v11, v10])
                        faces.append([v00, v01, v11])
            
            all_vertices.append(vertices)
            all_faces.extend(faces)
            vertex_offset += len(vertices)
        
        combined_vertices = np.vstack(all_vertices)
        return combined_vertices, np.array(all_faces)
    
    def _generate_plinth(
        self,
        radius: float,
        width: float,
        shoulder_radius: float,
        x_center: float,
        y_center: float,
        z_center: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generate the contact patch plinth (tire curtain).
        
        Construction:
        1. Intersect wheel with horizontal plane at z = plinth_cut_height (0.5mm)
        2. The intersection is an ellipse-like closed curve
        3. Extend the plinth slightly upward (to ensure intersection with wheel)
        4. Extrude down to z = -plinth_depth
        5. Close the bottom face
        """
        cut_height = self.config.plinth_cut_height  # mm above ground (0.5mm)
        plinth_depth = self.config.plinth_depth     # mm below ground (6mm)
        
        z_cut = cut_height
        z_bottom = -plinth_depth
        # Extend top slightly above cut height to ensure intersection with wheel
        z_top = cut_height + 1.0  # 1mm above cut height
        
        # The wheel is a cylinder with rounded shoulders
        # At z = z_cut, we need to find the intersection curve
        
        dz = z_cut - z_center  # Distance from wheel center to cut plane (negative, below center)
        
        if abs(dz) >= radius:
            # Cut plane doesn't intersect wheel
            return np.array([]).reshape(0, 3), np.array([]).reshape(0, 3)
        
        # Y boundaries
        tread_width = width - 2 * shoulder_radius
        y_tread_inner = y_center - tread_width / 2
        y_tread_outer = y_center + tread_width / 2
        y_wheel_inner = y_center - width / 2
        y_wheel_outer = y_center + width / 2
        
        # For each y, calculate the effective radius considering shoulders
        def get_effective_radius(y):
            """Get the wheel radius at a given y position, accounting for shoulders."""
            if y < y_tread_inner:
                # Inner shoulder region
                dy = y_tread_inner - y
                if dy > shoulder_radius:
                    return 0  # Outside wheel
                # Shoulder is a quarter circle
                r_eff = radius - shoulder_radius + np.sqrt(max(0, shoulder_radius**2 - dy**2))
                return r_eff
            elif y > y_tread_outer:
                # Outer shoulder region
                dy = y - y_tread_outer
                if dy > shoulder_radius:
                    return 0  # Outside wheel
                r_eff = radius - shoulder_radius + np.sqrt(max(0, shoulder_radius**2 - dy**2))
                return r_eff
            else:
                # Tread region - full radius
                return radius
        
        # Generate the intersection curve by sampling around the contact patch
        # Use more points for better accuracy
        n_y = 60  # Points along y direction
        y_values = np.linspace(y_wheel_inner, y_wheel_outer, n_y)
        
        curve_points = []
        
        # Front edge (negative x) - from inner to outer
        for y in y_values:
            r_eff = get_effective_radius(y)
            if r_eff > 0 and abs(dz) < r_eff:
                x = -np.sqrt(r_eff**2 - dz**2)
                curve_points.append([x_center + x, y, z_cut])
        
        # Back edge (positive x) - from outer to inner
        for y in reversed(y_values):
            r_eff = get_effective_radius(y)
            if r_eff > 0 and abs(dz) < r_eff:
                x = np.sqrt(r_eff**2 - dz**2)
                curve_points.append([x_center + x, y, z_cut])
        
        if len(curve_points) < 4:
            return np.array([]).reshape(0, 3), np.array([]).reshape(0, 3)
        
        curve_points = np.array(curve_points)
        
        # Smooth the curve using spline interpolation with moderate smoothing
        from scipy.interpolate import splprep, splev
        
        try:
            # Calculate a reasonable smoothing factor based on curve size
            curve_length = np.sum(np.sqrt(np.sum(np.diff(curve_points[:, :2], axis=0)**2, axis=1)))
            # Use smaller smoothing to stay closer to actual intersection
            smoothing_factor = curve_length * 0.005  # 0.5% of curve length
            
            # Parametric spline for closed curve with smoothing
            tck, u = splprep([curve_points[:, 0], curve_points[:, 1]], s=smoothing_factor, k=3, per=True)
            
            # Resample with more points for smoothness
            n_smooth = 120
            u_new = np.linspace(0, 1, n_smooth, endpoint=False)
            x_smooth, y_smooth = splev(u_new, tck)
            
            curve_x = x_smooth
            curve_y = y_smooth
            n_curve = n_smooth
        except Exception as e:
            # If spline fails, use original points
            print(f"Plinth spline smoothing failed: {e}")
            curve_x = curve_points[:, 0]
            curve_y = curve_points[:, 1]
            n_curve = len(curve_points)
        
        # Create vertices: top curve + bottom curve
        # Top is extended above cut height to ensure intersection
        vertices_top = np.column_stack([curve_x, curve_y, np.full(n_curve, z_top)])
        vertices_bottom = np.column_stack([curve_x, curve_y, np.full(n_curve, z_bottom)])
        
        # Center point for bottom cap
        center_x = np.mean(curve_x)
        center_y = np.mean(curve_y)
        center_bottom = np.array([[center_x, center_y, z_bottom]])
        
        vertices = np.vstack([vertices_top, vertices_bottom, center_bottom])
        
        # Indices:
        # 0 to n_curve-1: top curve
        # n_curve to 2*n_curve-1: bottom curve
        # 2*n_curve: center bottom
        
        faces = []
        
        # Side faces (vertical walls) - closed loop
        for i in range(n_curve):
            i_next = (i + 1) % n_curve
            v_top_0 = i
            v_top_1 = i_next
            v_bot_0 = n_curve + i
            v_bot_1 = n_curve + i_next
            
            # Two triangles per quad, normals pointing outward
            faces.append([v_top_0, v_bot_0, v_bot_1])
            faces.append([v_top_0, v_bot_1, v_top_1])
        
        # Bottom cap (fan triangulation from center)
        center_idx = 2 * n_curve
        for i in range(n_curve):
            i_next = (i + 1) % n_curve
            v0 = n_curve + i
            v1 = n_curve + i_next
            # Normal pointing down (-z)
            faces.append([center_idx, v1, v0])
        
        return vertices, np.array(faces)
    
    def save_surfaces(
        self,
        surfaces: Dict[str, Tuple[np.ndarray, np.ndarray]],
        output_dir: str,
        prefix: str = ""
    ) -> None:
        """
        Save all surfaces as a single ASCII STL file with multiple named solids.
        
        Args:
            surfaces: Dictionary of surface name -> (vertices, faces)
            output_dir: Output directory path
            prefix: Prefix for the filename and solid names
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Create single STL file with all surfaces as named solids
        filename = f"{prefix}wheel.stl" if prefix else "wheel.stl"
        filepath = output_path / filename
        
        save_multi_solid_stl(surfaces, str(filepath), name_prefix="wheel-")
