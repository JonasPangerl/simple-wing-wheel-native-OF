"""
3D preview visualization for wing and wheel geometry.

Uses matplotlib to display:
- Wing surfaces (color-coded)
- Wheel surfaces (color-coded)
- Ground plane reference
- Coordinate axes
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from typing import Dict, Tuple, Optional

from .config import GeometryConfig
from .wing_generator import WingGenerator
from .wheel_generator import WheelGenerator


# Color scheme for different surfaces
SURFACE_COLORS = {
    # Wing surfaces
    'suction': '#1f77b4',      # Blue - suction side
    'pressure': '#d62728',     # Red - pressure side
    'TE': '#ff7f0e',           # Orange - trailing edge
    'endplate': '#2ca02c',     # Green - endplate
    'endplate_TE': '#9467bd',  # Purple - endplate TE
    
    # Wheel surfaces
    'tread': '#7f7f7f',        # Gray - tread
    'shoulders': '#8c564b',    # Brown - shoulders
    'sidewall': '#e377c2',     # Pink - sidewall
    'plinth': '#bcbd22',       # Yellow-green - plinth
    
    # Reference
    'ground': '#17becf',       # Cyan - ground plane
}


def preview_wing_wheel(
    span: float,
    height: float,
    angle: float,
    width: float,
    config: GeometryConfig
) -> None:
    """
    Display 3D preview of wing and wheel geometry.
    
    Args:
        span: S/c value
        height: h/c value
        angle: AOA in degrees
        width: W/c value
        config: GeometryConfig instance
    """
    # Generate geometries
    wing_gen = WingGenerator(config)
    wheel_gen = WheelGenerator(config)
    
    wing_surfaces = wing_gen.generate_surfaces(span, height, angle)
    wheel_surfaces = wheel_gen.generate_surfaces(width)
    
    # Create figure
    fig = plt.figure(figsize=(14, 10))
    ax = fig.add_subplot(111, projection='3d')
    
    # Plot wing surfaces
    for name, (vertices, faces) in wing_surfaces.items():
        if len(vertices) == 0:
            continue
        plot_surface(ax, vertices, faces, SURFACE_COLORS.get(name, '#333333'), 
                    alpha=0.7, label=f'Wing: {name}')
    
    # Plot wheel surfaces
    for name, (vertices, faces) in wheel_surfaces.items():
        if len(vertices) == 0:
            continue
        plot_surface(ax, vertices, faces, SURFACE_COLORS.get(name, '#333333'),
                    alpha=0.7, label=f'Wheel: {name}')
    
    # Add ground plane
    add_ground_plane(ax, config)
    
    # Set labels and title
    ax.set_xlabel('X (mm) - Streamwise')
    ax.set_ylabel('Y (mm) - Spanwise')
    ax.set_zlabel('Z (mm) - Vertical')
    
    title = f'Wing & Wheel Preview\n'
    title += f'S/c={span:.2f}, h/c={height:.2f}, AOA={angle:.1f}°, W/c={width:.2f}'
    ax.set_title(title)
    
    # Set equal aspect ratio
    set_axes_equal(ax)
    
    # Add legend
    ax.legend(loc='upper left', fontsize=8)
    
    # Set view angle
    ax.view_init(elev=20, azim=-60)
    
    plt.tight_layout()
    plt.show()


def plot_surface(
    ax: Axes3D,
    vertices: np.ndarray,
    faces: np.ndarray,
    color: str,
    alpha: float = 0.7,
    label: str = None
) -> None:
    """
    Plot a triangulated surface on 3D axes.
    
    Args:
        ax: Matplotlib 3D axes
        vertices: Nx3 array of vertex coordinates
        faces: Mx3 array of face indices
        color: Face color
        alpha: Transparency (0-1)
        label: Legend label
    """
    # Create polygon collection
    triangles = []
    for face in faces:
        triangle = [vertices[face[0]], vertices[face[1]], vertices[face[2]]]
        triangles.append(triangle)
    
    collection = Poly3DCollection(
        triangles,
        facecolors=color,
        edgecolors='k',
        linewidths=0.1,
        alpha=alpha
    )
    
    ax.add_collection3d(collection)
    
    # Add invisible point for legend
    if label:
        ax.scatter([], [], [], c=color, label=label, s=50)


def add_ground_plane(ax: Axes3D, config: GeometryConfig) -> None:
    """Add a semi-transparent ground plane at z=0."""
    # Determine extent based on geometry
    chord = config.chord
    
    # Ground plane extent
    x_min = -2.5 * chord
    x_max = 1.5 * chord
    y_min = -0.2 * chord
    y_max = 2.0 * chord
    
    # Create ground plane vertices
    ground_verts = [
        [x_min, y_min, 0],
        [x_max, y_min, 0],
        [x_max, y_max, 0],
        [x_min, y_max, 0]
    ]
    
    # Plot as polygon
    ground = Poly3DCollection(
        [ground_verts],
        facecolors=SURFACE_COLORS['ground'],
        edgecolors='k',
        linewidths=1,
        alpha=0.3
    )
    ax.add_collection3d(ground)
    
    # Add grid lines on ground
    n_lines = 10
    x_lines = np.linspace(x_min, x_max, n_lines)
    y_lines = np.linspace(y_min, y_max, n_lines)
    
    for x in x_lines:
        ax.plot([x, x], [y_min, y_max], [0, 0], 'k-', alpha=0.2, linewidth=0.5)
    for y in y_lines:
        ax.plot([x_min, x_max], [y, y], [0, 0], 'k-', alpha=0.2, linewidth=0.5)


def set_axes_equal(ax: Axes3D) -> None:
    """
    Set equal aspect ratio for 3D plot.
    
    This ensures the geometry isn't distorted.
    """
    # Get current limits
    x_limits = ax.get_xlim3d()
    y_limits = ax.get_ylim3d()
    z_limits = ax.get_zlim3d()
    
    # Calculate ranges
    x_range = abs(x_limits[1] - x_limits[0])
    y_range = abs(y_limits[1] - y_limits[0])
    z_range = abs(z_limits[1] - z_limits[0])
    
    # Find the maximum range
    max_range = max(x_range, y_range, z_range)
    
    # Calculate centers
    x_middle = np.mean(x_limits)
    y_middle = np.mean(y_limits)
    z_middle = np.mean(z_limits)
    
    # Set new limits
    ax.set_xlim3d([x_middle - max_range/2, x_middle + max_range/2])
    ax.set_ylim3d([y_middle - max_range/2, y_middle + max_range/2])
    ax.set_zlim3d([z_middle - max_range/2, z_middle + max_range/2])


def preview_wing_only(
    span: float,
    height: float,
    angle: float,
    config: GeometryConfig
) -> None:
    """Preview only the wing geometry."""
    wing_gen = WingGenerator(config)
    wing_surfaces = wing_gen.generate_surfaces(span, height, angle)
    
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    for name, (vertices, faces) in wing_surfaces.items():
        if len(vertices) == 0:
            continue
        plot_surface(ax, vertices, faces, SURFACE_COLORS.get(name, '#333333'),
                    alpha=0.7, label=name)
    
    add_ground_plane(ax, config)
    
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_zlabel('Z (mm)')
    ax.set_title(f'Wing Preview: S/c={span:.2f}, h/c={height:.2f}, AOA={angle:.1f}°')
    
    set_axes_equal(ax)
    ax.legend()
    ax.view_init(elev=20, azim=-60)
    
    plt.tight_layout()
    plt.show()


def preview_wheel_only(
    width: float,
    config: GeometryConfig
) -> None:
    """Preview only the wheel geometry."""
    wheel_gen = WheelGenerator(config)
    wheel_surfaces = wheel_gen.generate_surfaces(width)
    
    fig = plt.figure(figsize=(12, 8))
    ax = fig.add_subplot(111, projection='3d')
    
    for name, (vertices, faces) in wheel_surfaces.items():
        if len(vertices) == 0:
            continue
        plot_surface(ax, vertices, faces, SURFACE_COLORS.get(name, '#333333'),
                    alpha=0.7, label=name)
    
    add_ground_plane(ax, config)
    
    ax.set_xlabel('X (mm)')
    ax.set_ylabel('Y (mm)')
    ax.set_zlabel('Z (mm)')
    ax.set_title(f'Wheel Preview: W/c={width:.2f}')
    
    set_axes_equal(ax)
    ax.legend()
    ax.view_init(elev=20, azim=-60)
    
    plt.tight_layout()
    plt.show()
