"""Deterministic synthetic data and quantitative validation for RF mapping.

The generator models scalar RSSI with known path loss, pass drift, sample noise,
and optional line-integrated attenuation.  Its bootstrap values are evidence
frequencies under this synthetic model, not posterior occupancy probabilities.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from rf_mapping.artifacts import file_sha256, json_safe, write_deterministic_npz
from rf_mapping.calibration import (
    fit_log_distance_calibration,
    load_calibration_csv,
    save_calibration,
)
from rf_mapping.observability import (
    ComponentMetric,
    ObservabilityConfig,
    SupportMetrics,
    calculate_support,
    extract_components,
)
from rf_mapping.occupancy import (
    AttenuationResult,
    bootstrap_attenuation_evidence_with_diagnostics,
    build_ray_matrix,
    fit_attenuation_map,
)


RICH_SURVEY_HEADER = (
    "pass_index",
    "x_cm",
    "y_cm",
    "sample_index",
    "device_time_ms",
    "rssi_dbm",
    "host_time_utc",
    "host_monotonic_ns",
    "packet_sequence",
    "ap_id",
    "z_cm",
    "yaw_deg",
    "pitch_deg",
    "roll_deg",
)
DETERMINISTIC_START_UTC = datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SimulationConfig:
    """Configuration for a four-metre controlled synthetic experiment."""

    scene: str = "one-rectangle"
    link_geometry: str = "crossing"
    seed: int = 0
    room_width_m: float = 4.0
    room_height_m: float = 4.0
    grid_resolution_m: float = 0.25
    receiver_spacing_m: float = 0.5
    receiver_height_m: float = 1.0
    pass_count: int = 3
    samples_per_location: int = 5
    sample_interval_ms: int = 100
    p0_dbm: float = -32.0
    path_loss_exponent: float = 2.0
    reference_distance_m: float = 1.0
    sample_noise_std_db: float = 0.35
    pass_drift_amplitude_db: float = 0.35
    rectangle_bounds_m: tuple[float, float, float, float] = (1.5, 2.5, 1.0, 3.0)
    rectangle_attenuation_db_per_m: float = 10.0
    bootstrap_count: int = 8
    attenuation_threshold_db_per_m: float = 2.0
    evidence_threshold: float = 0.625
    lambda_l1: float = 0.08
    lambda_tv: float = 0.12
    optimizer_max_iterations: int = 1000
    optimizer_relative_tolerance: float = 5e-5

    def __post_init__(self) -> None:
        if self.scene not in {"empty", "one-rectangle"}:
            raise ValueError("scene must be 'empty' or 'one-rectangle'.")
        if self.link_geometry not in {"single-ap", "crossing"}:
            raise ValueError("link_geometry must be 'single-ap' or 'crossing'.")
        if not 0 <= self.seed < 2**63:
            raise ValueError("seed must be in [0, 2**63).")
        positive = {
            "room_width_m": self.room_width_m,
            "room_height_m": self.room_height_m,
            "grid_resolution_m": self.grid_resolution_m,
            "receiver_spacing_m": self.receiver_spacing_m,
            "receiver_height_m": self.receiver_height_m,
            "reference_distance_m": self.reference_distance_m,
            "sample_noise_std_db": self.sample_noise_std_db,
            "rectangle_attenuation_db_per_m": self.rectangle_attenuation_db_per_m,
            "attenuation_threshold_db_per_m": self.attenuation_threshold_db_per_m,
            "optimizer_relative_tolerance": self.optimizer_relative_tolerance,
        }
        if any(not np.isfinite(value) or value <= 0 for value in positive.values()):
            raise ValueError("Simulation distances, noise, and thresholds must be positive.")
        if not np.isfinite([self.p0_dbm, self.path_loss_exponent]).all():
            raise ValueError("Path-loss parameters must be finite.")
        if self.path_loss_exponent <= 0 or self.pass_drift_amplitude_db < 0:
            raise ValueError("Path-loss exponent must be positive and drift nonnegative.")
        if self.pass_count < 3 or self.samples_per_location < 1:
            raise ValueError("Synthetic surveys require at least three passes and one sample.")
        if self.sample_interval_ms < 1 or self.bootstrap_count < 1:
            raise ValueError("Sampling interval and bootstrap count must be positive.")
        if self.optimizer_max_iterations < 1:
            raise ValueError("optimizer_max_iterations must be positive.")
        if min(self.lambda_l1, self.lambda_tv) < 0:
            raise ValueError("Regularization strengths cannot be negative.")
        if not 0 < self.evidence_threshold <= 1:
            raise ValueError("evidence_threshold must be in (0, 1].")
        for extent in (self.room_width_m, self.room_height_m):
            cell_count = extent / self.grid_resolution_m
            if not np.isclose(cell_count, round(cell_count)):
                raise ValueError("Room extents must be multiples of grid_resolution_m.")
        xmin, xmax, ymin, ymax = self.rectangle_bounds_m
        if not (0 <= xmin < xmax <= self.room_width_m):
            raise ValueError("Rectangle x bounds must lie inside the room.")
        if not (0 <= ymin < ymax <= self.room_height_m):
            raise ValueError("Rectangle y bounds must lie inside the room.")
        aligned = np.asarray(self.rectangle_bounds_m) / self.grid_resolution_m
        if not np.allclose(aligned, np.round(aligned)):
            raise ValueError("Rectangle bounds must align with grid cell edges.")


@dataclass(frozen=True)
class SyntheticDataset:
    config: SimulationConfig
    x_centers_m: np.ndarray
    y_centers_m: np.ndarray
    true_attenuation_db_per_m: np.ndarray
    transmitter_ids: tuple[str, ...]
    transmitter_positions_m: np.ndarray
    receiver_positions_m: np.ndarray
    link_transmitter_index: np.ndarray
    link_receiver_index: np.ndarray
    ray_matrix_m: np.ndarray
    path_loss_dbm: np.ndarray
    true_excess_attenuation_db: np.ndarray
    pass_drift_db: np.ndarray
    rssi_samples_dbm: np.ndarray

    @property
    def link_transmitter_positions_m(self) -> np.ndarray:
        return self.transmitter_positions_m[self.link_transmitter_index]

    @property
    def link_receiver_positions_m(self) -> np.ndarray:
        return self.receiver_positions_m[self.link_receiver_index]

    @property
    def link_transmitter_ids(self) -> np.ndarray:
        identifiers = np.asarray(self.transmitter_ids)
        return identifiers[self.link_transmitter_index]


@dataclass(frozen=True)
class ValidationResult:
    attenuation_result: AttenuationResult
    evidence_frequency: np.ndarray
    support: SupportMetrics
    component_labels: np.ndarray
    components: tuple[ComponentMetric, ...]
    status: str
    metrics: dict[str, Any]
    observed_excess_attenuation_db: np.ndarray
    observation_noise_std_db: np.ndarray
    pass_consistency: np.ndarray
    bootstrap_converged_fit_count: int
    bootstrap_fit_count: int


@dataclass(frozen=True)
class GeneratedArtifacts:
    survey_csv: Path
    metadata_json: Path
    calibration_csv: Path
    calibration_json: Path
    ground_truth_npz: Path
    validation_json: Path
    dataset: SyntheticDataset
    validation: ValidationResult


def _stable_ap_id(index: int) -> str:
    digest = hashlib.sha256(f"rf-mapping-synthetic-ap-{index}".encode()).hexdigest()
    return f"ap_{digest[:16]}"


def _grid_centers(extent_m: float, resolution_m: float) -> np.ndarray:
    count = int(round(extent_m / resolution_m))
    return (np.arange(count, dtype=float) + 0.5) * resolution_m


def _transmitter_positions(config: SimulationConfig) -> np.ndarray:
    height = config.receiver_height_m
    margin = 0.5
    positions = np.array(
        [
            [-margin, 0.5, height],
            [config.room_width_m - 0.5, -margin, height],
            [config.room_width_m + margin, config.room_height_m - 0.5, height],
            [0.5, config.room_height_m + margin, height],
        ],
        dtype=float,
    )
    return positions[:1] if config.link_geometry == "single-ap" else positions


def _receiver_positions(config: SimulationConfig) -> np.ndarray:
    x_count = int(math.floor(config.room_width_m / config.receiver_spacing_m))
    y_count = int(math.floor(config.room_height_m / config.receiver_spacing_m))
    x_values = (np.arange(x_count, dtype=float) + 0.5) * config.receiver_spacing_m
    y_values = (np.arange(y_count, dtype=float) + 0.5) * config.receiver_spacing_m
    grid_x, grid_y = np.meshgrid(x_values, y_values)
    positions = np.column_stack(
        (grid_x.ravel(), grid_y.ravel(), np.full(grid_x.size, config.receiver_height_m))
    )
    if config.scene == "one-rectangle":
        xmin, xmax, ymin, ymax = config.rectangle_bounds_m
        inside = (
            (positions[:, 0] >= xmin)
            & (positions[:, 0] < xmax)
            & (positions[:, 1] >= ymin)
            & (positions[:, 1] < ymax)
        )
        positions = positions[~inside]
    if positions.size == 0:
        raise ValueError("Receiver spacing and obstacle leave no receiver positions.")
    return positions


def simulate_survey(config: SimulationConfig | None = None) -> SyntheticDataset:
    """Generate deterministic scalar-RSSI samples and exact synthetic truth."""

    settings = config or SimulationConfig()
    x_centers = _grid_centers(settings.room_width_m, settings.grid_resolution_m)
    y_centers = _grid_centers(settings.room_height_m, settings.grid_resolution_m)
    grid_x, grid_y = np.meshgrid(x_centers, y_centers)
    attenuation = np.zeros(grid_x.shape, dtype=float)
    if settings.scene == "one-rectangle":
        xmin, xmax, ymin, ymax = settings.rectangle_bounds_m
        rectangle = (
            (grid_x >= xmin)
            & (grid_x < xmax)
            & (grid_y >= ymin)
            & (grid_y < ymax)
        )
        attenuation[rectangle] = settings.rectangle_attenuation_db_per_m

    transmitters = _transmitter_positions(settings)
    receivers = _receiver_positions(settings)
    transmitter_count = transmitters.shape[0]
    receiver_count = receivers.shape[0]
    link_transmitter_index = np.repeat(np.arange(transmitter_count), receiver_count)
    link_receiver_index = np.tile(np.arange(receiver_count), transmitter_count)
    link_transmitters = transmitters[link_transmitter_index]
    link_receivers = receivers[link_receiver_index]
    ray_matrix = build_ray_matrix(
        link_transmitters[:, :2],
        link_receivers[:, :2],
        x_centers,
        y_centers,
    )
    distances = np.linalg.norm(link_receivers - link_transmitters, axis=1)
    path_loss = settings.p0_dbm - 10.0 * settings.path_loss_exponent * np.log10(
        distances / settings.reference_distance_m
    )
    true_excess = ray_matrix @ attenuation.ravel()
    pass_drift = np.linspace(
        -settings.pass_drift_amplitude_db,
        settings.pass_drift_amplitude_db,
        settings.pass_count,
    )
    rng = np.random.default_rng(settings.seed)
    expected = (
        path_loss[np.newaxis, :, np.newaxis]
        - true_excess[np.newaxis, :, np.newaxis]
        + pass_drift[:, np.newaxis, np.newaxis]
    )
    noisy = expected + rng.normal(
        0.0,
        settings.sample_noise_std_db,
        (settings.pass_count, ray_matrix.shape[0], settings.samples_per_location),
    )
    samples = np.rint(noisy).astype(np.int16)
    transmitter_ids = tuple(_stable_ap_id(index) for index in range(transmitter_count))
    return SyntheticDataset(
        config=settings,
        x_centers_m=x_centers,
        y_centers_m=y_centers,
        true_attenuation_db_per_m=attenuation,
        transmitter_ids=transmitter_ids,
        transmitter_positions_m=transmitters,
        receiver_positions_m=receivers,
        link_transmitter_index=link_transmitter_index,
        link_receiver_index=link_receiver_index,
        ray_matrix_m=ray_matrix,
        path_loss_dbm=path_loss,
        true_excess_attenuation_db=true_excess,
        pass_drift_db=pass_drift,
        rssi_samples_dbm=samples,
    )


def _observation_statistics(
    dataset: SyntheticDataset,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    samples = dataset.rssi_samples_dbm.astype(float)
    per_pass_means = np.mean(samples, axis=2)
    mean_rssi = np.mean(per_pass_means, axis=0)
    observed_excess = dataset.path_loss_dbm - mean_rssi
    sample_count = dataset.config.samples_per_location
    within_variance = np.mean(np.var(samples, axis=2, ddof=0), axis=0) / sample_count
    between_variance = np.var(per_pass_means, axis=0, ddof=0)
    standard_error = np.sqrt(
        (within_variance + between_variance)
        / dataset.config.pass_count
    )
    quantization_std = 1.0 / math.sqrt(12.0)
    noise_floor = math.sqrt(
        dataset.config.sample_noise_std_db**2 / sample_count + quantization_std**2
    )
    observation_noise = np.maximum(standard_error, noise_floor)
    expected_pass_variation = math.sqrt(
        dataset.config.pass_drift_amplitude_db**2
        + dataset.config.sample_noise_std_db**2 / sample_count
    )
    pass_spread = np.std(per_pass_means, axis=0)
    pass_consistency = np.exp(
        -0.5 * (pass_spread / max(expected_pass_variation, 1e-12)) ** 2
    )
    return observed_excess, observation_noise, pass_consistency


def validate_synthetic_survey(
    dataset: SyntheticDataset,
    *,
    observability_config: ObservabilityConfig | None = None,
) -> ValidationResult:
    """Run MAP attenuation, bootstrap evidence, and the scientific shape gate."""

    observed_excess, observation_noise, pass_consistency = _observation_statistics(dataset)
    settings = dataset.config
    fit_options: dict[str, float | int] = {
        "lambda_l1": settings.lambda_l1,
        "lambda_tv": settings.lambda_tv,
        "cell_size_m": settings.grid_resolution_m,
        "max_iterations": settings.optimizer_max_iterations,
        "relative_tolerance": settings.optimizer_relative_tolerance,
    }
    attenuation_result = fit_attenuation_map(
        dataset.ray_matrix_m,
        observed_excess,
        observation_noise,
        dataset.true_attenuation_db_per_m.shape,
        **fit_options,
    )
    bootstrap = bootstrap_attenuation_evidence_with_diagnostics(
        dataset.ray_matrix_m,
        attenuation_result.predicted_excess_db,
        observation_noise,
        dataset.true_attenuation_db_per_m.shape,
        seed=settings.seed,
        bootstrap_count=settings.bootstrap_count,
        attenuation_threshold_db_per_m=settings.attenuation_threshold_db_per_m,
        fit_options=fit_options,
    )
    evidence = bootstrap.evidence_frequency
    support = calculate_support(
        dataset.ray_matrix_m,
        dataset.link_transmitter_positions_m[:, :2],
        dataset.link_receiver_positions_m[:, :2],
        dataset.link_transmitter_ids,
        observation_noise,
        dataset.x_centers_m,
        dataset.y_centers_m,
        link_pass_consistency=pass_consistency,
        link_pass_counts=np.full(dataset.ray_matrix_m.shape[0], settings.pass_count),
        config=observability_config,
    )
    inference_converged = (
        attenuation_result.converged
        and bootstrap.converged_fit_count == bootstrap.fit_count
    )
    observable_mask = support.observable_mask & inference_converged
    labels, components = extract_components(
        evidence,
        observable_mask,
        dataset.ray_matrix_m,
        dataset.link_transmitter_ids,
        dataset.x_centers_m,
        dataset.y_centers_m,
        evidence_threshold=settings.evidence_threshold,
        minimum_cells=2,
    )
    if not np.any(support.observable_mask):
        status = "insufficient_observability"
    elif not inference_converged:
        status = "optimizer_not_converged"
    elif components:
        status = "potential_attenuation_components"
    else:
        status = "no_supported_component"
    metrics = validation_metrics(
        dataset.true_attenuation_db_per_m > 0,
        labels > 0,
        dataset.true_attenuation_db_per_m,
        attenuation_result.attenuation_db_per_m,
        dataset.x_centers_m,
        dataset.y_centers_m,
    )
    return ValidationResult(
        attenuation_result=attenuation_result,
        evidence_frequency=evidence,
        support=support,
        component_labels=labels,
        components=tuple(components),
        status=status,
        metrics=metrics,
        observed_excess_attenuation_db=observed_excess,
        observation_noise_std_db=observation_noise,
        pass_consistency=pass_consistency,
        bootstrap_converged_fit_count=bootstrap.converged_fit_count,
        bootstrap_fit_count=bootstrap.fit_count,
    )


def root_mean_square_error(
    reference: np.ndarray,
    estimate: np.ndarray,
    mask: np.ndarray | None = None,
) -> float:
    expected = np.asarray(reference, dtype=float)
    actual = np.asarray(estimate, dtype=float)
    if expected.shape != actual.shape or expected.size == 0:
        raise ValueError("RMSE arrays must be non-empty and have equal shape.")
    selected = np.ones(expected.shape, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    if selected.shape != expected.shape or not np.any(selected):
        raise ValueError("RMSE mask must match the arrays and select at least one value.")
    differences = expected[selected] - actual[selected]
    if not np.isfinite(differences).all():
        raise ValueError("RMSE inputs must be finite.")
    return float(np.sqrt(np.mean(differences**2)))


def binary_overlap_metrics(
    reference_mask: np.ndarray,
    estimate_mask: np.ndarray,
) -> dict[str, float]:
    reference = np.asarray(reference_mask, dtype=bool)
    estimate = np.asarray(estimate_mask, dtype=bool)
    if reference.shape != estimate.shape or reference.size == 0:
        raise ValueError("Binary masks must be non-empty and have equal shape.")
    true_positive = int(np.count_nonzero(reference & estimate))
    false_positive = int(np.count_nonzero(~reference & estimate))
    union = int(np.count_nonzero(reference | estimate))
    predicted = int(np.count_nonzero(estimate))
    actual = int(np.count_nonzero(reference))
    negative = int(np.count_nonzero(~reference))
    return {
        "iou": true_positive / union if union else 1.0,
        "precision": true_positive / predicted if predicted else float(actual == 0),
        "recall": true_positive / actual if actual else float(predicted == 0),
        "false_positive_rate": false_positive / negative if negative else 0.0,
        "predicted_occupied_fraction": predicted / reference.size,
    }


def _boundary_mask(mask: np.ndarray) -> np.ndarray:
    values = np.asarray(mask, dtype=bool)
    padded = np.pad(values, 1, constant_values=False)
    interior = (
        padded[1:-1, 1:-1]
        & padded[:-2, 1:-1]
        & padded[2:, 1:-1]
        & padded[1:-1, :-2]
        & padded[1:-1, 2:]
    )
    return values & ~interior


def boundary_distance_metrics(
    reference_mask: np.ndarray,
    estimate_mask: np.ndarray,
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
) -> dict[str, float]:
    reference = np.asarray(reference_mask, dtype=bool)
    estimate = np.asarray(estimate_mask, dtype=bool)
    expected_shape = (len(y_centers_m), len(x_centers_m))
    if reference.shape != expected_shape or estimate.shape != expected_shape:
        raise ValueError("Boundary masks must match the supplied grid.")
    grid_x, grid_y = np.meshgrid(x_centers_m, y_centers_m)
    reference_boundary = _boundary_mask(reference)
    estimate_boundary = _boundary_mask(estimate)
    first = np.column_stack((grid_x[reference_boundary], grid_y[reference_boundary]))
    second = np.column_stack((grid_x[estimate_boundary], grid_y[estimate_boundary]))
    if first.size == 0 and second.size == 0:
        return {"symmetric_mean_m": 0.0, "hausdorff_m": 0.0}
    if first.size == 0 or second.size == 0:
        return {"symmetric_mean_m": math.inf, "hausdorff_m": math.inf}
    distances = np.linalg.norm(first[:, np.newaxis, :] - second[np.newaxis, :, :], axis=2)
    first_to_second = np.min(distances, axis=1)
    second_to_first = np.min(distances, axis=0)
    return {
        "symmetric_mean_m": float(
            0.5 * (np.mean(first_to_second) + np.mean(second_to_first))
        ),
        "hausdorff_m": float(max(np.max(first_to_second), np.max(second_to_first))),
    }


def _bounding_dimensions(
    mask: np.ndarray,
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
) -> tuple[float, float]:
    ys, xs = np.nonzero(mask)
    if xs.size == 0:
        return 0.0, 0.0
    if len(x_centers_m) < 2 or len(y_centers_m) < 2:
        raise ValueError("Bounding dimensions require at least two grid centers per axis.")
    resolution_x = float(np.diff(x_centers_m)[0])
    resolution_y = float(np.diff(y_centers_m)[0])
    return (
        (int(np.ptp(xs)) + 1) * resolution_x,
        (int(np.ptp(ys)) + 1) * resolution_y,
    )


def bounding_box_dimension_error(
    reference_mask: np.ndarray,
    estimate_mask: np.ndarray,
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
) -> dict[str, float]:
    reference = np.asarray(reference_mask, dtype=bool)
    estimate = np.asarray(estimate_mask, dtype=bool)
    expected_shape = (len(y_centers_m), len(x_centers_m))
    if reference.shape != expected_shape or estimate.shape != expected_shape:
        raise ValueError("Bounding-box masks must match the supplied grid.")
    reference_width, reference_height = _bounding_dimensions(
        reference, x_centers_m, y_centers_m
    )
    estimate_width, estimate_height = _bounding_dimensions(
        estimate, x_centers_m, y_centers_m
    )
    return {
        "reference_width_m": reference_width,
        "reference_height_m": reference_height,
        "estimated_width_m": estimate_width,
        "estimated_height_m": estimate_height,
        "absolute_width_error_m": abs(estimate_width - reference_width),
        "absolute_height_error_m": abs(estimate_height - reference_height),
    }


def validation_metrics(
    reference_mask: np.ndarray,
    estimate_mask: np.ndarray,
    reference_attenuation: np.ndarray,
    estimate_attenuation: np.ndarray,
    x_centers_m: np.ndarray,
    y_centers_m: np.ndarray,
) -> dict[str, Any]:
    return {
        "attenuation_rmse_db_per_m": root_mean_square_error(
            reference_attenuation, estimate_attenuation
        ),
        **binary_overlap_metrics(reference_mask, estimate_mask),
        "boundary": boundary_distance_metrics(
            reference_mask, estimate_mask, x_centers_m, y_centers_m
        ),
        "bounding_box": bounding_box_dimension_error(
            reference_mask, estimate_mask, x_centers_m, y_centers_m
        ),
    }


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _config_dictionary(config: SimulationConfig) -> dict[str, Any]:
    return asdict(config)


def _metadata(
    dataset: SyntheticDataset,
    run_uuid: str,
    survey_csv_sha256: str,
    calibration_sha256: str,
) -> dict[str, Any]:
    config = dataset.config
    sample_count = (
        config.pass_count
        * dataset.ray_matrix_m.shape[0]
        * config.samples_per_location
    )
    return {
        "schema_version": "2.0",
        "run_uuid": run_uuid,
        "created_utc": "2026-01-01T00:00:00.000Z",
        "units": {
            "position": "cm",
            "orientation": "deg",
            "rssi": "dBm",
            "device_time": "ms",
            "host_monotonic": "ns",
        },
        "run": {
            "environment_label": "deterministic_synthetic_room",
            "trial_label": f"{config.scene}_{config.link_geometry}",
            "notes": "No credentials, SSID, BSSID, or personal identifiers are present.",
            "seed": config.seed,
        },
        "data": {
            "csv_file": "survey_samples.csv",
            "csv_schema": "2.0",
            "csv_sha256": survey_csv_sha256,
            "received_sample_count": sample_count,
            "expected_sample_count_for_completed_points": sample_count,
            "packet_loss_count": 0,
            "csi_available": False,
            "noise_floor_available": False,
        },
        "pose": {
            "source": "synthetic_ground_truth",
            "coordinate_convention": "x right, y up, z vertical; metres converted to CSV centimetres",
            "position_standard_deviation_cm": [0.0, 0.0, 0.0],
            "orientation_standard_deviation_deg": [0.0, 0.0, 0.0],
        },
        "hardware": {
            "board_model": "synthetic_scalar_rssi_source",
            "chip_model": "not_applicable",
            "antenna_type": "synthetic_isotropic_model",
            "antenna_id": "simulated_antenna_0",
            "antenna_orientation": "fixed_yaw_pitch_roll_zero",
            "orientation_convention": "yaw=0 faces +x; pitch and roll use right-hand rule",
        },
        "channel": {
            "channel": 6,
            "bandwidth_mhz": 20,
            "phy_mode": "synthetic_802.11n_like_scalar_rssi",
            "csi_available": False,
        },
        "sampling": {
            "pass_count": config.pass_count,
            "samples_per_location": config.samples_per_location,
            "sample_interval_ms": config.sample_interval_ms,
            "sample_rate_hz": 1000.0 / config.sample_interval_ms,
            "dwell_time_s": config.samples_per_location * config.sample_interval_ms / 1000.0,
            "packet_loss_count": 0,
            "packet_success_fraction": 1.0,
            "noise_floor_available": False,
        },
        "calibration": {
            "file": "calibration.json",
            "version": "1.0",
            "sha256": calibration_sha256,
            "shared_model_for_ap_ids": list(dataset.transmitter_ids),
            "assumption": "all synthetic APs use identical known hardware and propagation parameters",
        },
        "transmitters": [
            {
                "ap_id": identifier,
                "identifier_kind": "privacy_preserving_synthetic_hash",
                "position_cm": {
                    "x": float(position[0] * 100.0),
                    "y": float(position[1] * 100.0),
                    "z": float(position[2] * 100.0),
                },
            }
            for identifier, position in zip(
                dataset.transmitter_ids, dataset.transmitter_positions_m
            )
        ],
    }


def _write_survey_csv(path: Path, dataset: SyntheticDataset) -> None:
    config = dataset.config
    packet_sequences = np.zeros(
        (config.pass_count, len(dataset.transmitter_ids)), dtype=int
    )
    row_index = 0
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, lineterminator="\n")
        writer.writerow(RICH_SURVEY_HEADER)
        for pass_index in range(config.pass_count):
            for link_index in range(dataset.ray_matrix_m.shape[0]):
                transmitter_index = int(dataset.link_transmitter_index[link_index])
                receiver = dataset.link_receiver_positions_m[link_index]
                for sample_index in range(config.samples_per_location):
                    elapsed_ms = row_index * config.sample_interval_ms
                    timestamp = DETERMINISTIC_START_UTC + timedelta(milliseconds=elapsed_ms)
                    writer.writerow(
                        (
                            pass_index + 1,
                            f"{receiver[0] * 100.0:.12g}",
                            f"{receiver[1] * 100.0:.12g}",
                            sample_index,
                            1000 + elapsed_ms,
                            int(dataset.rssi_samples_dbm[pass_index, link_index, sample_index]),
                            timestamp.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                            1_000_000_000 + elapsed_ms * 1_000_000,
                            int(packet_sequences[pass_index, transmitter_index]),
                            dataset.transmitter_ids[transmitter_index],
                            f"{receiver[2] * 100.0:.12g}",
                            0.0,
                            0.0,
                            0.0,
                        )
                    )
                    packet_sequences[pass_index, transmitter_index] += 1
                    row_index += 1


def _write_calibration_csv(path: Path, dataset: SyntheticDataset) -> None:
    config = dataset.config
    distances_m = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0)
    header = (
        "distance_m",
        "rssi_dbm",
        "pass_index",
        "ap_id",
        "board_model",
        "chip_model",
        "antenna_type",
        "antenna_id",
        "antenna_orientation",
        "channel",
        "bandwidth_mhz",
        "phy_mode",
        "receiver_height_cm",
        "transmitter_height_cm",
        "environment_label",
        "trial_label",
    )
    rng = np.random.default_rng(np.random.SeedSequence([config.seed, 0xCA11B4]))
    pass_drift = np.linspace(
        -config.pass_drift_amplitude_db,
        config.pass_drift_amplitude_db,
        config.pass_count,
    )
    with path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file, lineterminator="\n")
        writer.writerow(header)
        for pass_index, drift_db in enumerate(pass_drift, start=1):
            for distance_m in distances_m:
                mean_rssi = config.p0_dbm - 10.0 * config.path_loss_exponent * math.log10(
                    distance_m / config.reference_distance_m
                )
                for _ in range(config.samples_per_location):
                    rssi = mean_rssi + drift_db + rng.normal(0.0, config.sample_noise_std_db)
                    writer.writerow(
                        (
                            distance_m,
                            f"{rssi:.6f}",
                            pass_index,
                            dataset.transmitter_ids[0],
                            "synthetic_scalar_rssi_source",
                            "not_applicable",
                            "synthetic_isotropic_model",
                            "simulated_antenna_0",
                            "fixed_yaw_pitch_roll_zero",
                            6,
                            20,
                            "synthetic_802.11n_like_scalar_rssi",
                            int(round(config.receiver_height_m * 100)),
                            int(round(config.receiver_height_m * 100)),
                            "deterministic_synthetic_open_space",
                            "open_space_log_distance_calibration",
                        )
                    )


def _validation_report(
    dataset: SyntheticDataset,
    result: ValidationResult,
    hashes: dict[str, str],
    observability_config: ObservabilityConfig,
) -> dict[str, Any]:
    warnings = [
        "Bootstrap values are evidence frequencies, not posterior occupancy probabilities.",
        "Synthetic recovery does not establish performance in multipath or dynamic real rooms.",
        "IoU/precision/recall are 1.0 when truth and estimate are both empty; "
        "false_positive_rate reports the empty-scene error directly.",
    ]
    if result.status == "insufficient_observability":
        warnings.append("Shape and dimensions are suppressed because link observability failed.")
    return json_safe(
        {
            "schema_version": "1.0",
            "report_kind": "deterministic_synthetic_validation",
            "seed": dataset.config.seed,
            "scene": dataset.config.scene,
            "link_geometry": dataset.config.link_geometry,
            "software": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "platform": platform.platform(),
            },
            "input_sha256": hashes,
            "parameters": _config_dictionary(dataset.config),
            "optimizer": {
                "method": "projected_gradient_MAP_with_L1_and_smoothed_TV",
                "iterations": result.attenuation_result.iterations,
                "converged": result.attenuation_result.converged,
                "final_objective": result.attenuation_result.objective_history[-1],
                "residual_rmse_db": root_mean_square_error(
                    result.observed_excess_attenuation_db,
                    result.attenuation_result.predicted_excess_db,
                ),
                "bootstrap_converged_fit_count": result.bootstrap_converged_fit_count,
                "bootstrap_fit_count": result.bootstrap_fit_count,
            },
            "observability": {
                "status": result.status,
                "config": asdict(observability_config),
                "observable_cell_count": int(np.count_nonzero(result.support.observable_mask)),
                "total_cell_count": int(result.support.observable_mask.size),
                "failed_criteria_cell_counts": result.support.failed_criteria_counts,
            },
            "metrics": result.metrics,
            "components": [asdict(component) for component in result.components],
            "warnings": warnings,
        }
    )


def generate_synthetic_dataset(
    output_directory: str | Path,
    config: SimulationConfig | None = None,
    *,
    overwrite: bool = False,
    observability_config: ObservabilityConfig | None = None,
) -> GeneratedArtifacts:
    """Generate, validate, and write one complete deterministic fixture set."""

    settings = config or SimulationConfig()
    dataset = simulate_survey(settings)
    gate = observability_config or ObservabilityConfig()
    validation = validate_synthetic_survey(dataset, observability_config=gate)
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "survey_csv": output / "survey_samples.csv",
        "metadata_json": output / "survey_metadata.json",
        "calibration_csv": output / "calibration_samples.csv",
        "calibration_json": output / "calibration.json",
        "ground_truth_npz": output / "ground_truth.npz",
        "validation_json": output / "validation.json",
    }
    existing = [path for path in paths.values() if path.exists()]
    if existing and not overwrite:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(f"Refusing to overwrite existing synthetic artifacts: {names}")

    config_bytes = _canonical_json_bytes(_config_dictionary(settings))
    identity = hashlib.sha256(config_bytes).hexdigest()
    run_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"rf-mapping-run:{identity}"))
    _write_survey_csv(paths["survey_csv"], dataset)
    _write_calibration_csv(paths["calibration_csv"], dataset)
    calibration_result = fit_log_distance_calibration(
        load_calibration_csv(paths["calibration_csv"]),
        reference_distance_m=settings.reference_distance_m,
    )
    if not calibration_result.converged:
        raise RuntimeError("Synthetic calibration unexpectedly failed to converge.")
    save_calibration(calibration_result, paths["calibration_json"])
    calibration_document = json.loads(paths["calibration_json"].read_text(encoding="utf-8"))
    calibration_document["shared_model_for_ap_ids"] = list(dataset.transmitter_ids)
    calibration_document["shared_model_assumption"] = (
        "all synthetic APs use identical known hardware and propagation parameters"
    )
    paths["calibration_json"].write_bytes(_canonical_json_bytes(calibration_document))
    paths["metadata_json"].write_bytes(
        _canonical_json_bytes(
            _metadata(
                dataset,
                run_uuid,
                file_sha256(paths["survey_csv"]),
                file_sha256(paths["calibration_json"]),
            )
        )
    )
    rectangle_bounds = (
        np.asarray(settings.rectangle_bounds_m, dtype=float)
        if settings.scene == "one-rectangle"
        else np.empty(0, dtype=float)
    )
    write_deterministic_npz(
        paths["ground_truth_npz"],
        {
            "link_receiver_index": dataset.link_receiver_index,
            "link_transmitter_index": dataset.link_transmitter_index,
            "pass_drift_db": dataset.pass_drift_db,
            "path_loss_dbm": dataset.path_loss_dbm,
            "ray_matrix_m": dataset.ray_matrix_m,
            "receiver_positions_m": dataset.receiver_positions_m,
            "rectangle_bounds_m": rectangle_bounds,
            "rssi_samples_dbm": dataset.rssi_samples_dbm,
            "seed": np.asarray(settings.seed, dtype=np.int64),
            "transmitter_ids": np.asarray(dataset.transmitter_ids),
            "transmitter_positions_m": dataset.transmitter_positions_m,
            "true_attenuation_db_per_m": dataset.true_attenuation_db_per_m,
            "true_excess_attenuation_db": dataset.true_excess_attenuation_db,
            "x_centers_m": dataset.x_centers_m,
            "y_centers_m": dataset.y_centers_m,
        },
    )
    hashes = {
        name: file_sha256(paths[name])
        for name in (
            "survey_csv",
            "metadata_json",
            "calibration_csv",
            "calibration_json",
            "ground_truth_npz",
        )
    }
    report = _validation_report(dataset, validation, hashes, gate)
    paths["validation_json"].write_bytes(_canonical_json_bytes(report))
    return GeneratedArtifacts(
        survey_csv=paths["survey_csv"],
        metadata_json=paths["metadata_json"],
        calibration_csv=paths["calibration_csv"],
        calibration_json=paths["calibration_json"],
        ground_truth_npz=paths["ground_truth_npz"],
        validation_json=paths["validation_json"],
        dataset=dataset,
        validation=validation,
    )
