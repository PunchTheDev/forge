"""
Baseline stainless steel bracket for spec 003.

Simple L-bracket: a 10mm-thick back plate covering the 6-bolt pattern
plus a 15mm-thick horizontal arm extending 150mm from the wall.
The arm cross-section (15mm z-height × 90mm y-width) gives a section
modulus S = 90×15²/6 = 3375 mm³, producing σ_max ≈ 43.6 MPa against
the 100 kg load at 150mm (M = 147,150 N·mm). That is well below the
allowable 82 MPa (205/2.5). Estimated mass ≈ 1300 g.
"""

import io
from build123d import (
    Box,
    BuildPart,
    Location,
    Mode,
    add,
    export_step,
)


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a conservative L-bracket in stainless 316."""
    # Spec constraints
    bv = spec["constraints"]["build_volume_mm"]   # [x, y, z]
    wall_x = 10.0   # back plate thickness
    arm_z  = 15.0   # arm height (z) — drives section modulus
    arm_y  = 90.0   # arm width  (y)
    arm_x  = bv[0] - wall_x  # arm length to fill build volume

    with BuildPart() as part:
        # Back plate — covers full y×z face of build volume
        with Location((wall_x / 2, bv[1] / 2, bv[2] / 2)):
            Box(wall_x, bv[1], bv[2], mode=Mode.ADD)

        # Horizontal arm — centered in y, sits at bottom half of z
        arm_z_center = arm_z / 2
        with Location((wall_x + arm_x / 2, bv[1] / 2, arm_z_center)):
            Box(arm_x, arm_y, arm_z, mode=Mode.ADD)

    buf = io.BytesIO()
    export_step(part.part, buf)
    return buf.getvalue()
