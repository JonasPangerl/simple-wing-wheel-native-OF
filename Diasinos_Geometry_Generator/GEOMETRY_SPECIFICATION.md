# Wing and Wheel Geometry Specification

Based on Diasinos et al. literature and Figure 2 diagram.

## Coordinate System

- **X**: Streamwise, positive downstream. Wheel center at x=0.
- **Y**: Spanwise, positive outboard from symmetry plane (y=0).
- **Z**: Vertical, positive upward. Ground plane at z=0.

## Reference Dimension

- **Chord (c)**: 75mm (sub-scale model)

---

## Wing Geometry

### Airfoil Profile
- **Type**: NACA 4412, inverted for downforce
- **Orientation**: Suction side (lower surface) faces down (negative Z)
- **Data**: CSV provides coordinates already in downforce configuration
  - Negative Y values = suction side (becomes negative Z in 3D)
  - Positive Y values = pressure side (becomes positive Z in 3D)

### Airfoil Processing
1. Load full airfoil contour as single continuous curve (TE → LE → TE)
2. Apply spline smoothing to entire contour for C2 continuity
3. Split into suction and pressure surfaces at leading edge (x_min)
4. Apply blunt trailing edge modification (0.5mm thickness)

### Wing Rotation Point
- Located at **0.35c behind the leading edge** of the wing (corrected from 0.45c in paper)
- In wing-local coordinates: x_rot = 0.35c from LE
- Note: 0.45c would cause wing to protrude past endplate LE

### Wing Positioning
All x-positions are absolute, with wheel center at x=0.

- **Wing rotation point x**: -1.472c
- **Wing LE x (at AOA=0)**: rotation_pt - 0.35c = -1.822c
- **Wing TE x (at AOA=0)**: wing_LE + 1c = -0.822c

### Ride Height Constraint
- **Definition**: The lowest point of the wing is at height h above ground (z = h)
- The endplate bottom edge is 0.04c below the wing lowest point
- Therefore: z_ep_bottom = h - 0.04c
- This must be satisfied **after** applying angle of attack rotation
- **Calculation**: 
  1. Rotate wing by AOA around rotation point
  2. Find lowest z-coordinate on rotated wing
  3. Translate wing vertically so lowest point is at z = h

### Angle of Attack
- Wing rotates around the rotation point (0.45c from LE)
- Positive AOA: trailing edge moves UP, leading edge moves DOWN
- This increases the effective camber and downforce

---

## Endplate Geometry

### Dimensions (from Figure 2)
- **Total length**: 1.21c = 90.75mm
- **Height**: 0.413c = 30.975mm
- **Thickness (width)**: 0.04c = 3mm

### Positioning
All x-positions are absolute, with wheel center at x=0.

- **Endplate LE x-position**: -1.882c (including the LE radius)
- **Wing rotation point x**: -1.472c
- **Endplate TE x-position**: -0.672c
- **Endplate length**: 1.21c (from LE to TE)

### Endplate TE Chamfer
- Chamfer starts **0.11c ahead of the endplate trailing edge**
- Purpose: Thin the trailing edge of the endplate
- The chamfer tapers the thickness from full (0.04c) to a thin edge

### Endplate Leading Edge
- Rounded with radius = half thickness = 0.02c = 1.5mm

### Endplate Vertical Position
- Bottom edge: z_ep_bottom = h - 0.04c (where h is ride height parameter)
- Top edge: z_ep_top = z_ep_bottom + 0.413c
- The wing lowest point is 0.04c above z_ep_bottom

---

## Wheel Geometry

### Dimensions
- **Diameter**: 1.17c = 87.75mm
- **Width (W)**: Variable, baseline 0.63c = 47.25mm
- **Shoulder radius**: 0.067c = 5.025mm

### Positioning
- **Center x-position**: x = 0 (origin)
- **Center y-position**: y = T = 1.6c = 120mm (wheel track)
- **Center z-position**: z = radius = 0.585c = 43.875mm (bottom touches ground)

### Gap to Endplate
- Minimum gap between endplate and wheel: 0.087c = 6.525mm

---

## Variable Parameters

| Parameter | Symbol | Definition | Range | Default |
|-----------|--------|------------|-------|---------|
| Wing span | S | Half-span from symmetry to endplate outer edge | 0.97c - 1.6c | 1.42c |
| Ride height | h | Ground clearance parameter (see calculation) | 0.1c - 0.3c | 0.13c |
| Angle of attack | AOA | Wing rotation angle | 0° - 12° | 8° |
| Wheel width | W | Wheel width | 0.5c - 0.8c | 0.63c |

---

## Geometry Assembly Algorithm

### Step 1: Use Absolute X-Positions
All x-positions are defined absolutely (wheel center at x=0):
- Endplate LE: x = -1.882c
- Wing rotation point: x = -1.472c  
- Endplate TE: x = -0.672c
- Wing LE (at AOA=0): x = -1.822c (rotation_pt - 0.35c)
- Wing TE (at AOA=0): x = -0.822c

### Step 2: Apply Wing AOA and Find Lowest Point
1. Rotate wing profile by AOA around rotation point (in x-z plane)
2. Find the minimum z-coordinate of the rotated profile
3. This gives z_wing_min_local (relative to rotation point)

### Step 3: Set Ride Height
1. The ride height parameter h defines the wing's ground clearance
2. z_wing_min = h (the lowest point of wing is at height h above ground)
3. Calculate z_rot (rotation point z) such that after rotation, min z = h
4. z_rot = h - z_wing_min_local

### Step 4: Position Endplate Vertically
1. Endplate bottom is 0.04c below wing lowest point
2. z_ep_bottom = h - 0.04c
3. z_ep_top = z_ep_bottom + 0.413c

---

## Surface Definitions for CFD

### Wing Surfaces
- **suction**: Lower surface (negative z side)
- **pressure**: Upper surface (positive z side)  
- **TE**: Blunt trailing edge face

### Endplate Surfaces
- **endplate**: Main body (inner face, outer face, top, bottom, LE radius)
- **endplate_TE**: Trailing edge face (with chamfer)

### Wheel Surfaces
- **tread**: Outer circumferential surface
- **shoulders**: Rounded transitions
- **sidewall**: Flat side faces
- **plinth**: Contact patch curtain

---

## Key Relationships Summary

All x-positions are relative to wheel center at x=0.

```
ABSOLUTE X-POSITIONS (normalized by chord c):
Endplate LE x-position:     x_ep_le = -1.882c  (including LE radius)
Wing rotation point:        x_rot   = -1.472c
Endplate TE x-position:     x_ep_te = -0.672c

DERIVED X-POSITIONS (at AOA=0):
Wing LE:                    x_le = x_rot - 0.35c = -1.822c
Wing TE:                    x_te = x_le + 1c = -0.822c

VERTICAL POSITIONS:
Wing lowest point z:        z_wing_min = h (ride height parameter)
Endplate bottom:            z_ep_bottom = h - 0.04c
Endplate top:               z_ep_top = z_ep_bottom + 0.413c

VERIFICATION:
Endplate length:            x_ep_te - x_ep_le = -0.672c - (-1.882c) = 1.21c ✓
Rotation pt to EP TE:       x_ep_te - x_rot = -0.672c - (-1.472c) = 0.8c ✓
Wing LE behind EP LE:       x_le - x_ep_le = -1.822c - (-1.882c) = 0.06c ✓
```
