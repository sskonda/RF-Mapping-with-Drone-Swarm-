"""Small-data path-loss plus Gaussian-process RF field estimation.

The posterior represents a model estimate, not additional measurements.  The
path-loss calibration is treated as fixed; posterior uncertainty therefore
covers only the residual field under the selected kernel and noise model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SupportMetrics:
    """Geometric support for query locations in the horizontal plane."""

    distance_to_sample_m: np.ndarray
    effective_density: np.ndarray
    inside_convex_hull: np.ndarray
    extrapolation_mask: np.ndarray


@dataclass(frozen=True)
class FieldPosterior:
    """Posterior arrays, one value per query location."""

    mean_dbm: np.ndarray
    standard_deviation_db: np.ndarray
    path_loss_mean_dbm: np.ndarray
    residual_mean_db: np.ndarray
    support: SupportMetrics


@dataclass(frozen=True)
class LeaveOneLocationOutDiagnostics:
    """Predictions made after withholding every sample at one location."""

    locations_xyz_m: np.ndarray
    observed_mean_dbm: np.ndarray
    predicted_mean_dbm: np.ndarray
    predicted_standard_deviation_db: np.ndarray
    residual_db: np.ndarray
    rmse_db: float
    mae_db: float


@dataclass(frozen=True)
class ResolutionDiagnostics:
    """Relationship between display pixels and physical/model support."""

    grid_resolution_m: float
    median_measurement_spacing_m: float | None
    measurement_spacing_to_grid_ratio: float | None
    correlation_length_to_grid_ratio: float
    warnings: tuple[str, ...]


def _as_xyz(values: np.ndarray, name: str) -> np.ndarray:
    points = np.asarray(values, dtype=float)
    if points.ndim == 1:
        points = points.reshape(1, -1)
    if points.ndim != 2 or points.shape[1] not in (2, 3):
        raise ValueError(f"{name} must have shape (n, 2) or (n, 3)")
    if points.shape[0] == 0:
        raise ValueError(f"{name} cannot be empty")
    if not np.all(np.isfinite(points)):
        raise ValueError(f"{name} must contain only finite values")
    if points.shape[1] == 2:
        points = np.column_stack((points, np.zeros(points.shape[0])))
    return points


def _as_position_xyz(value: np.ndarray, name: str) -> np.ndarray:
    position = np.asarray(value, dtype=float)
    if position.ndim != 1 or position.size not in (2, 3):
        raise ValueError(f"{name} must contain two or three coordinates")
    if not np.all(np.isfinite(position)):
        raise ValueError(f"{name} must contain only finite values")
    if position.size == 2:
        position = np.append(position, 0.0)
    return position


def _positive_finite(value: float, name: str) -> float:
    parsed = float(value)
    if not np.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{name} must be finite and greater than zero")
    return parsed


def path_loss_mean(
    receiver_positions_m: np.ndarray,
    ap_position_m: np.ndarray,
    *,
    p0_dbm: float,
    path_loss_exponent: float,
    reference_distance_m: float = 1.0,
    minimum_distance_m: float = 1e-3,
) -> np.ndarray:
    """Evaluate ``P0 - 10 n log10(d / d0)`` using 3D link distance.

    ``minimum_distance_m`` only prevents the logarithmic singularity at the AP.
    Analyses should normally mask distances below their calibration range.
    """

    receivers = _as_xyz(receiver_positions_m, "receiver_positions_m")
    ap_position = _as_position_xyz(ap_position_m, "ap_position_m")
    p0 = float(p0_dbm)
    if not np.isfinite(p0):
        raise ValueError("p0_dbm must be finite")
    exponent = _positive_finite(path_loss_exponent, "path_loss_exponent")
    reference_distance = _positive_finite(
        reference_distance_m, "reference_distance_m"
    )
    minimum_distance = _positive_finite(minimum_distance_m, "minimum_distance_m")

    distances = np.linalg.norm(receivers - ap_position, axis=1)
    distances = np.maximum(distances, minimum_distance)
    return p0 - 10.0 * exponent * np.log10(distances / reference_distance)


def rbf_kernel(
    first_positions_m: np.ndarray,
    second_positions_m: np.ndarray,
    *,
    length_scale_m: float,
    signal_std_db: float,
) -> np.ndarray:
    """Return an isotropic squared-exponential covariance matrix."""

    first = _as_xyz(first_positions_m, "first_positions_m")
    second = _as_xyz(second_positions_m, "second_positions_m")
    length_scale = _positive_finite(length_scale_m, "length_scale_m")
    signal_std = _positive_finite(signal_std_db, "signal_std_db")
    differences = first[:, np.newaxis, :] - second[np.newaxis, :, :]
    squared_distances = np.einsum("ijk,ijk->ij", differences, differences)
    return signal_std**2 * np.exp(-0.5 * squared_distances / length_scale**2)


def convex_hull_2d(positions_m: np.ndarray) -> np.ndarray:
    """Return counter-clockwise convex-hull vertices using a monotone chain."""

    points = _as_xyz(positions_m, "positions_m")[:, :2]
    ordered = sorted({(float(x), float(y)) for x, y in points})
    if len(ordered) <= 1:
        return np.asarray(ordered, dtype=float).reshape(-1, 2)

    def cross(
        origin: tuple[float, float],
        first: tuple[float, float],
        second: tuple[float, float],
    ) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in ordered:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0.0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(ordered):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0.0:
            upper.pop()
        upper.append(point)

    return np.asarray(lower[:-1] + upper[:-1], dtype=float)


def points_inside_convex_hull_2d(
    query_positions_m: np.ndarray,
    hull_vertices_m: np.ndarray,
    *,
    tolerance_m: float = 1e-9,
) -> np.ndarray:
    """Classify points on or inside a convex hull, including degenerate hulls."""

    queries = _as_xyz(query_positions_m, "query_positions_m")[:, :2]
    hull = np.asarray(hull_vertices_m, dtype=float)
    if hull.ndim != 2 or hull.shape[1] != 2 or hull.shape[0] == 0:
        raise ValueError("hull_vertices_m must have shape (n, 2) with n >= 1")
    if not np.all(np.isfinite(hull)):
        raise ValueError("hull_vertices_m must contain only finite values")
    tolerance = float(tolerance_m)
    if not np.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("tolerance_m must be finite and non-negative")

    if hull.shape[0] == 1:
        return np.linalg.norm(queries - hull[0], axis=1) <= tolerance

    if hull.shape[0] == 2:
        segment = hull[1] - hull[0]
        segment_length_squared = float(segment @ segment)
        if segment_length_squared == 0.0:
            return np.linalg.norm(queries - hull[0], axis=1) <= tolerance
        offsets = queries - hull[0]
        parameters = offsets @ segment / segment_length_squared
        projections = hull[0] + parameters[:, np.newaxis] * segment
        on_line = np.linalg.norm(queries - projections, axis=1) <= tolerance
        return on_line & (parameters >= -tolerance) & (parameters <= 1.0 + tolerance)

    edges = np.roll(hull, -1, axis=0) - hull
    offsets = queries[:, np.newaxis, :] - hull[np.newaxis, :, :]
    cross_products = (
        edges[np.newaxis, :, 0] * offsets[:, :, 1]
        - edges[np.newaxis, :, 1] * offsets[:, :, 0]
    )
    scaled_tolerance = tolerance * np.maximum(
        1.0, np.linalg.norm(edges, axis=1)
    )
    return np.all(cross_products >= -scaled_tolerance[np.newaxis, :], axis=1)


def support_metrics(
    observation_positions_m: np.ndarray,
    query_positions_m: np.ndarray,
    *,
    length_scale_m: float,
) -> SupportMetrics:
    """Compute nearest-sample distance, kernel density, and hull support."""

    observations = np.unique(
        _as_xyz(observation_positions_m, "observation_positions_m")[:, :2], axis=0
    )
    queries = _as_xyz(query_positions_m, "query_positions_m")[:, :2]
    length_scale = _positive_finite(length_scale_m, "length_scale_m")
    differences = queries[:, np.newaxis, :] - observations[np.newaxis, :, :]
    squared_distances = np.einsum("ijk,ijk->ij", differences, differences)
    distances = np.sqrt(np.min(squared_distances, axis=1))
    density = np.sum(
        np.exp(-0.5 * squared_distances / length_scale**2), axis=1
    )
    hull = convex_hull_2d(observations)
    inside = points_inside_convex_hull_2d(queries, hull)
    return SupportMetrics(
        distance_to_sample_m=distances,
        effective_density=density,
        inside_convex_hull=inside,
        extrapolation_mask=~inside,
    )


def display_resolution_diagnostics(
    observation_positions_m: np.ndarray,
    *,
    grid_resolution_m: float,
    length_scale_m: float,
    material_ratio: float = 4.0,
) -> ResolutionDiagnostics:
    """Warn when display sampling materially exceeds data/model resolution."""

    observations = np.unique(
        _as_xyz(observation_positions_m, "observation_positions_m")[:, :2], axis=0
    )
    grid_resolution = _positive_finite(grid_resolution_m, "grid_resolution_m")
    length_scale = _positive_finite(length_scale_m, "length_scale_m")
    ratio_threshold = _positive_finite(material_ratio, "material_ratio")
    warnings: list[str] = []

    median_spacing: float | None = None
    spacing_ratio: float | None = None
    if observations.shape[0] >= 2:
        differences = observations[:, np.newaxis, :] - observations[np.newaxis, :, :]
        distances = np.linalg.norm(differences, axis=2)
        np.fill_diagonal(distances, np.inf)
        median_spacing = float(np.median(np.min(distances, axis=1)))
        spacing_ratio = median_spacing / grid_resolution
        if spacing_ratio >= ratio_threshold:
            warnings.append(
                "Display pixels are materially finer than the median physical "
                "measurement spacing; they do not add measured resolution."
            )
    else:
        warnings.append(
            "Measurement spacing is unavailable because fewer than two unique "
            "locations were supplied."
        )

    correlation_ratio = length_scale / grid_resolution
    if correlation_ratio >= ratio_threshold:
        warnings.append(
            "Display pixels are materially finer than the GP correlation length; "
            "fine pixels are samples of the same smooth model."
        )
    return ResolutionDiagnostics(
        grid_resolution_m=grid_resolution,
        median_measurement_spacing_m=median_spacing,
        measurement_spacing_to_grid_ratio=spacing_ratio,
        correlation_length_to_grid_ratio=correlation_ratio,
        warnings=tuple(warnings),
    )


class RFFieldGP:
    """Path-loss mean plus an RBF GP, or an explicit constant-mean fallback."""

    def __init__(
        self,
        *,
        ap_position_m: np.ndarray | None,
        p0_dbm: float,
        path_loss_exponent: float | None,
        reference_distance_m: float = 1.0,
        minimum_distance_m: float = 1e-3,
        length_scale_m: float = 0.5,
        signal_std_db: float = 6.0,
        noise_floor_db: float = 1.0,
        initial_jitter_db2: float = 1e-10,
        jitter_multiplier: float = 10.0,
        max_cholesky_attempts: int = 10,
    ) -> None:
        self.p0_dbm = float(p0_dbm)
        if not np.isfinite(self.p0_dbm):
            raise ValueError("p0_dbm must be finite")
        if (ap_position_m is None) != (path_loss_exponent is None):
            raise ValueError(
                "ap_position_m and path_loss_exponent must either both be set "
                "or both be None for an exploratory constant mean."
            )
        self.ap_position_m = (
            None
            if ap_position_m is None
            else _as_position_xyz(ap_position_m, "ap_position_m")
        )
        self.path_loss_exponent = (
            None
            if path_loss_exponent is None
            else _positive_finite(path_loss_exponent, "path_loss_exponent")
        )
        self.reference_distance_m = _positive_finite(
            reference_distance_m, "reference_distance_m"
        )
        self.minimum_distance_m = _positive_finite(
            minimum_distance_m, "minimum_distance_m"
        )
        self.length_scale_m = _positive_finite(length_scale_m, "length_scale_m")
        self.signal_std_db = _positive_finite(signal_std_db, "signal_std_db")
        self.noise_floor_db = float(noise_floor_db)
        if not np.isfinite(self.noise_floor_db) or self.noise_floor_db < 0.0:
            raise ValueError("noise_floor_db must be finite and non-negative")
        self.initial_jitter_db2 = _positive_finite(
            initial_jitter_db2, "initial_jitter_db2"
        )
        self.jitter_multiplier = _positive_finite(
            jitter_multiplier, "jitter_multiplier"
        )
        if self.jitter_multiplier <= 1.0:
            raise ValueError("jitter_multiplier must be greater than one")
        if not isinstance(max_cholesky_attempts, int) or max_cholesky_attempts < 1:
            raise ValueError("max_cholesky_attempts must be a positive integer")
        self.max_cholesky_attempts = max_cholesky_attempts
        self._observation_positions_m: np.ndarray | None = None
        self._observed_rssi_dbm: np.ndarray | None = None
        self._observation_variance_db2: np.ndarray | None = None
        self._cholesky_factor: np.ndarray | None = None
        self._alpha: np.ndarray | None = None
        self._jitter_used_db2: float | None = None

    @property
    def jitter_used_db2(self) -> float:
        if self._jitter_used_db2 is None:
            raise RuntimeError("fit must be called before reading jitter_used_db2")
        return self._jitter_used_db2

    def _path_loss(self, positions_m: np.ndarray) -> np.ndarray:
        if self.ap_position_m is None or self.path_loss_exponent is None:
            return np.full(len(positions_m), self.p0_dbm, dtype=float)
        return path_loss_mean(
            positions_m,
            self.ap_position_m,
            p0_dbm=self.p0_dbm,
            path_loss_exponent=self.path_loss_exponent,
            reference_distance_m=self.reference_distance_m,
            minimum_distance_m=self.minimum_distance_m,
        )

    def fit(
        self,
        observation_positions_m: np.ndarray,
        observed_rssi_dbm: np.ndarray,
        observation_variance_db2: np.ndarray | float | None = None,
    ) -> RFFieldGP:
        """Fit residual weights with heteroscedastic diagonal noise."""

        positions = _as_xyz(observation_positions_m, "observation_positions_m")
        rssi = np.asarray(observed_rssi_dbm, dtype=float)
        if rssi.ndim != 1 or rssi.shape[0] != positions.shape[0]:
            raise ValueError("observed_rssi_dbm must have shape (n,)")
        if not np.all(np.isfinite(rssi)):
            raise ValueError("observed_rssi_dbm must contain only finite values")

        if observation_variance_db2 is None:
            variances = np.zeros(positions.shape[0], dtype=float)
        else:
            variances = np.asarray(observation_variance_db2, dtype=float)
            if variances.ndim == 0:
                variances = np.full(positions.shape[0], float(variances))
            if variances.ndim != 1 or variances.shape[0] != positions.shape[0]:
                raise ValueError("observation_variance_db2 must be scalar or shape (n,)")
            if not np.all(np.isfinite(variances)) or np.any(variances < 0.0):
                raise ValueError(
                    "observation_variance_db2 must be finite and non-negative"
                )

        covariance = rbf_kernel(
            positions,
            positions,
            length_scale_m=self.length_scale_m,
            signal_std_db=self.signal_std_db,
        )
        diagonal_noise = variances + self.noise_floor_db**2
        residuals = rssi - self._path_loss(positions)
        jitter = self.initial_jitter_db2
        cholesky_factor: np.ndarray | None = None
        for _ in range(self.max_cholesky_attempts):
            try:
                cholesky_factor = np.linalg.cholesky(
                    covariance + np.diag(diagonal_noise + jitter)
                )
                break
            except np.linalg.LinAlgError:
                jitter *= self.jitter_multiplier
        if cholesky_factor is None:
            raise np.linalg.LinAlgError(
                "GP covariance remained non-positive-definite after escalating jitter"
            )

        intermediate = np.linalg.solve(cholesky_factor, residuals)
        self._alpha = np.linalg.solve(cholesky_factor.T, intermediate)
        self._observation_positions_m = positions.copy()
        self._observed_rssi_dbm = rssi.copy()
        self._observation_variance_db2 = variances.copy()
        self._cholesky_factor = cholesky_factor
        self._jitter_used_db2 = jitter
        return self

    def predict(
        self,
        query_positions_m: np.ndarray,
        *,
        include_measurement_noise: bool = False,
    ) -> FieldPosterior:
        """Predict the latent RF field and its conditional standard deviation."""

        if (
            self._observation_positions_m is None
            or self._cholesky_factor is None
            or self._alpha is None
        ):
            raise RuntimeError("fit must be called before predict")
        queries = _as_xyz(query_positions_m, "query_positions_m")
        cross_covariance = rbf_kernel(
            queries,
            self._observation_positions_m,
            length_scale_m=self.length_scale_m,
            signal_std_db=self.signal_std_db,
        )
        residual_mean = cross_covariance @ self._alpha
        projected = np.linalg.solve(self._cholesky_factor, cross_covariance.T)
        posterior_variance = self.signal_std_db**2 - np.einsum(
            "ij,ij->j", projected, projected
        )
        posterior_variance = np.maximum(posterior_variance, 0.0)
        if include_measurement_noise:
            posterior_variance += self.noise_floor_db**2
        path_mean = self._path_loss(queries)
        return FieldPosterior(
            mean_dbm=path_mean + residual_mean,
            standard_deviation_db=np.sqrt(posterior_variance),
            path_loss_mean_dbm=path_mean,
            residual_mean_db=residual_mean,
            support=support_metrics(
                self._observation_positions_m,
                queries,
                length_scale_m=self.length_scale_m,
            ),
        )

    def leave_one_location_out(self) -> LeaveOneLocationOutDiagnostics | None:
        """Return location-level cross-validation, or ``None`` below four sites."""

        if (
            self._observation_positions_m is None
            or self._observed_rssi_dbm is None
            or self._observation_variance_db2 is None
        ):
            raise RuntimeError("fit must be called before leave_one_location_out")
        locations, location_indices = np.unique(
            self._observation_positions_m, axis=0, return_inverse=True
        )
        if locations.shape[0] < 4:
            return None

        observed_means = np.empty(locations.shape[0], dtype=float)
        predicted_means = np.empty(locations.shape[0], dtype=float)
        predicted_standard_deviations = np.empty(locations.shape[0], dtype=float)
        for index, location in enumerate(locations):
            held_out = location_indices == index
            observed_means[index] = float(np.mean(self._observed_rssi_dbm[held_out]))
            training = ~held_out
            model = RFFieldGP(
                ap_position_m=self.ap_position_m,
                p0_dbm=self.p0_dbm,
                path_loss_exponent=self.path_loss_exponent,
                reference_distance_m=self.reference_distance_m,
                minimum_distance_m=self.minimum_distance_m,
                length_scale_m=self.length_scale_m,
                signal_std_db=self.signal_std_db,
                noise_floor_db=self.noise_floor_db,
                initial_jitter_db2=self.initial_jitter_db2,
                jitter_multiplier=self.jitter_multiplier,
                max_cholesky_attempts=self.max_cholesky_attempts,
            ).fit(
                self._observation_positions_m[training],
                self._observed_rssi_dbm[training],
                self._observation_variance_db2[training],
            )
            posterior = model.predict(location)
            predicted_means[index] = posterior.mean_dbm[0]
            predicted_standard_deviations[index] = posterior.standard_deviation_db[0]

        residuals = observed_means - predicted_means
        return LeaveOneLocationOutDiagnostics(
            locations_xyz_m=locations,
            observed_mean_dbm=observed_means,
            predicted_mean_dbm=predicted_means,
            predicted_standard_deviation_db=predicted_standard_deviations,
            residual_db=residuals,
            rmse_db=float(np.sqrt(np.mean(residuals**2))),
            mae_db=float(np.mean(np.abs(residuals))),
        )
