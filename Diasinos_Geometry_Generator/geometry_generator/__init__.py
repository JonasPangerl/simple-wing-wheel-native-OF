"""
Wing and Wheel STL Geometry Generator

Generate parametric STL files of NACA 4412 wing (with endplate) and wheel geometry
based on Diasinos et al. literature for CFD studies.
"""

from .config import GeometryConfig
from .wing_generator import WingGenerator
from .wheel_generator import WheelGenerator
from .generate import generate_from_config, preview_geometry

__version__ = "1.0.0"
__all__ = [
    "GeometryConfig",
    "WingGenerator", 
    "WheelGenerator",
    "generate_from_config",
    "preview_geometry",
]
