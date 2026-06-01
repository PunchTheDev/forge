"""
FEA pipeline: gmsh meshing → CalculiX solve → max von Mises stress extraction.

Workflow:
  1. Write STEP bytes to a temp file.
  2. gmsh imports STEP, generates C3D4 (4-node linear tet) mesh.
  3. Write CalculiX .inp file with BCs and load.
  4. Run `ccx` solver.
  5. Parse .frd output for max von Mises stress.
  6. Compare against allowable = yield_stress / safety_factor.
"""

from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FEAResult:
    passed: bool
    max_stress_mpa: float = 0.0
    allowable_mpa: float = 0.0
    reason: str = ""
    element_count: int = 0
    load_node_count: int = 0


MESH_SIZE_MM = 4.0  # element characteristic length — coarse but fast

# Anti-gaming thresholds
MIN_ELEMENTS = 100       # reject trivially sparse meshes
MIN_LOAD_NODES = 3       # load must be distributed; a single nub at the exact load
                         # coordinate is numerically degenerate and easy to game


def run(step_bytes: bytes, spec: dict, mat: dict) -> FEAResult:
    """Run FEA on the given STEP geometry. Returns FEAResult."""
    allowable = mat["yield_stress_mpa"] / spec["constraints"]["safety_factor"]

    with tempfile.TemporaryDirectory() as tmpdir:
        step_path = os.path.join(tmpdir, "part.step")
        inp_path = os.path.join(tmpdir, "job.inp")
        Path(step_path).write_bytes(step_bytes)

        try:
            nodes, elements = _mesh(step_path, tmpdir)
        except Exception as e:
            return FEAResult(passed=False, reason=f"Meshing failed: {e}")

        if not nodes or not elements:
            return FEAResult(passed=False, reason="Empty mesh produced by gmsh")

        # Reject trivially sparse meshes — a part with fewer than MIN_ELEMENTS
        # tetrahedra is either a near-zero-volume shell or a gameable nub.
        if len(elements) < MIN_ELEMENTS:
            return FEAResult(
                passed=False,
                reason=f"Degenerate mesh: only {len(elements)} elements (min {MIN_ELEMENTS})",
            )

        bolt_nodes = _find_bolt_nodes(nodes, spec)
        load_nodes = _find_load_nodes(nodes, spec)

        if not bolt_nodes:
            return FEAResult(
                passed=False,
                reason=f"No bolt nodes found near mount face (x=0 ± 8mm, bolt centers). Mesh size={MESH_SIZE_MM}mm",
                element_count=len(elements),
            )

        # Require load to be distributed across enough nodes so a single-nub
        # geometry can't pass by concentrating stress at one integration point.
        if len(load_nodes) < MIN_LOAD_NODES:
            return FEAResult(
                passed=False,
                reason=(
                    f"Too few nodes near load point: {len(load_nodes)} (min {MIN_LOAD_NODES}). "
                    "Part must have material distributed at the load application zone."
                ),
                element_count=len(elements),
                load_node_count=len(load_nodes),
            )

        _write_inp(inp_path, nodes, elements, bolt_nodes, load_nodes, spec, mat)

        try:
            _run_ccx(tmpdir, "job")
        except Exception as e:
            return FEAResult(
                passed=False,
                reason=f"CalculiX failed: {e}",
                element_count=len(elements),
                load_node_count=len(load_nodes),
            )

        frd_path = os.path.join(tmpdir, "job.frd")
        if not os.path.exists(frd_path):
            return FEAResult(
                passed=False,
                reason="CalculiX produced no .frd output",
                element_count=len(elements),
                load_node_count=len(load_nodes),
            )

        max_stress = _parse_frd(frd_path)
        if max_stress is None:
            return FEAResult(
                passed=False,
                reason="Could not parse stress from .frd",
                element_count=len(elements),
                load_node_count=len(load_nodes),
            )

        passed = max_stress <= allowable
        return FEAResult(
            passed=passed,
            max_stress_mpa=max_stress,
            allowable_mpa=allowable,
            reason="" if passed else f"Max stress {max_stress:.1f} MPa > allowable {allowable:.1f} MPa",
            element_count=len(elements),
            load_node_count=len(load_nodes),
        )


def _mesh(step_path: str, tmpdir: str) -> tuple[dict, list]:
    """Use gmsh to mesh the STEP file. Returns (nodes dict, elements list)."""
    import gmsh

    mesh_path = os.path.join(tmpdir, "part.msh")

    gmsh.initialize()
    gmsh.option.setNumber("General.Verbosity", 0)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMin", MESH_SIZE_MM)
    gmsh.option.setNumber("Mesh.CharacteristicLengthMax", MESH_SIZE_MM)
    gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay — more robust than Frontal
    gmsh.option.setNumber("Mesh.ElementOrder", 1)  # Linear tets (C3D4) — avoids Jacobian issues near curved surfaces

    gmsh.model.add("part")
    gmsh.merge(step_path)
    gmsh.model.geo.synchronize()
    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate(3)
    gmsh.write(mesh_path)
    gmsh.finalize()

    return _parse_msh(mesh_path)


def _parse_msh(msh_path: str) -> tuple[dict, list]:
    """Parse gmsh .msh v4 file. Returns nodes dict {id: (x,y,z)} and C3D4 element list."""
    nodes: dict[int, tuple[float, float, float]] = {}
    elements: list[tuple[int, ...]] = []

    with open(msh_path) as f:
        content = f.read()

    # Nodes section
    node_block_match = re.search(r"\$Nodes\n(.*?)\$EndNodes", content, re.DOTALL)
    if node_block_match:
        lines = node_block_match.group(1).strip().split("\n")
        i = 1  # skip overall header
        while i < len(lines):
            parts = lines[i].split()
            if len(parts) == 4:  # entity block header: dim tag parametric numNodes
                num_nodes = int(parts[3])
                node_ids = [int(lines[i + 1 + j]) for j in range(num_nodes)]
                for j, nid in enumerate(node_ids):
                    coords_line = lines[i + 1 + num_nodes + j].split()
                    nodes[nid] = (float(coords_line[0]), float(coords_line[1]), float(coords_line[2]))
                i += 1 + num_nodes * 2
            else:
                i += 1

    # Elements section — type 4 = 4-node linear tet (C3D4)
    elem_block_match = re.search(r"\$Elements\n(.*?)\$EndElements", content, re.DOTALL)
    if elem_block_match:
        lines = elem_block_match.group(1).strip().split("\n")
        i = 1  # skip overall header
        while i < len(lines):
            parts = lines[i].split()
            if len(parts) == 4:
                entity_dim, entity_tag, elem_type, num_elems = (
                    int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                )
                for j in range(num_elems):
                    elem_line = lines[i + 1 + j].split()
                    if elem_type == 4:  # C3D4: 4-node linear tetrahedron
                        elements.append(tuple(int(x) for x in elem_line))
                i += 1 + num_elems
            else:
                i += 1

    return nodes, elements


def _find_bolt_nodes(nodes: dict, spec: dict, tol: float = 8.0) -> list[int]:
    """Find nodes near each bolt hole center on the mount face (X ≈ mount_face_x)."""
    pattern = spec["constraints"]["bolt_pattern_mm"]
    mount_x = spec["constraints"]["mount_face_x_mm"]
    result = []
    for ny, nz in pattern:
        for nid, (x, y, z) in nodes.items():
            if (abs(x - mount_x) < tol and
                    math.sqrt((y - ny)**2 + (z - nz)**2) < tol):
                result.append(nid)
    return result


def _find_load_nodes(nodes: dict, spec: dict, tol: float = 15.0) -> list[int]:
    """Find nodes near the load application point."""
    lp = spec["constraints"]["load_point_mm"]
    result = []
    for nid, (x, y, z) in nodes.items():
        if (abs(x - lp[0]) < tol and
                abs(y - lp[1]) < tol and
                abs(z - lp[2]) < tol):
            result.append(nid)
    return result


def _write_inp(
    inp_path: str,
    nodes: dict,
    elements: list,
    bolt_nodes: list[int],
    load_nodes: list[int],
    spec: dict,
    mat: dict,
) -> None:
    """Write CalculiX .inp file."""
    E = mat["youngs_modulus_mpa"]
    nu = mat["poisson_ratio"]
    rho = mat["density_kg_m3"] * 1e-12  # kg/m³ → t/mm³ (CalculiX units: t, mm, s)
    load_n = spec["constraints"]["load_newtons"]
    load_per_node = load_n / len(load_nodes) if load_nodes else load_n

    with open(inp_path, "w") as f:
        f.write("*HEADING\n")
        f.write("Forge FEA evaluation\n")

        f.write("*NODE\n")
        for nid, (x, y, z) in nodes.items():
            f.write(f"{nid}, {x:.6f}, {y:.6f}, {z:.6f}\n")

        f.write("*ELEMENT, TYPE=C3D4, ELSET=SOLID\n")
        for elem in elements:
            f.write(", ".join(str(n) for n in elem) + "\n")

        f.write("*MATERIAL, NAME=MAT\n")
        f.write("*ELASTIC\n")
        f.write(f"{E}, {nu}\n")
        f.write("*DENSITY\n")
        f.write(f"{rho}\n")

        f.write("*SOLID SECTION, MATERIAL=MAT, ELSET=SOLID\n")
        f.write("\n")

        if bolt_nodes:
            f.write("*NSET, NSET=FIXED\n")
            for nid in bolt_nodes:
                f.write(f"{nid},\n")
            f.write("*BOUNDARY\n")
            f.write("FIXED, 1, 3, 0.0\n")

        if load_nodes:
            f.write("*NSET, NSET=LOADED\n")
            for nid in load_nodes:
                f.write(f"{nid},\n")

        f.write("*STEP\n")
        f.write("*STATIC\n")

        if load_nodes:
            f.write("*CLOAD\n")
            # Apply load in -Z direction (gravity-like downward)
            for nid in load_nodes:
                f.write(f"{nid}, 3, {-load_per_node:.6f}\n")

        f.write("*NODE FILE\n")
        f.write("U\n")
        f.write("*EL FILE\n")
        f.write("S\n")
        f.write("*END STEP\n")


def _run_ccx(workdir: str, jobname: str) -> None:
    result = subprocess.run(
        ["ccx", "-i", jobname],
        cwd=workdir,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        # ccx writes most output to stdout, not stderr
        raw = (result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace"))
        # Collapse to single line so it survives JSON→shell→JS round-trips
        brief = " ".join(raw.split())[-500:] or f"exit code {result.returncode}"
        raise RuntimeError(brief)


def _parse_frd(frd_path: str) -> float | None:
    """
    Parse CalculiX .frd binary/ASCII output to extract max von Mises stress.
    The .frd format stores stress components; we compute von Mises from S11/S22/S33/S12/S13/S23.
    """
    try:
        with open(frd_path) as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        return None

    # ASCII .frd: stress block starts with '  -4  STRESS'
    # Components per node: S11, S22, S33, S12, S13, S23
    in_stress = False
    max_vm = 0.0

    for line in lines:
        if "STRESS" in line and "-4" in line:
            in_stress = True
            continue
        if in_stress:
            if line.startswith(" -3"):
                break
            if line.startswith(" -1"):
                # Node stress line: -1  node_id  S11  S22  S33  S12  S13  S23
                parts = line.split()
                if len(parts) >= 7:
                    try:
                        s11, s22, s33 = float(parts[2]), float(parts[3]), float(parts[4])
                        s12, s13, s23 = float(parts[5]), float(parts[6]), float(parts[7]) if len(parts) > 7 else 0.0
                        vm = math.sqrt(
                            0.5 * ((s11-s22)**2 + (s22-s33)**2 + (s33-s11)**2)
                            + 3 * (s12**2 + s13**2 + s23**2)
                        )
                        max_vm = max(max_vm, vm)
                    except (ValueError, IndexError):
                        pass

    return max_vm if max_vm > 0 else None
