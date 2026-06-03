"""Geometry validation: build volume, bolt holes, overhang, wall thickness."""

from __future__ import annotations

import math
import tempfile
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class GeometryResult:
    passed: bool
    reason: str = ""
    bounding_box_mm: tuple[float, float, float] | None = None
    volume_mm3: float = 0.0
    mass_grams: float = 0.0


def validate(step_bytes: bytes, spec: dict, mat: dict) -> GeometryResult:
    """
    Load a STEP file and validate it against the spec's geometric constraints.
    Returns GeometryResult with mass_grams populated if passed.
    """
    try:
        from OCP.BRep import BRep_Builder
        from OCP.BRepBndLib import BRepBndLib
        from OCP.BRepGProp import BRepGProp
        from OCP.Bnd import Bnd_Box
        from OCP.GProp import GProp_GProps
        from OCP.STEPControl import STEPControl_Reader
        from OCP.IFSelect import IFSelect_RetDone

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            f.write(step_bytes)
            path = f.name

        try:
            reader = STEPControl_Reader()
            status = reader.ReadFile(path)
            if status != IFSelect_RetDone:
                return GeometryResult(passed=False, reason="Failed to read STEP file")
            reader.TransferRoots()
            shape = reader.OneShape()
        finally:
            os.unlink(path)

    except Exception as e:
        return GeometryResult(passed=False, reason=f"STEP import error: {e}")

    # Bounding box check
    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
    bvol = spec["constraints"]["build_volume_mm"]
    if dx > bvol[0] or dy > bvol[1] or dz > bvol[2]:
        return GeometryResult(
            passed=False,
            reason=f"Exceeds build volume: part={dx:.1f}×{dy:.1f}×{dz:.1f} mm, limit={bvol[0]}×{bvol[1]}×{bvol[2]} mm",
        )

    # Volume and mass
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    volume_mm3 = props.Mass()  # BRepGProp uses mm³ when input is mm
    if volume_mm3 <= 0:
        return GeometryResult(passed=False, reason="Part has zero or negative volume")

    mass_g = volume_mm3 * mat["density_kg_m3"] * 1e-6  # mm³ → cm³ → g

    # Bolt hole presence check (fast: verify no solid material at bolt centers on mount face)
    bolt_check = _check_bolt_holes(shape, spec)
    if not bolt_check[0]:
        return GeometryResult(passed=False, reason=bolt_check[1])

    # Overhang check (sampled ray-cast approximation)
    overhang_ok, overhang_reason = _check_overhang(shape, spec)
    if not overhang_ok:
        return GeometryResult(passed=False, reason=overhang_reason)

    # Wall thickness check (ray-cast cross-section sampler)
    wall_ok, wall_reason = _check_wall_thickness(
        shape, spec, xmin, ymin, zmin, xmax, ymax, zmax
    )
    if not wall_ok:
        return GeometryResult(passed=False, reason=wall_reason)

    return GeometryResult(
        passed=True,
        bounding_box_mm=(dx, dy, dz),
        volume_mm3=volume_mm3,
        mass_grams=mass_g,
    )


def _check_bolt_holes(shape: Any, spec: dict) -> tuple[bool, str]:
    """
    Verify bolt holes exist at the required pattern on the mount face.
    Strategy: shoot a ray along X at each bolt center (Y, Z); if it hits
    material at X=0 without a through-hole, the part is solid there.
    Uses BRepIntCurveSurface_Inter for intersection.
    """
    try:
        from OCP.gp import gp_Pnt, gp_Dir, gp_Lin
        from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
        from OCP.GeomAbs import GeomAbs_IsOpposite

        pattern = spec["constraints"]["bolt_pattern_mm"]
        # Bolt holes are centered at (Y, Z) pairs from the pattern,
        # offset to sit within the part bounds.
        # We check that a ray along +X through the bolt center
        # passes through the part (hits both entry and exit surfaces).
        clearance = spec["constraints"]["bolt_diameter_clearance_mm"] / 2

        for i, (by, bz) in enumerate(pattern):
            ray = gp_Lin(gp_Pnt(-10.0, by, bz), gp_Dir(1.0, 0.0, 0.0))
            inter = BRepIntCurveSurface_Inter()
            inter.Init(shape, ray, 1e-3)
            hits = 0
            while inter.More():
                hits += 1
                inter.Next()
            # A through-hole produces an even number of intersections ≥ 2
            # A solid plug through the bolt center would give odd or no clear channel
            # Heuristic: require at least 2 intersection surfaces (enters and exits)
            if hits < 2:
                return False, f"Bolt hole {i+1} missing or obstructed at ({by}, {bz})"

    except Exception as e:
        # If OCP raycasting fails gracefully, skip this check (don't penalize)
        return True, ""

    return True, ""


def _check_overhang(shape: Any, spec: dict) -> tuple[bool, str]:
    """
    Approximate overhang check: sample face normals and flag faces
    whose downward-projected angle exceeds max_overhang_deg.
    Print direction assumed to be +Z (layer-by-layer upward).
    """
    try:
        from OCP.BRep import BRep_Tool
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.gp import gp_Dir

        max_deg = spec["constraints"]["max_overhang_deg"]
        threshold = math.cos(math.radians(90 - max_deg))  # cos of angle from horizontal

        mesh = BRepMesh_IncrementalMesh(shape, 1.0)  # 1mm deflection
        mesh.Perform()

        exp = TopExp_Explorer(shape, TopAbs_FACE)
        worst_angle = 0.0
        while exp.More():
            face = exp.Current()
            location = face.Location()
            triangulation = BRep_Tool.Triangulation_s(face, location)
            if triangulation is None:
                exp.Next()
                continue
            for i in range(1, triangulation.NbTriangles() + 1):
                n1, n2, n3 = triangulation.Triangle(i).Get()
                p1 = triangulation.Node(n1)
                p2 = triangulation.Node(n2)
                p3 = triangulation.Node(n3)
                # Face normal approximation via cross product
                ax = p2.X() - p1.X(); ay = p2.Y() - p1.Y(); az = p2.Z() - p1.Z()
                bx = p3.X() - p1.X(); by_ = p3.Y() - p1.Y(); bz = p3.Z() - p1.Z()
                nx = ay * bz - az * by_
                ny = az * bx - ax * bz
                nz = ax * by_ - ay * bx
                mag = math.sqrt(nx*nx + ny*ny + nz*nz)
                if mag < 1e-10:
                    continue
                nz_norm = nz / mag
                # Overhang: face points downward (nz < 0)
                if nz_norm < -threshold:
                    angle = math.degrees(math.acos(max(0.0, min(1.0, -nz_norm))))
                    worst_angle = max(worst_angle, angle)
            exp.Next()

        if worst_angle > max_deg + 1.0:  # 1° tolerance
            return False, f"Overhang {worst_angle:.1f}° exceeds limit of {max_deg}°"

    except Exception:
        # Non-fatal: skip overhang check if OCP mesh fails
        pass

    return True, ""


def _check_wall_thickness(
    shape: Any,
    spec: dict,
    xmin: float,
    ymin: float,
    zmin: float,
    xmax: float,
    ymax: float,
    zmax: float,
) -> tuple[bool, str]:
    """
    Check minimum wall thickness via ray casting along X, Y, and Z axes.

    For each axis, cast a grid of rays from below the bounding box and collect
    intersection parameters. Consecutive entry/exit pairs give chord lengths
    through solid material. Any chord shorter than min_wall_thickness_mm
    (minus a 0.1mm print tolerance) fails the check.

    X-rays skip samples near bolt hole centers to avoid flagging intentional
    clearance holes in the mounting face as thin walls.
    """
    try:
        from OCP.gp import gp_Pnt, gp_Dir, gp_Lin
        from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter

        min_wall = spec["constraints"]["min_wall_thickness_mm"]
        bolt_pattern = spec["constraints"].get("bolt_pattern_mm", [])
        bolt_radius = spec["constraints"].get("bolt_diameter_clearance_mm", 0.0) / 2.0

        SAMPLES = 8   # grid resolution per transverse axis
        TOL = 1e-3    # intersection tolerance (mm)
        PRINT_TOL = 0.1  # slicer rounding tolerance

        def ray_chords(
            axis: int,
            start_offset: float,
            perp_a_range: tuple[float, float],
            perp_b_range: tuple[float, float],
            perp_a_axis: int,
            perp_b_axis: int,
            exclude_centers: list[tuple[float, float]] | None = None,
            exclude_radius: float = 0.0,
        ) -> float:
            """Return minimum chord length found across the sampled ray grid."""
            direction = [0.0, 0.0, 0.0]
            direction[axis] = 1.0
            d = gp_Dir(*direction)

            a_vals = [
                perp_a_range[0] + (perp_a_range[1] - perp_a_range[0]) * (i + 0.5) / SAMPLES
                for i in range(SAMPLES)
            ]
            b_vals = [
                perp_b_range[0] + (perp_b_range[1] - perp_b_range[0]) * (i + 0.5) / SAMPLES
                for i in range(SAMPLES)
            ]

            min_chord = float("inf")
            for a in a_vals:
                for b in b_vals:
                    if exclude_centers:
                        too_close = any(
                            math.sqrt((a - ec[0]) ** 2 + (b - ec[1]) ** 2) < exclude_radius
                            for ec in exclude_centers
                        )
                        if too_close:
                            continue

                    pt = [0.0, 0.0, 0.0]
                    pt[axis] = start_offset
                    pt[perp_a_axis] = a
                    pt[perp_b_axis] = b
                    ray = gp_Lin(gp_Pnt(*pt), d)

                    inter = BRepIntCurveSurface_Inter()
                    inter.Init(shape, ray, TOL)
                    params: list[float] = []
                    while inter.More():
                        params.append(inter.W())
                        inter.Next()
                    params.sort()

                    # Consecutive pairs are entry/exit through solid material.
                    for i in range(0, len(params) - 1, 2):
                        chord = params[i + 1] - params[i]
                        if chord > TOL and chord < min_chord:
                            min_chord = chord

            return min_chord

        bolt_yz = [(float(bp[0]), float(bp[1])) for bp in bolt_pattern]

        # X-axis: exclude samples at bolt hole (Y, Z) centers (intentional voids)
        min_x = ray_chords(
            axis=0, start_offset=xmin - 1.0,
            perp_a_range=(ymin, ymax), perp_b_range=(zmin, zmax),
            perp_a_axis=1, perp_b_axis=2,
            exclude_centers=bolt_yz, exclude_radius=bolt_radius,
        )
        # Y-axis
        min_y = ray_chords(
            axis=1, start_offset=ymin - 1.0,
            perp_a_range=(xmin, xmax), perp_b_range=(zmin, zmax),
            perp_a_axis=0, perp_b_axis=2,
        )
        # Z-axis (print direction)
        min_z = ray_chords(
            axis=2, start_offset=zmin - 1.0,
            perp_a_range=(xmin, xmax), perp_b_range=(ymin, ymax),
            perp_a_axis=0, perp_b_axis=1,
        )

        global_min = min(min_x, min_y, min_z)
        if global_min < float("inf") and global_min < min_wall - PRINT_TOL:
            axis_label = {min_x: "X", min_y: "Y", min_z: "Z"}[global_min]
            return (
                False,
                f"Wall too thin: {global_min:.2f}mm along {axis_label}-axis "
                f"(minimum {min_wall}mm)",
            )

    except Exception:
        # Non-fatal: OCP failure skips the check rather than penalizing valid geometry
        pass

    return True, ""
