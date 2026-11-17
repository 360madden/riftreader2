"""Dependency-free offline BVH prototype for already transformed triangle meshes.

This accelerates *candidate* ray intersections only. It does not establish
visible screen fragments, collision, floor, route clearance, or input authority.
Retains physical_pixel_surface's exact triangle intersection and output contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from scripts import physical_pixel_surface as surface


@dataclass(frozen=True, slots=True)
class _Node:
    bounds: tuple[float, float, float, float, float, float]
    left: "_Node | None" = None
    right: "_Node | None" = None
    face_indices: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class PreparedMesh:
    vertices: tuple
    faces: tuple
    root: _Node
    degenerate_triangles: int
    node_count: int
    leaf_count: int
    leaf_size: int


def _padded_bounds(a, b, c):
    # The exact narrowphase admits barycentric edge tolerance of 1e-10.
    # Padding must conservatively include those near-edge rays as well.
    low = [min(a[i], b[i], c[i]) for i in range(3)]
    high = [max(a[i], b[i], c[i]) for i in range(3)]
    for i in range(3):
        magnitude = max(abs(low[i]), abs(high[i]))
        pad = 1e-8 + 4e-10 * (high[i] - low[i]) + 1e-14 * magnitude
        low[i] -= pad
        high[i] += pad
    return tuple(low + high)


def prepare(vertices, faces, *, leaf_size=24):
    """Build a balanced, conservative BVH; preserve original face indices."""
    surface._require(type(leaf_size) is int and 4 <= leaf_size <= 256,
                     "bvh-leaf-size-invalid")
    surface._require(0 < len(vertices) <= surface.MAX_VERTICES
                     and 0 < len(faces) <= surface.MAX_TRIANGLES,
                     "bvh-mesh-size-invalid")
    # Own immutable nested geometry before computing any bounds. A caller must
    # not be able to mutate a prepared index's bounds/narrowphase consistency.
    vertices = tuple(tuple(point) for point in vertices)
    faces = tuple((tuple(indices), group) for indices, group in faces)
    surface._require(all(type(group) is str for _indices, group in faces),
                     "bvh-face-group-must-be-string")
    bounds, centers, degenerate_count = [], [], 0
    for indices, _group in faces:
        a, b, c = (vertices[i] for i in indices)
        bbox = _padded_bounds(a, b, c)
        bounds.append(bbox)
        centers.append(tuple((bbox[i] + bbox[i+3]) * .5 for i in range(3)))
        normal = surface._cross(surface._subtract(b, a), surface._subtract(c, a))
        degenerate_count += math.hypot(*normal) <= 1e-12

    counts = [0, 0]

    def build(indices):
        counts[0] += 1
        first = bounds[indices[0]]
        low = list(first[:3])
        high = list(first[3:])
        center_low = list(centers[indices[0]])
        center_high = list(centers[indices[0]])
        for face_id in indices[1:]:
            box = bounds[face_id]
            ctr = centers[face_id]
            for axis in range(3):
                if box[axis] < low[axis]:
                    low[axis] = box[axis]
                if box[axis+3] > high[axis]:
                    high[axis] = box[axis+3]
                if ctr[axis] < center_low[axis]:
                    center_low[axis] = ctr[axis]
                if ctr[axis] > center_high[axis]:
                    center_high[axis] = ctr[axis]
        box = tuple(low + high)
        if len(indices) <= leaf_size:
            counts[1] += 1
            return _Node(bounds=box, face_indices=tuple(indices))
        axis = max(range(3), key=lambda a: center_high[a] - center_low[a])
        indices.sort(key=lambda i: (centers[i][axis], i))
        middle = len(indices) // 2
        return _Node(bounds=box,
                     left=build(indices[:middle]),
                     right=build(indices[middle:]))

    root = build(list(range(len(faces))))
    return PreparedMesh(vertices, faces, root, int(degenerate_count),
                        counts[0], counts[1], leaf_size)


def _interval(box, origin, direction, max_distance):
    near, far = 0.0, max_distance
    for axis in range(3):
        component = direction[axis]
        low, high = box[axis], box[axis+3]
        if component == 0:
            if origin[axis] < low or origin[axis] > high:
                return None
            continue
        t0, t1 = (low-origin[axis])/component, (high-origin[axis])/component
        if t0 > t1:
            t0, t1 = t1, t0
        near = max(near, t0)
        far = min(far, t1)
        if far < near:
            return None
    return near


def _candidate_indices(index, origin, direction, max_distance):
    candidates = []
    stack = [index.root]
    while stack:
        node = stack.pop()
        if _interval(node.bounds, origin, direction, max_distance) is None:
            continue
        if node.face_indices:
            candidates.extend(node.face_indices)
        else:
            stack.append(node.right)
            stack.append(node.left)
    return candidates


def candidate_count(index, ray, *, max_distance=2000.0):
    """Diagnostic-only conservative broadphase count for a valid ray."""
    origin = surface._xyz(ray.get("nativeEyeXYZ"), "native-eye")
    direction = surface._xyz(ray.get("unitDirectionXYZ"), "ray-direction")
    return len(_candidate_indices(index, origin, direction, max_distance))


def intersect(index, ray, max_distance=2000.0, selected_triangle=None):
    """Exact physical_pixel_surface.intersect_prepared contract with BVH culling."""
    surface._require(type(max_distance) in (int, float)
                     and math.isfinite(max_distance) and 0 < max_distance <= 10000,
                     "max-distance-invalid")
    surface._require(selected_triangle is None or
                     (type(selected_triangle) is int
                      and 1 <= selected_triangle <= surface.MAX_TRIANGLES),
                     "selected-triangle-index-invalid")
    surface._require(isinstance(ray, dict)
                     and ray.get("status") == "available-candidate",
                     "validated-pixel-ray-required")
    origin = surface._xyz(ray.get("nativeEyeXYZ"), "native-eye")
    direction = surface._xyz(ray.get("unitDirectionXYZ"), "ray-direction")
    surface._require(abs(math.hypot(*direction) - 1) <= 1e-6,
                     "ray-not-unit-length")
    hits = []
    for face_id in _candidate_indices(index, origin, direction, max_distance):
        indices, group = index.faces[face_id]
        a, b, c = (index.vertices[i] for i in indices)
        hit, _degenerate = surface._intersect(
            origin, direction, a, b, c, max_distance)
        if hit is not None:
            hit["triangleIndex"] = face_id + 1
            hit["meshGroup"] = group
            hits.append(hit)
    hits.sort(key=lambda hit: (hit["distanceNative"], hit["triangleIndex"]))
    groups = []
    for hit in hits:
        if not groups or hit["distanceNative"] - groups[-1][0] > 1e-4:
            groups.append([hit["distanceNative"], 0])
        groups[-1][1] += 1
        hit["depthGroup"] = len(groups)
    for hit in hits:
        hit["coincidentGroupSize"] = groups[hit["depthGroup"]-1][1]
    selected_hit = None
    if selected_triangle is not None:
        surface._require(selected_triangle <= len(index.faces),
                         "selected-triangle-out-of-mesh")
        selected_hit = next((dict(hit) for hit in hits
                             if hit["triangleIndex"] == selected_triangle), None)
        surface._require(selected_hit is not None,
                         "selected-triangle-not-intersected")
        selected_hit.update(
            admissionEligible=False, worldSurfaceVerified=False,
            qualification="Explicit display-only triangle candidate; "
                          "not a qualified floor or route destination")
    return {"status": "candidate-hits" if hits else "no-candidate-intersection",
            "trianglesChecked": len(index.faces),
            "verticesChecked": len(index.vertices),
            "degenerateTriangles": index.degenerate_triangles,
            "hitCount": len(hits),
            "distinctDepthGroups": len(groups),
            "hitsTruncated": len(hits) > surface.MAX_REPORTED_HITS,
            "candidateFirstXYZ": hits[0]["candidateXYZ"] if hits else None,
            "selectedTriangleIndex": selected_triangle, "selectedHit": selected_hit,
            "hits": hits[:surface.MAX_REPORTED_HITS],
            "sourceCoverageComplete": False, "floorQualified": False,
            "movementEligible": False,
            "obstacleQualified": False, "occlusionQualified": False,
            "qualification": "Offline ray/mesh mathematical candidates only; OBJ source-frame "
                             "registration, world instance, mesh coverage, rendered depth, "
                             "collision response, stacked floor choice and route clearance "
                             "are not independently qualified."}
