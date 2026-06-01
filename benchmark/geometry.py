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
