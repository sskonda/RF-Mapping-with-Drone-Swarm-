from __future__ import annotations

from dataclasses import dataclass

import numpy as np


UNKNOWN_EVIDENCE_SCORE = 0.5
LIMITED_FREE_EVIDENCE_SCORE = 0.05


@dataclass(frozen=True)
class AttenuationResult:
    attenuation_db_per_m: np.ndarray
    predicted_excess_db: np.ndarray
    residuals_db: np.ndarray
    objective_history: tuple[float, ...]
    iterations: int
    converged: bool


@dataclass(frozen=True)
class BootstrapEvidenceResult:
    evidence_frequency: np.ndarray
    converged_fit_count: int
    fit_count: int
    iterations: tuple[int, ...]


def grid_centers(
    minimum: float,
    maximum: float,
    resolution: float,
) -> np.ndarray:
    if not np.isfinite([minimum, maximum, resolution]).all():
        raise ValueError("Grid bounds and resolution must be finite.")
    if resolution <= 0 or maximum < minimum:
        raise ValueError("Grid resolution must be positive and maximum >= minimum.")
    interval_count = (maximum - minimum) / resolution
    if not np.isclose(interval_count, round(interval_count), rtol=1e-9, atol=1e-12):
        raise ValueError("Grid bound span must be an integer multiple of resolution.")
    count = int(round(interval_count)) + 1
    return minimum + np.arange(count, dtype=float) * resolution


def _cell_edges(centers: np.ndarray) -> np.ndarray:
    values = np.asarray(centers, dtype=float)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError("Grid centers must be a finite, non-empty 1D array.")
    if values.size == 1:
        raise ValueError("At least two grid centers are required for ray tracing.")
    differences = np.diff(values)
    if not np.allclose(differences, differences[0]) or differences[0] <= 0:
        raise ValueError("Grid centers must be uniformly spaced and increasing.")
    half = differences[0] / 2.0
    return np.concatenate(([values[0] - half], values[:-1] + half, [values[-1] + half]))


def _clip_parameter_interval(
    start: np.ndarray,
    delta: np.ndarray,
    x_edges: np.ndarray,
    y_edges: np.ndarray,
) -> tuple[float, float] | None:
    lower = 0.0
    upper = 1.0
    for origin, direction, minimum, maximum in (
        (start[0], delta[0], x_edges[0], x_edges[-1]),
        (start[1], delta[1], y_edges[0], y_edges[-1]),
    ):
        if direction == 0.0:
            if origin < minimum or origin > maximum:
                return None
            continue
        first = (minimum - origin) / direction
        second = (maximum - origin) / direction
        axis_lower, axis_upper = sorted((first, second))
        lower = max(lower, axis_lower)
        upper = min(upper, axis_upper)
        if upper <= lower:
            return None
    return lower, upper


def line_grid_intersection_lengths(
    start_xy_m: np.ndarray | tuple[float, float],
    end_xy_m: np.ndarray | tuple[float, float],
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
) -> np.ndarray:
    """Return exact segment length in each cell, with rows ordered y then x.

    A segment exactly on an internal boundary is assigned to the cell on the
    positive side of that boundary. This half-open convention prevents double
    counting while preserving the total in-grid path length.
    """

    start = np.asarray(start_xy_m, dtype=float)
    end = np.asarray(end_xy_m, dtype=float)
    if start.shape != (2,) or end.shape != (2,) or not np.isfinite([start, end]).all():
        raise ValueError("Ray endpoints must each contain two finite coordinates.")
    x_edges = _cell_edges(x_centers_m)
    y_edges = _cell_edges(y_centers_m)
    output = np.zeros((len(y_centers_m), len(x_centers_m)), dtype=float)
    delta = end - start
    total_length = float(np.linalg.norm(delta))
    if total_length == 0.0:
        return output

    clipped = _clip_parameter_interval(start, delta, x_edges, y_edges)
    if clipped is None:
        return output
    lower, upper = clipped
    crossings = [lower, upper]
    if delta[0] != 0.0:
        x_parameters = (x_edges[1:-1] - start[0]) / delta[0]
        crossings.extend(x_parameters[(x_parameters > lower) & (x_parameters < upper)])
    if delta[1] != 0.0:
        y_parameters = (y_edges[1:-1] - start[1]) / delta[1]
        crossings.extend(y_parameters[(y_parameters > lower) & (y_parameters < upper)])
    parameters = np.unique(np.asarray(crossings, dtype=float))

    for interval_start, interval_end in zip(parameters[:-1], parameters[1:]):
        if interval_end <= interval_start:
            continue
        midpoint = start + (0.5 * (interval_start + interval_end)) * delta
        x_index = int(np.searchsorted(x_edges, midpoint[0], side="right") - 1)
        y_index = int(np.searchsorted(y_edges, midpoint[1], side="right") - 1)
        x_index = min(max(x_index, 0), len(x_centers_m) - 1)
        y_index = min(max(y_index, 0), len(y_centers_m) - 1)
        output[y_index, x_index] += (interval_end - interval_start) * total_length
    return output


def build_ray_matrix(
    transmitter_xy_m: np.ndarray,
    receiver_xy_m: np.ndarray,
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
) -> np.ndarray:
    transmitters = np.asarray(transmitter_xy_m, dtype=float)
    receivers = np.asarray(receiver_xy_m, dtype=float)
    if (
        transmitters.ndim != 2
        or transmitters.shape[1] != 2
        or receivers.shape != transmitters.shape
        or not np.isfinite(transmitters).all()
        or not np.isfinite(receivers).all()
    ):
        raise ValueError("Transmitter and receiver positions must be matching N x 2 arrays.")
    rows = [
        line_grid_intersection_lengths(start, end, x_centers_m, y_centers_m).ravel()
        for start, end in zip(transmitters, receivers)
    ]
    return np.asarray(rows, dtype=float)


def _tv_value_and_gradient(
    values: np.ndarray,
    epsilon: float,
) -> tuple[float, np.ndarray]:
    horizontal = values[:, 1:] - values[:, :-1]
    vertical = values[1:, :] - values[:-1, :]
    horizontal_scale = np.sqrt(horizontal * horizontal + epsilon * epsilon)
    vertical_scale = np.sqrt(vertical * vertical + epsilon * epsilon)
    gradient = np.zeros_like(values)
    horizontal_direction = horizontal / horizontal_scale
    vertical_direction = vertical / vertical_scale
    gradient[:, 1:] += horizontal_direction
    gradient[:, :-1] -= horizontal_direction
    gradient[1:, :] += vertical_direction
    gradient[:-1, :] -= vertical_direction
    value = float(
        np.sum(horizontal_scale - epsilon) + np.sum(vertical_scale - epsilon)
    )
    return value, gradient


def _spectral_norm_power(matrix: np.ndarray, iterations: int = 30) -> float:
    if matrix.size == 0 or not np.any(matrix):
        return 0.0
    vector = np.full(matrix.shape[1], 1.0 / np.sqrt(matrix.shape[1]))
    for _ in range(iterations):
        projected = matrix.T @ (matrix @ vector)
        norm = float(np.linalg.norm(projected))
        if norm == 0.0:
            return 0.0
        vector = projected / norm
    return float(np.linalg.norm(matrix @ vector))


def attenuation_objective(
    attenuation_db_per_m: np.ndarray,
    ray_matrix_m: np.ndarray,
    excess_attenuation_db: np.ndarray,
    noise_standard_deviation_db: np.ndarray,
    lambda_l1: float,
    lambda_tv: float,
    tv_epsilon: float,
    grid_shape: tuple[int, int],
    cell_size_m: float = 1.0,
) -> float:
    values = np.asarray(attenuation_db_per_m, dtype=float).reshape(grid_shape)
    residual = ray_matrix_m @ values.ravel() - excess_attenuation_db
    weighted_error = residual / noise_standard_deviation_db
    tv_value, _ = _tv_value_and_gradient(values, tv_epsilon)
    return float(
        0.5 * weighted_error @ weighted_error
        + lambda_l1 * cell_size_m**2 * np.sum(values)
        + lambda_tv * cell_size_m * tv_value
    )


def fit_attenuation_map(
    ray_matrix_m: np.ndarray,
    excess_attenuation_db: np.ndarray,
    noise_standard_deviation_db: np.ndarray,
    grid_shape: tuple[int, int],
    *,
    lambda_l1: float = 0.2,
    lambda_tv: float = 0.5,
    tv_epsilon: float = 0.05,
    cell_size_m: float = 1.0,
    max_iterations: int = 1000,
    relative_tolerance: float = 1e-5,
) -> AttenuationResult:
    """Fit nonnegative attenuation with sparse and smoothed anisotropic-TV priors."""

    matrix = np.asarray(ray_matrix_m, dtype=float)
    observations = np.asarray(excess_attenuation_db, dtype=float)
    noise = np.asarray(noise_standard_deviation_db, dtype=float)
    if (
        not isinstance(grid_shape, tuple)
        or len(grid_shape) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in grid_shape)
    ):
        raise ValueError("grid_shape must contain two positive integers.")
    cell_count = int(np.prod(grid_shape))
    if matrix.ndim != 2 or matrix.shape != (observations.size, cell_count):
        raise ValueError("Ray matrix shape is inconsistent with observations/grid.")
    if noise.shape != observations.shape or np.any(noise <= 0):
        raise ValueError("Noise standard deviations must be positive and match observations.")
    if (
        not np.isfinite(matrix).all()
        or np.any(matrix < 0.0)
        or not np.isfinite(observations).all()
        or not np.isfinite(noise).all()
    ):
        raise ValueError("Attenuation inputs must be finite.")
    parameters = np.asarray(
        [lambda_l1, lambda_tv, tv_epsilon, cell_size_m, relative_tolerance],
        dtype=float,
    )
    if not np.isfinite(parameters).all():
        raise ValueError("Optimizer parameters must be finite.")
    if min(lambda_l1, lambda_tv) < 0 or tv_epsilon <= 0 or cell_size_m <= 0:
        raise ValueError("Regularization must be nonnegative and TV epsilon positive.")
    if (
        isinstance(max_iterations, bool)
        or not isinstance(max_iterations, int)
        or max_iterations <= 0
        or relative_tolerance <= 0
    ):
        raise ValueError("Optimizer limits must be positive.")

    weighted_matrix = matrix / noise[:, None]
    spectral_norm = _spectral_norm_power(weighted_matrix)
    lipschitz_bound = (
        spectral_norm * spectral_norm
        + 8.0 * lambda_tv * cell_size_m / tv_epsilon
    )
    step = 1.0 / max(lipschitz_bound, 1e-12)
    attenuation = np.zeros(cell_count, dtype=float)
    history: list[float] = []
    converged = False

    for iteration in range(1, max_iterations + 1):
        grid = attenuation.reshape(grid_shape)
        residual = matrix @ attenuation - observations
        _, tv_gradient = _tv_value_and_gradient(grid, tv_epsilon)
        gradient = (
            matrix.T @ (residual / (noise * noise))
            + lambda_l1 * cell_size_m**2
            + lambda_tv * cell_size_m * tv_gradient.ravel()
        )
        current_objective = attenuation_objective(
            attenuation,
            matrix,
            observations,
            noise,
            lambda_l1,
            lambda_tv,
            tv_epsilon,
            grid_shape,
            cell_size_m,
        )

        accepted_step = step
        for _ in range(30):
            candidate = np.maximum(0.0, attenuation - accepted_step * gradient)
            delta = candidate - attenuation
            candidate_objective = attenuation_objective(
                candidate,
                matrix,
                observations,
                noise,
                lambda_l1,
                lambda_tv,
                tv_epsilon,
                grid_shape,
                cell_size_m,
            )
            upper_bound = (
                current_objective
                + float(gradient @ delta)
                + float(delta @ delta) / (2.0 * accepted_step)
            )
            if candidate_objective <= upper_bound + 1e-10:
                break
            accepted_step *= 0.5
        else:
            raise RuntimeError("Attenuation optimizer line search failed.")

        history.append(candidate_objective)
        change = float(np.linalg.norm(delta))
        scale = max(1.0, float(np.linalg.norm(attenuation)))
        relative_objective_change = abs(candidate_objective - current_objective) / max(
            1.0, abs(current_objective)
        )
        attenuation = candidate
        step = min(accepted_step * 1.05, 1.0 / max(spectral_norm * spectral_norm, 1e-12))
        if (
            change <= relative_tolerance * scale
            or relative_objective_change <= relative_tolerance
        ):
            converged = True
            break

    predicted = matrix @ attenuation
    return AttenuationResult(
        attenuation_db_per_m=attenuation.reshape(grid_shape),
        predicted_excess_db=predicted,
        residuals_db=observations - predicted,
        objective_history=tuple(history),
        iterations=iteration,
        converged=converged,
    )


def bootstrap_attenuation_evidence(
    ray_matrix_m: np.ndarray,
    excess_attenuation_db: np.ndarray,
    noise_standard_deviation_db: np.ndarray,
    grid_shape: tuple[int, int],
    *,
    seed: int,
    bootstrap_count: int,
    attenuation_threshold_db_per_m: float,
    fit_options: dict[str, float | int] | None = None,
) -> np.ndarray:
    """Return fitted-model parametric-bootstrap attenuation exceedance frequency."""

    base = fit_attenuation_map(
        ray_matrix_m,
        excess_attenuation_db,
        noise_standard_deviation_db,
        grid_shape,
        **(fit_options or {}),
    )
    return bootstrap_attenuation_evidence_with_diagnostics(
        ray_matrix_m,
        base.predicted_excess_db,
        noise_standard_deviation_db,
        grid_shape,
        seed=seed,
        bootstrap_count=bootstrap_count,
        attenuation_threshold_db_per_m=attenuation_threshold_db_per_m,
        fit_options=fit_options,
    ).evidence_frequency


def bootstrap_attenuation_evidence_with_diagnostics(
    ray_matrix_m: np.ndarray,
    fitted_excess_attenuation_db: np.ndarray,
    noise_standard_deviation_db: np.ndarray,
    grid_shape: tuple[int, int],
    *,
    seed: int,
    bootstrap_count: int,
    attenuation_threshold_db_per_m: float,
    fit_options: dict[str, float | int] | None = None,
) -> BootstrapEvidenceResult:
    """Refit draws from the fitted Gaussian forward model and report convergence."""

    if (
        isinstance(bootstrap_count, bool)
        or not isinstance(bootstrap_count, int)
        or bootstrap_count <= 0
        or not np.isfinite(attenuation_threshold_db_per_m)
        or attenuation_threshold_db_per_m < 0
    ):
        raise ValueError("Bootstrap count must be positive and threshold nonnegative.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
        raise ValueError("Bootstrap seed must be an integer in [0, 2**63).")
    rng = np.random.default_rng(seed)
    exceedances = np.zeros(grid_shape, dtype=float)
    options = fit_options or {}
    iterations: list[int] = []
    converged_count = 0
    for _ in range(bootstrap_count):
        sampled = rng.normal(
            fitted_excess_attenuation_db, noise_standard_deviation_db
        )
        fitted = fit_attenuation_map(
            ray_matrix_m,
            sampled,
            noise_standard_deviation_db,
            grid_shape,
            **options,
        )
        iterations.append(fitted.iterations)
        converged_count += int(fitted.converged)
        exceedances += fitted.attenuation_db_per_m >= attenuation_threshold_db_per_m
    return BootstrapEvidenceResult(
        evidence_frequency=exceedances / bootstrap_count,
        converged_fit_count=converged_count,
        fit_count=bootstrap_count,
        iterations=tuple(iterations),
    )


def occupancy_from_evidence(
    evidence_frequency: np.ndarray,
    observable_mask: np.ndarray,
    traversed_free_mask: np.ndarray,
    ap_free_mask: np.ndarray,
    *,
    occupied_activation: float = 0.5,
    known_free_score: float = LIMITED_FREE_EVIDENCE_SCORE,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a conservative evidence score; unresolved cells remain exactly 0.5.

    This bookkeeping score is not a physical occupancy posterior and must not
    authorize navigation through RF-only clear or unknown space.
    """

    evidence = np.asarray(evidence_frequency, dtype=float)
    observable = np.asarray(observable_mask, dtype=bool)
    traversed = np.asarray(traversed_free_mask, dtype=bool)
    ap_cells = np.asarray(ap_free_mask, dtype=bool)
    if not (evidence.shape == observable.shape == traversed.shape == ap_cells.shape):
        raise ValueError("Occupancy arrays must have identical shapes.")
    if not np.isfinite(evidence).all() or not np.isfinite(known_free_score):
        raise ValueError("Evidence and free score must be finite.")
    if np.any((evidence < 0) | (evidence > 1)) or not 0 < known_free_score < 0.5:
        raise ValueError("Evidence must be in [0, 1] and free score in (0, 0.5).")
    if not np.isfinite(occupied_activation) or not 0 < occupied_activation <= 1:
        raise ValueError("Occupied activation must be in (0, 1].")

    occupancy_score = np.full(evidence.shape, UNKNOWN_EVIDENCE_SCORE, dtype=float)
    active = observable & (evidence >= occupied_activation)
    if occupied_activation == 1.0:
        occupancy_score[active] = 1.0
    else:
        occupancy_score[active] = UNKNOWN_EVIDENCE_SCORE + (
            1.0 - UNKNOWN_EVIDENCE_SCORE
        ) * (
            (evidence[active] - occupied_activation)
            / (1.0 - occupied_activation)
        )
    # 0 unknown, 1 limited free evidence, 2 attenuation evidence, 3 conflict.
    states = np.zeros(evidence.shape, dtype=np.uint8)
    states[active] = 2
    known_free = traversed | ap_cells
    occupancy_score[known_free] = known_free_score
    states[known_free] = 1
    conflicts = known_free & active
    occupancy_score[conflicts] = UNKNOWN_EVIDENCE_SCORE
    states[conflicts] = 3
    return occupancy_score, states
