"""
STEP geometric similarity check.

Compares two STEP files by sampling random surface points and computing
a symmetric mean-Hausdorff distance, normalized to a [0, 1] similarity
score. 1.0 = identical geometry, 0.0 = very different.

Used to detect submissions that copy or minimally perturb the current SOTA.
"""

from __future__ import annotations

import os
import tempfile

import numpy as np


# Fraction of bounding-box diagonal used as the normalization scale.
# A mean-Hausdorff distance equal to this fraction maps to similarity 0.0.
# Smaller → more sensitive; 0.05 (5%) is calibrated so near-copies score > 0.95.
_SCALE_FRACTION = 0.05


def compute(step_a: bytes, step_b: bytes, n_samples: int = 1000, seed: int = 42) -> float:
    """
    Return similarity in [0, 1] between two STEP files.

    Raises ValueError if either file cannot be tessellated.
    Returns 0.0 if surface sampling yields < 10 points (degenerate shapes).
    """
    pts_a = _sample_surface(step_a, n_samples, seed)
    pts_b = _sample_surface(step_b, n_samples, seed)

    if len(pts_a) < 10 or len(pts_b) < 10:
        return 0.0

    # Bounding-box diagonal of the combined point cloud — scale reference.
    all_pts = np.vstack([pts_a, pts_b])
    diag = float(np.linalg.norm(all_pts.max(axis=0) - all_pts.min(axis=0)))
    if diag < 1e-6:
        return 1.0  # both degenerate at same location

    # (N, M) pairwise distance matrix — 1000×1000 × 8 bytes = 8 MB, acceptable.
    dist = np.linalg.norm(pts_a[:, np.newaxis, :] - pts_b[np.newaxis, :, :], axis=2)

    # Mean symmetric Hausdorff: average of (mean nearest-neighbour distances).
    # More robust than max Hausdorff; not fooled by a single outlier vertex.
    mean_h = (dist.min(axis=1).mean() + dist.min(axis=0).mean()) / 2.0

    normalized = mean_h / (diag * _SCALE_FRACTION)
    return float(max(0.0, 1.0 - normalized))


def _sample_surface(step_bytes: bytes, n: int, seed: int) -> np.ndarray:
    """
    Load a STEP file, tessellate its surface at 1 mm deflection, and return
    a (k, 3) array of triangle centroid coordinates (k ≤ n).
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        f.write(step_bytes)
        path = f.name

    try:
        reader = STEPControl_Reader()
        if reader.ReadFile(path) != IFSelect_RetDone:
            raise ValueError("STEPControl_Reader failed to load file")
        reader.TransferRoots()
        shape = reader.OneShape()
    finally:
        os.unlink(path)

    BRepMesh_IncrementalMesh(shape, 1.0).Perform()

    centroids: list[list[float]] = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = exp.Current()
        loc = face.Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            for i in range(1, tri.NbTriangles() + 1):
                n1, n2, n3 = tri.Triangle(i).Get()
                p1, p2, p3 = tri.Node(n1), tri.Node(n2), tri.Node(n3)
                centroids.append([
                    (p1.X() + p2.X() + p3.X()) / 3.0,
                    (p1.Y() + p2.Y() + p3.Y()) / 3.0,
                    (p1.Z() + p2.Z() + p3.Z()) / 3.0,
                ])
        exp.Next()

    if not centroids:
        return np.zeros((0, 3), dtype=float)

    pts = np.array(centroids, dtype=float)
    if len(pts) > n:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(pts), size=n, replace=False)
        pts = pts[idx]
    return pts
