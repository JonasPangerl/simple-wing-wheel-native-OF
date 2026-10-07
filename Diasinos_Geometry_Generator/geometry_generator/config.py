"""
Geometry configuration and constants from Diasinos et al. literature.

All dimensions are normalized by chord (c) unless otherwise specified.
Sub-scale model: c = 75mm
"""

from dataclasses import dataclass, field
from typing import List, Optional
import yaml
from pathlib import Path


@dataclass
class GeometryConfig:
    """Configuration for wing and wheel geometry generation."""
    
    # Reference dimension
    chord: float = 75.0  # mm
    
    # Wing parameters (NACA 4412 inverted)
    # From literature: single-element wing, no taper/sweep
    
    # Endplate parameters (normalized by chord)
    endplate_length: float = 1.21        # 1.21c total length (EP LE to EP TE)
    endplate_height: float = 0.413       # 0.413c total height
    endplate_thickness: float = 0.04     # 0.04c width/thickness
    endplate_below_wing: float = 0.04    # 0.04c below wing lowest point
    endplate_chamfer_length: float = 0.11  # 0.11c chamfer at TE
    
    # Absolute x-positions (normalized by chord, wheel center at x=0)
    # These are the reference positions from the diagram
    endplate_le_x: float = -1.882        # EP LE x-position (including LE radius)
    endplate_te_x: float = -0.672        # EP TE x-position
    wing_rotation_x: float = -1.472      # Wing rotation point x-position
    
    # Wing rotation point offset from wing LE (at AOA=0)
    wing_rotation_from_le: float = 0.35  # 0.35c behind wing LE (in x at AOA=0)
    
    # Wheel parameters (normalized by chord)
    wheel_diameter: float = 1.17        # 1.17c = 87.75mm at c=75mm
    wheel_shoulder_radius: float = 0.067  # 0.067c = 5mm
    
    # Fixed positioning (normalized by chord)
    # T is the distance from centerline (y=0) to the OUTER surface of the wheel
    wheel_track_outer: float = 1.6        # T/c = 1.6 (wheel outer surface y-position)
    gap_endplate_wheel: float = 0.087   # 0.087c gap between endplate and wheel
    
    # Variable parameters (can be overridden)
    span: float = 1.42                  # S/c default
    ride_height: float = 0.13           # h/c default
    angle_of_attack: float = 8.0        # degrees default
    wheel_width: float = 0.63           # W/c default
    
    # Trailing edge
    trailing_edge_thickness: float = 1.0  # mm (absolute, not normalized)
    
    # Plinth parameters (absolute mm)
    plinth_cut_height: float = 0.5      # mm above ground to intersect wheel
    plinth_depth: float = 6.0           # mm below ground (z=0)

    # --- Wheel tessellation ------------------------------------------------
    # Facet size has to be at least as fine as the CFD cell, otherwise
    # snappyHexMesh snaps to the facets and the prism layers get squeezed by
    # them. The RANS setup uses a 0.293 mm cell on the wheel (level 6), and
    # the circumference at R = 43.875 mm is 275.7 mm, so:
    #     900 segments -> 0.306 mm facets
    # The original value of 180 gave 1.53 mm, five times coarser than the
    # cell, which cost most of the layer coverage on the tread.
    wheel_circumferential_segments: int = 900

    # Across the shoulder quarter-circle (R = 0.067c = 5.0 mm, arc 7.9 mm).
    # 24 already gives 0.33 mm, which matches the cell size.
    wheel_shoulder_segments: int = 24
    
    # Airfoil data path
    airfoil_csv: str = "Documents/naca4412_75mmCord.csv"
    
    # Output directory
    output_dir: str = "./output"
    
    # Parameter sweep lists
    spans: List[float] = field(default_factory=lambda: [1.42])
    heights: List[float] = field(default_factory=lambda: [0.13])
    angles: List[float] = field(default_factory=lambda: [8.0])
    widths: List[float] = field(default_factory=lambda: [0.63])
    
    @property
    def wheel_radius(self) -> float:
        """Wheel radius normalized by chord."""
        return self.wheel_diameter / 2.0
    
    @property
    def wheel_radius_mm(self) -> float:
        """Wheel radius in mm."""
        return self.wheel_radius * self.chord
    
    @property
    def wheel_diameter_mm(self) -> float:
        """Wheel diameter in mm."""
        return self.wheel_diameter * self.chord
    
    def get_wheel_width_mm(self, width_c: Optional[float] = None) -> float:
        """Get wheel width in mm."""
        w = width_c if width_c is not None else self.wheel_width
        return w * self.chord
    
    def get_span_mm(self, span_c: Optional[float] = None) -> float:
        """Get wing span in mm."""
        s = span_c if span_c is not None else self.span
        return s * self.chord
    
    def get_ride_height_mm(self, height_c: Optional[float] = None) -> float:
        """Get ride height in mm."""
        h = height_c if height_c is not None else self.ride_height
        return h * self.chord
    
    def get_endplate_position_y(self, span_c: Optional[float] = None) -> float:
        """
        Get endplate outer edge y-position in mm.
        The endplate is at the wing tip, so y = span.
        """
        return self.get_span_mm(span_c)
    
    def get_wheel_center_y_mm(self, width_c: Optional[float] = None) -> float:
        """Get wheel center y-position in mm.
        
        T (wheel_track_outer) is distance to outer surface.
        Center = T - W/2
        """
        w = width_c if width_c is not None else self.wheel_width
        return (self.wheel_track_outer - w / 2) * self.chord
    
    def get_wing_te_x_mm(self) -> float:
        """
        Get wing trailing edge x-position in mm.
        From diagram: wing TE is at x = -(0.11c + 0.087c + wheel_radius)
        Wheel center is at x=0.
        """
        # Distance from wheel center to wing TE
        # = gap to wheel front + wheel radius + small gap
        distance = self.wing_te_to_wheel_x + self.gap_endplate_wheel + self.wheel_radius
        return -distance * self.chord
    
    def get_wing_le_x_mm(self) -> float:
        """Get wing leading edge x-position in mm."""
        return self.get_wing_te_x_mm() - self.chord
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> "GeometryConfig":
        """Load configuration from YAML file."""
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
        
        config = cls()
        
        # Update with values from YAML
        if 'chord' in data:
            config.chord = float(data['chord'])
        if 'spans' in data:
            config.spans = [float(x) for x in data['spans']]
        if 'heights' in data:
            config.heights = [float(x) for x in data['heights']]
        if 'angles' in data:
            config.angles = [float(x) for x in data['angles']]
        if 'widths' in data:
            config.widths = [float(x) for x in data['widths']]
        if 'trailing_edge_thickness' in data:
            config.trailing_edge_thickness = float(data['trailing_edge_thickness'])
        if 'plinth_cut_height' in data:
            config.plinth_cut_height = float(data['plinth_cut_height'])
        if 'plinth_depth' in data:
            config.plinth_depth = float(data['plinth_depth'])
        if 'wheel_circumferential_segments' in data:
            config.wheel_circumferential_segments = int(
                data['wheel_circumferential_segments'])
        if 'wheel_shoulder_segments' in data:
            config.wheel_shoulder_segments = int(
                data['wheel_shoulder_segments'])
        if 'airfoil_csv' in data:
            config.airfoil_csv = data['airfoil_csv']
        if 'output_dir' in data:
            config.output_dir = data['output_dir']
            
        return config
    
    def to_yaml(self, yaml_path: str) -> None:
        """Save configuration to YAML file."""
        data = {
            'spans': self.spans,
            'heights': self.heights,
            'angles': self.angles,
            'widths': self.widths,
            'trailing_edge_thickness': self.trailing_edge_thickness,
            'chord': self.chord,
            'plinth_cut_height': self.plinth_cut_height,
            'plinth_depth': self.plinth_depth,
            'output_dir': self.output_dir,
        }
        with open(yaml_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
