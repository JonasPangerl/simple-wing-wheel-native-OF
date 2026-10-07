# ============================================================================
# dump_camera.py - read the current camera out of an interactive ParaView session
#
# HOW TO USE
#   1. Open the case in the ParaView GUI and make an x-normal slice.
#   2. Zoom/pan until the view shows EXACTLY the framing you want.
#   3. View -> Python Shell, then:
#          exec(open('/netappfs/scratch/CFD/develop/jpa/simple_wing_wheel/RANS_Simulations/postprocessing/dump_camera.py').read())
#   4. Send me the printed block, or paste it straight into slices.yaml.
#
# Why this is needed: a screenshot of the Adjust Camera dialog is not enough. In
# perspective mode the visible extent depends on view angle AND distance, and
# the numbers in that dialog gave a visible height of about 2.2 m, which cannot
# be the zoomed view actually on screen. The parallel-projection scale below is
# unambiguous.
# ============================================================================

from paraview.simple import GetActiveView

v = GetActiveView()

pos = list(v.CameraPosition)
foc = list(v.CameraFocalPoint)
up = list(v.CameraViewUp)
par = int(v.CameraParallelProjection)
scale = float(v.CameraParallelScale)
size = list(v.ViewSize)

# View direction, i.e. what camera_dir must be in slices.yaml.
d = [foc[i] - pos[i] for i in range(3)]
mag = sum(c * c for c in d) ** 0.5
d = [c / mag for c in d] if mag > 0 else d
# Snap to the nearest axis so the value is clean.
axis = max(range(3), key=lambda i: abs(d[i]))
cam_dir = [0, 0, 0]
cam_dir[axis] = 1 if d[axis] > 0 else -1

normal_name = "xyz"[axis]
IN_PLANE = {"x": ("y", "z"), "y": ("x", "z"), "z": ("x", "y")}
h_name, v_name = IN_PLANE[normal_name]
h_idx = "xyz".index(h_name)
v_idx = "xyz".index(v_name)

print("")
print("=" * 68)
print("CAMERA READOUT")
print("=" * 68)
print("  parallel projection : %s" % ("ON" if par else "OFF  <-- turn it ON!"))
print("  ViewSize            : %d x %d  (aspect %.4f)"
      % (size[0], size[1], float(size[0]) / float(size[1])))
print("  CameraPosition      : %.6f  %.6f  %.6f" % tuple(pos))
print("  CameraFocalPoint    : %.6f  %.6f  %.6f" % tuple(foc))
print("  CameraViewUp        : %g  %g  %g" % tuple(up))
print("  CameraParallelScale : %.6f" % scale)
print("  slice normal        : %s" % normal_name)
print("")

if not par:
    print("  WARNING: parallel projection is OFF, so CameraParallelScale does")
    print("  not describe what you see. Enable it first:")
    print("      GetActiveView().CameraParallelProjection = 1; Render()")
    print("  then re-zoom to taste and run this script again.")
    print("")
else:
    aspect = float(size[0]) / float(size[1])
    half_h = scale * aspect
    hl, hh = foc[h_idx] - half_h, foc[h_idx] + half_h
    vl, vh = foc[v_idx] - scale, foc[v_idx] + scale
    print("  Visible region:")
    print("    %s  %.4f .. %.4f   (%.1f mm wide)" % (h_name, hl, hh, 1000 * (hh - hl)))
    print("    %s  %.4f .. %.4f   (%.1f mm tall)" % (v_name, vl, vh, 1000 * (vh - vl)))
    print("")
    print("  Paste into slices.yaml under directions.%s:" % normal_name)
    print("  " + "-" * 60)
    print("    frame:")
    print("      horizontal: [%.4f, %.4f]   # %s" % (hl, hh, h_name))
    print("      vertical: [%.4f, %.4f]     # %s" % (vl, vh, v_name))
    print("    camera_dir: [%d, %d, %d]" % tuple(cam_dir))
    print("    view_up: [%g, %g, %g]" % tuple(up))
    print("    # exact override, independent of image aspect:")
    print("    parallel_scale: %.6f" % scale)
    print("    center: [%.6f, %.6f]" % (foc[h_idx], foc[v_idx]))
    print("  " + "-" * 60)
    print("")
