from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ObservabilityConfig:
    min_links: int = 6
    min_transmitters: int = 2
    min_angle_bins: int = 3
    angle_bin_count: int = 12
    max_receiver_distance_m: float = 1.0
    min_sensitivity: float = 0.5
    min_conditioning_score: float = 1e-3
    min_pass_consistency: float = 0.5
    min_repeated_links: int = 3


@dataclass(frozen=True)
class SupportMetrics:
    link_count: np.ndarray
    transmitter_count: np.ndarray
    angle_bin_count: np.ndarray
    distance_to_receiver_m: np.ndarray
    sensitivity: np.ndarray
    conditioning_score: np.ndarray
    pass_consistency: np.ndarray
    repeated_link_count: np.ndarray
    observable_mask: np.ndarray
    failed_criteria_counts: dict[str, int]


@dataclass(frozen=True)
class ComponentMetric:
    component_id: int
    cell_count: int
    supporting_links: int
    supporting_transmitters: int
    area_m2: float
    perimeter_m: float
    axis_aligned_width_m: float
    axis_aligned_height_m: float
    oriented_major_m: float
    oriented_minor_m: float
    orientation_deg: float
    centroid_x_m: float
    centroid_y_m: float
    mean_evidence: float
    minimum_evidence: float
    dimension_discretization_bound_m: float
    touches_unobserved: bool


def _validate_config(config: ObservabilityConfig) -> None:
    integer_values = (
        config.min_links,
        config.min_transmitters,
        config.min_angle_bins,
        config.angle_bin_count,
        config.min_repeated_links,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 1
        for value in integer_values
    ):
        raise ValueError("Observability count thresholds must be positive.")
    if config.min_angle_bins > config.angle_bin_count:
        raise ValueError("Minimum angle bins cannot exceed the total bin count.")
    numeric_values = (
        config.max_receiver_distance_m,
        config.min_sensitivity,
        config.min_conditioning_score,
        config.min_pass_consistency,
    )
    if not np.isfinite(numeric_values).all():
        raise ValueError("Observability thresholds must be finite.")
    if config.max_receiver_distance_m <= 0 or config.min_sensitivity < 0:
        raise ValueError("Distance must be positive and sensitivity nonnegative.")
    if not 0 <= config.min_conditioning_score <= 1:
        raise ValueError("Conditioning threshold must be in [0, 1].")
    if not 0 <= config.min_pass_consistency <= 1:
        raise ValueError("Pass consistency threshold must be in [0, 1].")


def calculate_support(
    ray_matrix_m: np.ndarray,
    transmitter_xy_m: np.ndarray,
    receiver_xy_m: np.ndarray,
    transmitter_ids: list[str] | np.ndarray,
    noise_standard_deviation_db: np.ndarray,
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
    *,
    link_pass_consistency: np.ndarray | None = None,
    link_pass_counts: np.ndarray | None = None,
    config: ObservabilityConfig | None = None,
) -> SupportMetrics:
    settings = config or ObservabilityConfig()
    _validate_config(settings)
    matrix = np.asarray(ray_matrix_m, dtype=float)
    transmitters = np.asarray(transmitter_xy_m, dtype=float)
    receivers = np.asarray(receiver_xy_m, dtype=float)
    noise = np.asarray(noise_standard_deviation_db, dtype=float)
    identifiers = np.asarray(transmitter_ids, dtype=str)
    x_centers = np.asarray(x_centers_m, dtype=float)
    y_centers = np.asarray(y_centers_m, dtype=float)
    for centers, name in ((x_centers, "x_centers_m"), (y_centers, "y_centers_m")):
        if (
            centers.ndim != 1
            or centers.size < 2
            or not np.isfinite(centers).all()
            or np.any(np.diff(centers) <= 0.0)
        ):
            raise ValueError(f"{name} must be a finite increasing vector with two points.")
    shape = (len(y_centers_m), len(x_centers_m))
    cell_count = int(np.prod(shape))
    link_count_total = matrix.shape[0] if matrix.ndim == 2 else -1
    if (
        matrix.shape != (link_count_total, cell_count)
        or transmitters.shape != (link_count_total, 2)
        or receivers.shape != transmitters.shape
        or noise.shape != (link_count_total,)
        or identifiers.shape != (link_count_total,)
    ):
        raise ValueError("Support inputs have inconsistent dimensions.")
    if any(not identifier for identifier in identifiers):
        raise ValueError("Every support link requires a non-empty transmitter ID.")
    if link_count_total == 0 or np.any(noise <= 0):
        raise ValueError("At least one link and positive noise are required.")
    if not all(np.isfinite(item).all() for item in (matrix, transmitters, receivers, noise)):
        raise ValueError("Support inputs must be finite.")

    consistency = (
        np.zeros(link_count_total, dtype=float)
        if link_pass_consistency is None
        else np.asarray(link_pass_consistency, dtype=float)
    )
    raw_pass_counts = (
        np.ones(link_count_total, dtype=int)
        if link_pass_counts is None
        else np.asarray(link_pass_counts)
    )
    if consistency.shape != (link_count_total,) or raw_pass_counts.shape != (link_count_total,):
        raise ValueError("Pass support arrays must match the number of links.")
    if (
        not np.isfinite(consistency).all()
        or np.any((consistency < 0) | (consistency > 1))
        or not np.issubdtype(raw_pass_counts.dtype, np.integer)
        or np.any(raw_pass_counts < 1)
    ):
        raise ValueError("Pass consistency must be in [0, 1] and counts positive.")
    pass_counts = raw_pass_counts.astype(int, copy=False)

    through = matrix > 1e-9
    link_counts = np.sum(through, axis=0).astype(int)
    transmitter_counts = np.zeros(cell_count, dtype=int)
    angle_counts = np.zeros(cell_count, dtype=int)
    pass_scores = np.zeros(cell_count, dtype=float)
    repeated_counts = np.zeros(cell_count, dtype=int)
    conditioning = np.zeros(cell_count, dtype=float)
    sensitivity = np.zeros(cell_count, dtype=float)
    link_angles = np.mod(
        np.arctan2(receivers[:, 1] - transmitters[:, 1], receivers[:, 0] - transmitters[:, 0]),
        np.pi,
    )
    angle_bins = np.minimum(
        (link_angles / np.pi * settings.angle_bin_count).astype(int),
        settings.angle_bin_count - 1,
    )
    geometry_keys = [
        (
            identifiers[index],
            *np.round(transmitters[index], 9),
            *np.round(receivers[index], 9),
        )
        for index in range(link_count_total)
    ]
    for cell_index in range(cell_count):
        supported = np.flatnonzero(through[:, cell_index])
        if supported.size == 0:
            continue
        grouped: dict[tuple[object, ...], list[int]] = {}
        for row_index in supported:
            grouped.setdefault(geometry_keys[row_index], []).append(int(row_index))
        representatives = np.asarray(
            [row_indices[0] for row_indices in grouped.values()], dtype=int
        )
        link_counts[cell_index] = len(grouped)
        transmitter_counts[cell_index] = np.unique(identifiers[representatives]).size
        angle_counts[cell_index] = np.unique(angle_bins[representatives]).size
        group_consistency = np.asarray(
            [float(np.mean(consistency[rows])) for rows in grouped.values()]
        )
        group_weights = np.asarray(
            [float(np.max(matrix[rows, cell_index] / noise[rows])) for rows in grouped.values()]
        )
        pass_scores[cell_index] = float(
            np.average(group_consistency, weights=group_weights)
        )
        repeated_counts[cell_index] = sum(
            int(np.max(pass_counts[rows]) >= 2) for rows in grouped.values()
        )
        sensitivity[cell_index] = float(np.linalg.norm(group_weights))
        directions = np.column_stack(
            (
                np.cos(link_angles[representatives]),
                np.sin(link_angles[representatives]),
            )
        )
        direction_weights = group_weights**2
        fisher = (directions * direction_weights[:, None]).T @ directions
        eigenvalues = np.linalg.eigvalsh(fisher)
        if eigenvalues[-1] > 0.0:
            conditioning[cell_index] = float(eigenvalues[0] / eigenvalues[-1])

    grid_x, grid_y = np.meshgrid(x_centers_m, y_centers_m)
    cell_positions = np.column_stack((grid_x.ravel(), grid_y.ravel()))
    receiver_distances = np.linalg.norm(
        cell_positions[:, None, :] - receivers[None, :, :], axis=2
    )
    nearest_receiver = np.min(receiver_distances, axis=1)

    criteria = {
        "links": link_counts >= settings.min_links,
        "transmitters": transmitter_counts >= settings.min_transmitters,
        "angles": angle_counts >= settings.min_angle_bins,
        "receiver_distance": nearest_receiver <= settings.max_receiver_distance_m,
        "sensitivity": sensitivity >= settings.min_sensitivity,
        "conditioning": conditioning >= settings.min_conditioning_score,
        "pass_consistency": pass_scores >= settings.min_pass_consistency,
        "repeated_links": repeated_counts >= settings.min_repeated_links,
    }
    observable = np.logical_and.reduce(tuple(criteria.values()))
    failures = {name: int(np.count_nonzero(~passed)) for name, passed in criteria.items()}
    return SupportMetrics(
        link_count=link_counts.reshape(shape),
        transmitter_count=transmitter_counts.reshape(shape),
        angle_bin_count=angle_counts.reshape(shape),
        distance_to_receiver_m=nearest_receiver.reshape(shape),
        sensitivity=sensitivity.reshape(shape),
        conditioning_score=conditioning.reshape(shape),
        pass_consistency=pass_scores.reshape(shape),
        repeated_link_count=repeated_counts.reshape(shape),
        observable_mask=observable.reshape(shape),
        failed_criteria_counts=failures,
    )


def point_clearance_mask(
    points_xy_m: np.ndarray,
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
    clearance_radius_m: float,
) -> np.ndarray:
    points = np.asarray(points_xy_m, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
        raise ValueError("Clearance points must be a finite N x 2 array.")
    if clearance_radius_m < 0:
        raise ValueError("Clearance radius cannot be negative.")
    grid_x, grid_y = np.meshgrid(x_centers_m, y_centers_m)
    mask = np.zeros(grid_x.shape, dtype=bool)
    half_cell = 0.5 * min(float(np.diff(x_centers_m)[0]), float(np.diff(y_centers_m)[0]))
    effective_radius = max(clearance_radius_m, half_cell)
    for point in points:
        mask |= np.hypot(grid_x - point[0], grid_y - point[1]) <= effective_radius
    return mask


def extract_components(
    evidence_frequency: np.ndarray,
    observable_mask: np.ndarray,
    ray_matrix_m: np.ndarray,
    transmitter_ids: list[str] | np.ndarray,
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
    *,
    evidence_threshold: float,
    minimum_cells: int = 1,
) -> tuple[np.ndarray, list[ComponentMetric]]:
    evidence = np.asarray(evidence_frequency, dtype=float)
    observable = np.asarray(observable_mask, dtype=bool)
    x_centers_m = np.asarray(x_centers_m, dtype=float)
    y_centers_m = np.asarray(y_centers_m, dtype=float)
    shape = (len(y_centers_m), len(x_centers_m))
    matrix = np.asarray(ray_matrix_m, dtype=float)
    identifiers = np.asarray(transmitter_ids, dtype=str)
    if evidence.shape != shape or observable.shape != shape:
        raise ValueError("Evidence and observability must match the requested grid.")
    if (
        matrix.ndim != 2
        or matrix.shape[1] != evidence.size
        or identifiers.shape != (matrix.shape[0],)
    ):
        raise ValueError("Ray support does not match the evidence grid.")
    if (
        not np.isfinite(evidence).all()
        or np.any((evidence < 0.0) | (evidence > 1.0))
        or not np.isfinite(evidence_threshold)
        or not 0 <= evidence_threshold <= 1
        or isinstance(minimum_cells, bool)
        or not isinstance(minimum_cells, int)
        or minimum_cells < 1
    ):
        raise ValueError("Evidence threshold must be in [0, 1] and minimum cells positive.")
    if not np.isfinite(matrix).all() or np.any(matrix < 0.0):
        raise ValueError("Ray lengths must be finite and nonnegative.")

    candidates = observable & (evidence >= evidence_threshold)
    labels = np.zeros(shape, dtype=int)
    metrics: list[ComponentMetric] = []
    if len(x_centers_m) < 2 or len(y_centers_m) < 2:
        raise ValueError("Component grids require at least two centers per axis.")
    resolution_x = float(np.diff(x_centers_m)[0])
    resolution_y = float(np.diff(y_centers_m)[0])
    if (
        not np.isfinite(x_centers_m).all()
        or not np.isfinite(y_centers_m).all()
        or not np.allclose(np.diff(x_centers_m), resolution_x)
        or not np.allclose(np.diff(y_centers_m), resolution_y)
        or resolution_x <= 0.0
        or resolution_y <= 0.0
    ):
        raise ValueError("Component grids must be finite, uniform, and increasing.")
    if not np.isclose(resolution_x, resolution_y):
        raise ValueError("Component metrics currently require square grid cells.")
    resolution = resolution_x
    next_label = 0

    for start_y, start_x in zip(*np.nonzero(candidates)):
        if labels[start_y, start_x] != 0:
            continue
        stack = [(int(start_y), int(start_x))]
        cells: list[tuple[int, int]] = []
        labels[start_y, start_x] = -1
        while stack:
            y_index, x_index = stack.pop()
            cells.append((y_index, x_index))
            for neighbor_y, neighbor_x in (
                (y_index - 1, x_index),
                (y_index + 1, x_index),
                (y_index, x_index - 1),
                (y_index, x_index + 1),
            ):
                if (
                    0 <= neighbor_y < shape[0]
                    and 0 <= neighbor_x < shape[1]
                    and candidates[neighbor_y, neighbor_x]
                    and labels[neighbor_y, neighbor_x] == 0
                ):
                    labels[neighbor_y, neighbor_x] = -1
                    stack.append((neighbor_y, neighbor_x))
        if len(cells) < minimum_cells:
            for y_index, x_index in cells:
                labels[y_index, x_index] = 0
            continue

        next_label += 1
        for y_index, x_index in cells:
            labels[y_index, x_index] = next_label
        indices = np.asarray(cells, dtype=int)
        ys = indices[:, 0]
        xs = indices[:, 1]
        positions = np.column_stack((x_centers_m[xs], y_centers_m[ys]))
        centered = positions - np.mean(positions, axis=0)
        if len(cells) > 1:
            _, _, right_vectors = np.linalg.svd(centered, full_matrices=False)
            major_axis = right_vectors[0]
        else:
            major_axis = np.array([1.0, 0.0])
        minor_axis = np.array([-major_axis[1], major_axis[0]])
        major_projection = positions @ major_axis
        minor_projection = positions @ minor_axis
        major_dimension = float(np.ptp(major_projection) + resolution)
        minor_dimension = float(np.ptp(minor_projection) + resolution)
        if minor_dimension > major_dimension:
            major_dimension, minor_dimension = minor_dimension, major_dimension
            major_axis = minor_axis

        perimeter_edges = 0
        touches_unobserved = False
        flat_cells = ys * shape[1] + xs
        for y_index, x_index in cells:
            for neighbor_y, neighbor_x in (
                (y_index - 1, x_index),
                (y_index + 1, x_index),
                (y_index, x_index - 1),
                (y_index, x_index + 1),
            ):
                outside = not (0 <= neighbor_y < shape[0] and 0 <= neighbor_x < shape[1])
                if outside or not candidates[neighbor_y, neighbor_x]:
                    perimeter_edges += 1
                if outside or not observable[neighbor_y, neighbor_x]:
                    touches_unobserved = True
        supporting_rows = np.any(matrix[:, flat_cells] > 1e-9, axis=1)
        independent_support = {
            (
                identifiers[row_index],
                tuple(np.round(matrix[row_index], 9)),
            )
            for row_index in np.flatnonzero(supporting_rows)
        }
        component_evidence = evidence[ys, xs]
        metrics.append(
            ComponentMetric(
                component_id=next_label,
                cell_count=len(cells),
                supporting_links=len(independent_support),
                supporting_transmitters=int(np.unique(identifiers[supporting_rows]).size),
                area_m2=len(cells) * resolution * resolution,
                perimeter_m=perimeter_edges * resolution,
                axis_aligned_width_m=(int(np.ptp(xs)) + 1) * resolution,
                axis_aligned_height_m=(int(np.ptp(ys)) + 1) * resolution,
                oriented_major_m=major_dimension,
                oriented_minor_m=minor_dimension,
                orientation_deg=float(np.degrees(np.arctan2(major_axis[1], major_axis[0])) % 180.0),
                centroid_x_m=float(np.mean(positions[:, 0])),
                centroid_y_m=float(np.mean(positions[:, 1])),
                mean_evidence=float(np.mean(component_evidence)),
                minimum_evidence=float(np.min(component_evidence)),
                dimension_discretization_bound_m=resolution,
                touches_unobserved=touches_unobserved,
            )
        )
    return labels, metrics
