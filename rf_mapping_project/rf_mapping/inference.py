"""End-to-end offline probabilistic RF-assisted mapping."""

from __future__ import annotations

import json
import math
import platform
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import matplotlib
import numpy as np

from .artifacts import file_sha256, json_safe, write_deterministic_npz
from .calibration import CalibrationResult, load_calibration
from .data import (
    SurveyDataset,
    compute_inference_aggregates,
    load_survey_csv,
)
from .field_model import RFFieldGP, display_resolution_diagnostics
from .observability import (
    ObservabilityConfig,
    SupportMetrics,
    calculate_support,
    extract_components,
    point_clearance_mask,
)
from .occupancy import (
    AttenuationResult,
    BootstrapEvidenceResult,
    LIMITED_FREE_EVIDENCE_SCORE,
    UNKNOWN_EVIDENCE_SCORE,
    bootstrap_attenuation_evidence_with_diagnostics,
    build_ray_matrix,
    fit_attenuation_map,
    grid_centers,
    occupancy_from_evidence,
)
from .visualization import save_inference_figure


MAX_GRID_CELL_COUNT = 250_000
MAX_RAY_MATRIX_ELEMENT_COUNT = 10_000_000
MAX_GP_OBSERVATION_COUNT = 2_500


@dataclass(frozen=True)
class InferenceConfig:
    grid_resolution_m: float = 0.1
    kernel_length_scale_m: float = 0.5
    gp_signal_std_db: float = 6.0
    gp_noise_floor_db: float = 1.0
    lambda_l1: float = 0.2
    lambda_tv: float = 0.5
    tv_epsilon: float = 0.05
    optimizer_max_iterations: int = 600
    optimizer_relative_tolerance: float = 1e-5
    bootstrap_count: int = 20
    attenuation_threshold_db_per_m: float = 2.0
    evidence_threshold: float = 0.7
    minimum_component_cells: int = 2
    receiver_clearance_radius_m: float = 0.0
    seed: int = 0
    min_links: int = 4
    min_transmitters: int = 2
    min_angle_bins: int = 2
    angle_bin_count: int = 12
    max_receiver_distance_m: float = 1.0
    min_sensitivity: float = 0.5
    min_conditioning_score: float = 0.1
    min_pass_consistency: float = 0.5
    min_repeated_links: int = 3

    def __post_init__(self) -> None:
        positive = (
            self.grid_resolution_m,
            self.kernel_length_scale_m,
            self.gp_signal_std_db,
            self.gp_noise_floor_db,
            self.tv_epsilon,
            self.optimizer_relative_tolerance,
            self.attenuation_threshold_db_per_m,
            self.max_receiver_distance_m,
        )
        if not np.isfinite(positive).all() or any(value <= 0 for value in positive):
            raise ValueError("Inference scales, noise, and positive thresholds must be finite.")
        nonnegative = (
            self.lambda_l1,
            self.lambda_tv,
            self.min_sensitivity,
            self.receiver_clearance_radius_m,
        )
        if not np.isfinite(nonnegative).all() or min(nonnegative) < 0:
            raise ValueError("Regularization and sensitivity thresholds cannot be negative.")
        counts = (
            self.optimizer_max_iterations,
            self.bootstrap_count,
            self.minimum_component_cells,
            self.min_links,
            self.min_transmitters,
            self.min_angle_bins,
            self.angle_bin_count,
            self.min_repeated_links,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in counts
        ):
            raise ValueError("Inference count parameters must be positive integers.")
        if not 0 < self.evidence_threshold <= 1:
            raise ValueError("Evidence threshold must be in (0, 1].")
        bounded = (
            self.evidence_threshold,
            self.min_conditioning_score,
            self.min_pass_consistency,
        )
        if not np.isfinite(bounded).all():
            raise ValueError("Inference probability-like thresholds must be finite.")
        if not 0 <= self.min_conditioning_score <= 1 or not 0 <= self.min_pass_consistency <= 1:
            raise ValueError("Conditioning and pass-consistency thresholds must be in [0, 1].")
        if self.min_angle_bins > self.angle_bin_count:
            raise ValueError("Minimum angle bins cannot exceed the total angle-bin count.")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed < 2**63:
            raise ValueError("Seed must be in [0, 2**63).")

    def observability_config(self) -> ObservabilityConfig:
        return ObservabilityConfig(
            min_links=self.min_links,
            min_transmitters=self.min_transmitters,
            min_angle_bins=self.min_angle_bins,
            angle_bin_count=self.angle_bin_count,
            max_receiver_distance_m=self.max_receiver_distance_m,
            min_sensitivity=self.min_sensitivity,
            min_conditioning_score=self.min_conditioning_score,
            min_pass_consistency=self.min_pass_consistency,
            min_repeated_links=self.min_repeated_links,
        )


@dataclass(frozen=True)
class InferenceArtifacts:
    figure_path: Path
    arrays_path: Path
    report_path: Path
    status: str
    component_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _LinkObservation:
    ap_id: str | None
    receiver_xyz_m: tuple[float, float, float]
    rssi_dbm: float
    robust_median_rssi_dbm: float
    variance_db2: float
    within_pass_variance_db2: float
    between_pass_variance_db2: float
    pass_count: int
    pass_consistency: float
    outlier_count: int
    sample_count: int
    retained_sample_count: int
    pass_median_range_db: float
    pass_drift_db: float
    per_pass_statistics: tuple[dict[str, Any], ...]
    source_index: int


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _metadata_value_is_resolved(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    text = str(value).strip()
    return bool(text) and not text.startswith("REPLACE_WITH_")


def _transmitters_from_metadata(dataset: SurveyDataset) -> dict[str, np.ndarray]:
    if dataset.metadata is None:
        return {}
    document = dataset.metadata.document
    raw_items = document.get("transmitters")
    if raw_items is None and isinstance(document.get("transmitter"), dict):
        raw_items = [document["transmitter"]]
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list):
        return {}
    output: dict[str, np.ndarray] = {}
    for item in raw_items:
        if not isinstance(item, dict) or not isinstance(item.get("ap_id"), str):
            continue
        position = item.get("position_cm")
        if isinstance(position, dict):
            coordinates = [position.get(axis) for axis in ("x", "y", "z")]
        else:
            coordinates = [item.get(f"{axis}_cm") for axis in ("x", "y", "z")]
        parsed = [_finite_number(value) for value in coordinates]
        if any(value is None for value in parsed):
            continue
        output[item["ap_id"]] = np.asarray(parsed, dtype=float) / 100.0
    return output


def _metadata_gate_issues(datasets: Sequence[SurveyDataset]) -> list[str]:
    issues: list[str] = []
    for index, dataset in enumerate(datasets):
        prefix = f"dataset[{index}]"
        if dataset.schema_version != "2.0":
            issues.append(f"{prefix}: version 2 sample timing/pose fields are unavailable")
        if dataset.metadata is None:
            issues.append(f"{prefix}: survey metadata is unavailable")
            continue
        document = dataset.metadata.document
        pose = document.get("pose") if isinstance(document.get("pose"), dict) else {}
        hardware = (
            document.get("hardware") if isinstance(document.get("hardware"), dict) else {}
        )
        channel = document.get("channel") if isinstance(document.get("channel"), dict) else {}
        if not pose.get("source"):
            issues.append(f"{prefix}: pose.source is missing")
        uncertainty_keys = {
            "position_standard_deviation_cm",
            "standard_deviation_cm",
            "covariance_cm2",
            "covariance",
        }
        if not any(key in pose for key in uncertainty_keys):
            issues.append(f"{prefix}: pose uncertainty/covariance is missing")
        for field in (
            "board_model",
            "chip_model",
            "antenna_type",
            "antenna_id",
            "antenna_orientation",
        ):
            if not _metadata_value_is_resolved(hardware.get(field)):
                issues.append(f"{prefix}: hardware.{field} is missing or unresolved")
        for alternatives in (
            ("channel", "channel_number"),
            ("bandwidth_mhz",),
            ("phy_mode",),
        ):
            if not any(
                _metadata_value_is_resolved(channel.get(field))
                for field in alternatives
            ):
                issues.append(
                    f"{prefix}: channel.{alternatives[0]} is missing or unresolved"
                )
        if not _transmitters_from_metadata(dataset):
            issues.append(f"{prefix}: no complete transmitter position is available")
        if any(
            sample.z_cm is None
            or sample.yaw_deg is None
            or sample.pitch_deg is None
            or sample.roll_deg is None
            for sample in dataset.samples
        ):
            issues.append(f"{prefix}: receiver height/orientation is incomplete")
        orientations = {
            (sample.yaw_deg, sample.pitch_deg, sample.roll_deg)
            for sample in dataset.samples
            if sample.yaw_deg is not None
        }
        if len(orientations) > 1:
            issues.append(
                f"{prefix}: receiver antenna orientation changed within the run"
            )
        heights = {sample.z_cm for sample in dataset.samples if sample.z_cm is not None}
        if len(heights) > 1:
            issues.append(f"{prefix}: receiver height changed within the run")
    return issues


def _observations_from_datasets(
    datasets: Sequence[SurveyDataset],
) -> tuple[list[_LinkObservation], dict[str, np.ndarray]]:
    observations: list[_LinkObservation] = []
    all_transmitters: dict[str, np.ndarray] = {}
    for source_index, dataset in enumerate(datasets):
        transmitters = _transmitters_from_metadata(dataset)
        for identifier, position in transmitters.items():
            if identifier in all_transmitters and not np.allclose(
                all_transmitters[identifier], position
            ):
                raise ValueError(
                    f"Transmitter {identifier!r} has contradictory positions across metadata."
                )
            all_transmitters[identifier] = position
        aggregates = compute_inference_aggregates(dataset)
        for aggregate in aggregates.values():
            ap_id = aggregate.ap_id
            if ap_id is None and len(transmitters) == 1:
                ap_id = next(iter(transmitters))
            receiver_z_cm = aggregate.z_cm
            if receiver_z_cm is None and dataset.metadata is not None:
                pose = dataset.metadata.document.get("pose", {})
                if isinstance(pose, dict):
                    receiver_z_cm = _finite_number(pose.get("receiver_z_cm"))
            receiver_z_m = 0.0 if receiver_z_cm is None else receiver_z_cm / 100.0
            ratio = aggregate.between_to_within_standard_deviation_ratio
            consistency = (
                0.0
                if ratio is None or not math.isfinite(ratio)
                else 1.0 / (1.0 + ratio)
            )
            observations.append(
                _LinkObservation(
                    ap_id=ap_id,
                    receiver_xyz_m=(
                        aggregate.x_cm / 100.0,
                        aggregate.y_cm / 100.0,
                        receiver_z_m,
                    ),
                    rssi_dbm=aggregate.robust_central_rssi_dbm,
                    robust_median_rssi_dbm=aggregate.robust_median_rssi_dbm,
                    variance_db2=max(aggregate.central_estimate_variance_db2, 0.0),
                    within_pass_variance_db2=aggregate.within_pass_variance_db2,
                    between_pass_variance_db2=aggregate.between_pass_variance_db2,
                    pass_count=aggregate.pass_count,
                    pass_consistency=consistency,
                    outlier_count=aggregate.outlier_count,
                    sample_count=aggregate.sample_count,
                    retained_sample_count=aggregate.retained_sample_count,
                    pass_median_range_db=aggregate.pass_median_range_db,
                    pass_drift_db=aggregate.pass_drift_db,
                    per_pass_statistics=tuple(
                        {
                            "pass_index": summary.pass_index,
                            "raw": asdict(summary.raw),
                            "robust": asdict(summary.robust),
                            "outlier_count": summary.outlier_count,
                        }
                        for summary in aggregate.per_pass
                    ),
                    source_index=source_index,
                )
            )
    if not observations:
        raise ValueError("No valid location aggregates were available for inference.")
    return observations, all_transmitters


def _calibration_mapping(
    calibration_paths: Sequence[str | Path],
    ap_ids: set[str],
    allow_shared_calibration: bool,
) -> tuple[dict[str, CalibrationResult], list[str], list[dict[str, Any]]]:
    results = [load_calibration(path) for path in calibration_paths]
    mapping: dict[str, CalibrationResult] = {}
    unassigned: list[CalibrationResult] = []
    documents: list[dict[str, Any]] = []
    calibration_warnings: list[str] = []
    for path, result in zip(calibration_paths, results):
        input_path = Path(path)
        documents.append(
            {
                "path": str(input_path),
                "sha256": file_sha256(input_path),
                "artifact": result.to_document(),
            }
        )
        if not result.converged:
            calibration_warnings.append(
                f"Calibration {input_path} did not meet its convergence rule and "
                "was not used for obstacle inference."
            )
            continue
        identifier = result.metadata.get("ap_id")
        if identifier:
            if identifier in mapping:
                raise ValueError(f"More than one calibration was supplied for AP {identifier!r}.")
            mapping[identifier] = result
        else:
            unassigned.append(result)
    missing = ap_ids - set(mapping)
    usable_results = [result for result in results if result.converged]
    if len(ap_ids) == 1 and len(usable_results) == 1 and len(unassigned) == 1:
        mapping[next(iter(ap_ids))] = usable_results[0]
        missing.clear()
    elif missing and allow_shared_calibration and len(usable_results) == 1:
        for identifier in missing:
            mapping[identifier] = usable_results[0]
        calibration_warnings.append(
            "One explicitly shared calibration model was applied to multiple APs; "
            "real AP transmit powers should be calibrated separately."
        )
        missing.clear()
    if unassigned and len(results) > 1:
        calibration_warnings.append(
            "Calibration artifacts without ap_id could not be assigned in a multi-AP run."
        )
    if missing:
        calibration_warnings.append(
            "Missing calibration for AP identifiers: " + ", ".join(sorted(missing))
        )
    for document, result in zip(documents, results):
        document["ap_ids_applied"] = sorted(
            identifier for identifier, assigned in mapping.items() if assigned is result
        )
    return mapping, calibration_warnings, documents


def _calibration_metadata_issues(
    datasets: Sequence[SurveyDataset],
    calibrations: dict[str, CalibrationResult],
    calibration_documents: Sequence[dict[str, Any]],
) -> list[str]:
    issues: list[str] = []
    provenance_by_ap = {
        ap_id: (document["sha256"], document["artifact"]["schema_version"])
        for document in calibration_documents
        for ap_id in document["ap_ids_applied"]
    }
    comparisons = {
        "board_model": ("hardware", "board_model"),
        "chip_model": ("hardware", "chip_model"),
        "antenna_type": ("hardware", "antenna_type"),
        "antenna_id": ("hardware", "antenna_id"),
        "antenna_orientation": ("hardware", "antenna_orientation"),
        "channel": ("channel", "channel"),
        "bandwidth_mhz": ("channel", "bandwidth_mhz"),
        "phy_mode": ("channel", "phy_mode"),
    }
    for dataset_index, dataset in enumerate(datasets):
        if dataset.metadata is None:
            continue
        document = dataset.metadata.document
        transmitters = _transmitters_from_metadata(dataset)
        for ap_id in transmitters:
            calibration = calibrations.get(ap_id)
            if calibration is None:
                continue
            for calibration_key, (section_name, survey_key) in comparisons.items():
                expected = calibration.metadata.get(calibration_key)
                section = document.get(section_name, {})
                if not _metadata_value_is_resolved(expected):
                    issues.append(
                        f"dataset[{dataset_index}]: calibration metadata "
                        f"{calibration_key} is missing or unresolved for AP {ap_id}"
                    )
                    continue
                if not isinstance(section, dict):
                    continue
                actual = section.get(survey_key)
                if actual is None and survey_key == "channel":
                    actual = section.get("channel_number")
                if not _metadata_value_is_resolved(actual):
                    issues.append(
                        f"dataset[{dataset_index}]: calibration {calibration_key} "
                        f"has no resolved survey metadata for AP {ap_id}"
                    )
                    continue
                if calibration_key in {"channel", "bandwidth_mhz"}:
                    values_match = math.isclose(
                        float(actual), float(expected), rel_tol=0.0, abs_tol=1e-9
                    )
                else:
                    values_match = str(actual) == str(expected)
                if not values_match:
                    issues.append(
                        f"dataset[{dataset_index}]: calibration {calibration_key} "
                        f"does not match survey metadata for AP {ap_id}"
                    )
            recorded_calibration = document.get("calibration", {})
            provenance = provenance_by_ap.get(ap_id)
            if isinstance(recorded_calibration, dict) and provenance is not None:
                recorded_hash = recorded_calibration.get("sha256")
                if recorded_hash is not None and recorded_hash != provenance[0]:
                    issues.append(
                        f"dataset[{dataset_index}]: recorded calibration hash does "
                        f"not match the supplied calibration for AP {ap_id}"
                    )
                recorded_version = recorded_calibration.get("version")
                if recorded_version is not None and str(recorded_version) != provenance[1]:
                    issues.append(
                        f"dataset[{dataset_index}]: recorded calibration version does "
                        f"not match the supplied calibration for AP {ap_id}"
                    )
            expected_transmitter_height = _finite_number(
                calibration.metadata.get("transmitter_height_cm")
            )
            if expected_transmitter_height is None:
                issues.append(
                    f"dataset[{dataset_index}]: calibration transmitter height "
                    f"is missing for AP {ap_id}"
                )
            actual_transmitter_height = transmitters[ap_id][2] * 100.0
            if expected_transmitter_height is not None and not math.isclose(
                expected_transmitter_height,
                actual_transmitter_height,
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                issues.append(
                    f"dataset[{dataset_index}]: calibration transmitter height "
                    f"does not match survey metadata for AP {ap_id}"
                )
            expected_receiver_height = _finite_number(
                calibration.metadata.get("receiver_height_cm")
            )
            if expected_receiver_height is None:
                issues.append(
                    f"dataset[{dataset_index}]: calibration receiver height is "
                    f"missing for AP {ap_id}"
                )
            observed_heights = {
                sample.z_cm for sample in dataset.samples if sample.ap_id == ap_id
            }
            if expected_receiver_height is not None and any(
                height is None
                or not math.isclose(
                    expected_receiver_height,
                    height,
                    rel_tol=0.0,
                    abs_tol=1e-6,
                )
                for height in observed_heights
            ):
                issues.append(
                    f"dataset[{dataset_index}]: calibration receiver height "
                    f"does not match survey samples for AP {ap_id}"
                )
            if calibration.metadata.get("antenna_orientation") == "fixed_yaw_pitch_roll_zero":
                if any(
                    not np.allclose(
                        (sample.yaw_deg, sample.pitch_deg, sample.roll_deg),
                        (0.0, 0.0, 0.0),
                    )
                    for sample in dataset.samples
                    if sample.ap_id == ap_id
                ):
                    issues.append(
                        f"dataset[{dataset_index}]: calibration antenna orientation "
                        f"does not match survey samples for AP {ap_id}"
                    )
    return issues


def _grid_for_geometry(
    observations: Sequence[_LinkObservation],
    transmitter_positions: dict[str, np.ndarray],
    resolution_m: float,
) -> tuple[np.ndarray, np.ndarray]:
    receiver_xy = np.asarray([item.receiver_xyz_m[:2] for item in observations])
    points = [receiver_xy]
    if transmitter_positions:
        points.append(np.asarray([position[:2] for position in transmitter_positions.values()]))
    all_points = np.vstack(points)
    minima = np.floor(np.min(all_points, axis=0) / resolution_m) * resolution_m
    maxima = np.ceil(np.max(all_points, axis=0) / resolution_m) * resolution_m
    for axis in range(2):
        if np.isclose(minima[axis], maxima[axis]):
            minima[axis] -= resolution_m
            maxima[axis] += resolution_m
    axis_counts = [
        int(round((maxima[axis] - minima[axis]) / resolution_m)) + 1
        for axis in range(2)
    ]
    cell_count = axis_counts[0] * axis_counts[1]
    if cell_count > MAX_GRID_CELL_COUNT:
        raise ValueError(
            f"The requested analysis grid has {cell_count} cells; the prototype "
            f"limit is {MAX_GRID_CELL_COUNT}. Increase --grid-resolution-cm or "
            "reduce the coordinate extent."
        )
    x_centers = grid_centers(float(minima[0]), float(maxima[0]), resolution_m)
    y_centers = grid_centers(float(minima[1]), float(maxima[1]), resolution_m)
    return x_centers, y_centers


def _empty_support(shape: tuple[int, int]) -> SupportMetrics:
    zeros = np.zeros(shape, dtype=float)
    zero_counts = np.zeros(shape, dtype=int)
    return SupportMetrics(
        link_count=zero_counts.copy(),
        transmitter_count=zero_counts.copy(),
        angle_bin_count=zero_counts.copy(),
        distance_to_receiver_m=np.full(shape, np.inf),
        sensitivity=zeros.copy(),
        conditioning_score=zeros.copy(),
        pass_consistency=zeros.copy(),
        repeated_link_count=zero_counts.copy(),
        observable_mask=np.zeros(shape, dtype=bool),
        failed_criteria_counts={"link_geometry": int(np.prod(shape))},
    )


def _fit_options(config: InferenceConfig, scale: float = 1.0) -> dict[str, float | int]:
    return {
        "lambda_l1": config.lambda_l1 * scale,
        "lambda_tv": config.lambda_tv * scale,
        "tv_epsilon": config.tv_epsilon,
        "cell_size_m": config.grid_resolution_m,
        "max_iterations": config.optimizer_max_iterations,
        "relative_tolerance": config.optimizer_relative_tolerance,
    }


def _regularization_sensitivity(
    matrix: np.ndarray,
    excess: np.ndarray,
    noise: np.ndarray,
    shape: tuple[int, int],
    config: InferenceConfig,
    base: AttenuationResult,
) -> list[dict[str, Any]]:
    baseline_mask = base.attenuation_db_per_m >= config.attenuation_threshold_db_per_m
    output: list[dict[str, Any]] = []
    for scale in (0.5, 1.0, 2.0):
        result = base if scale == 1.0 else fit_attenuation_map(
            matrix, excess, noise, shape, **_fit_options(config, scale)
        )
        mask = result.attenuation_db_per_m >= config.attenuation_threshold_db_per_m
        union = np.count_nonzero(mask | baseline_mask)
        intersection = np.count_nonzero(mask & baseline_mask)
        output.append(
            {
                "joint_regularization_scale": scale,
                "attenuation_mass_db_m": float(
                    np.sum(result.attenuation_db_per_m) * config.grid_resolution_m**2
                ),
                "thresholded_cell_count": int(np.count_nonzero(mask)),
                "jaccard_against_selected": intersection / union if union else 1.0,
                "converged": result.converged,
                "iterations": result.iterations,
            }
        )
    return output


def run_offline_inference(
    raw_csv_paths: Sequence[str | Path],
    *,
    metadata_paths: Sequence[str | Path] = (),
    calibration_paths: Sequence[str | Path] = (),
    output_directory: str | Path = "inference_output",
    field_ap_id: str | None = None,
    config: InferenceConfig | None = None,
    allow_shared_calibration: bool = False,
    overwrite: bool = False,
    show: bool = False,
) -> InferenceArtifacts:
    """Create figure, deterministic arrays, and an auditable inference report."""

    settings = config or InferenceConfig()
    if not raw_csv_paths:
        raise ValueError("At least one survey CSV is required.")
    if metadata_paths and len(metadata_paths) != len(raw_csv_paths):
        raise ValueError("Supply either no metadata or one --metadata path per survey CSV.")
    paired_metadata: list[str | Path | None] = (
        list(metadata_paths) if metadata_paths else [None] * len(raw_csv_paths)
    )
    captured_warnings: list[str] = []
    datasets: list[SurveyDataset] = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        for raw_path, metadata_path in zip(raw_csv_paths, paired_metadata):
            datasets.append(load_survey_csv(raw_path, metadata_path))
        captured_warnings.extend(str(item.message) for item in caught)
    captured_warnings.extend(
        (
            "Only discrete receiver poses are plotted; no continuous traversed path "
            "is inferred from manual point order.",
            "Posterior standard deviation is conditional on fixed GP, calibration, "
            "and pose parameters; calibration-parameter and pose uncertainty are not "
            "propagated into this prototype posterior.",
        )
    )

    observations, transmitter_positions = _observations_from_datasets(datasets)
    known_ap_ids = {item.ap_id for item in observations if item.ap_id is not None}
    calibrations, calibration_warnings, calibration_documents = _calibration_mapping(
        calibration_paths, known_ap_ids, allow_shared_calibration
    )
    captured_warnings.extend(calibration_warnings)
    x_centers, y_centers = _grid_for_geometry(
        observations, transmitter_positions, settings.grid_resolution_m
    )
    shape = (len(y_centers), len(x_centers))
    grid_x, grid_y = np.meshgrid(x_centers, y_centers)

    available_field_ids = sorted(known_ap_ids)
    if field_ap_id is None:
        selected_ap_id: str | None = available_field_ids[0] if available_field_ids else None
    else:
        if field_ap_id not in known_ap_ids:
            raise ValueError(
                f"Requested field AP {field_ap_id!r} is absent; available IDs: "
                f"{available_field_ids or ['unidentified']}."
            )
        selected_ap_id = field_ap_id
    field_observations = [item for item in observations if item.ap_id == selected_ap_id]
    if not field_observations:
        field_observations = observations
    if len(field_observations) > MAX_GP_OBSERVATION_COUNT:
        raise ValueError(
            f"The selected field has {len(field_observations)} location observations; "
            f"the small-data GP limit is {MAX_GP_OBSERVATION_COUNT}. Aggregate "
            "repeat poses or analyze a bounded trial."
        )
    field_positions = np.asarray([item.receiver_xyz_m for item in field_observations])
    field_rssi = np.asarray([item.rssi_dbm for item in field_observations])
    field_variance = np.asarray([item.variance_db2 for item in field_observations])
    query_z = float(np.median(field_positions[:, 2]))
    query_positions = np.column_stack(
        (grid_x.ravel(), grid_y.ravel(), np.full(grid_x.size, query_z))
    )
    calibrated_field = (
        selected_ap_id is not None
        and selected_ap_id in calibrations
        and selected_ap_id in transmitter_positions
    )
    if calibrated_field:
        field_calibration = calibrations[selected_ap_id]
        gp = RFFieldGP(
            ap_position_m=transmitter_positions[selected_ap_id],
            p0_dbm=field_calibration.p0_dbm,
            path_loss_exponent=field_calibration.path_loss_exponent,
            reference_distance_m=field_calibration.reference_distance_m,
            minimum_distance_m=field_calibration.minimum_distance_m,
            length_scale_m=settings.kernel_length_scale_m,
            signal_std_db=settings.gp_signal_std_db,
            noise_floor_db=math.hypot(
                settings.gp_noise_floor_db, field_calibration.residual_sigma_db
            ),
        )
    else:
        captured_warnings.append(
            "No matched calibration plus AP position was available for the field panel; "
            "using an exploratory constant-mean GP. Obstacle inference is disabled."
        )
        gp = RFFieldGP(
            ap_position_m=None,
            p0_dbm=float(np.median(field_rssi)),
            path_loss_exponent=None,
            length_scale_m=settings.kernel_length_scale_m,
            signal_std_db=settings.gp_signal_std_db,
            noise_floor_db=settings.gp_noise_floor_db,
        )
    gp.fit(field_positions, field_rssi, field_variance)
    posterior = gp.predict(query_positions)
    posterior_mean = posterior.mean_dbm.reshape(shape)
    posterior_std = posterior.standard_deviation_db.reshape(shape)
    gp_density = posterior.support.effective_density.reshape(shape)
    extrapolation = posterior.support.extrapolation_mask.reshape(shape)
    if calibrated_field:
        query_distances = np.linalg.norm(
            query_positions - transmitter_positions[str(selected_ap_id)], axis=1
        ).reshape(shape)
        outside_calibration_range = (
            (query_distances < field_calibration.minimum_distance_m)
            | (query_distances > field_calibration.maximum_distance_m)
        )
        extrapolation |= outside_calibration_range
        if np.any(outside_calibration_range):
            captured_warnings.append(
                "The hatched field includes locations outside the path-loss "
                "calibration distance range."
            )
    resolution_diagnostics = display_resolution_diagnostics(
        field_positions,
        grid_resolution_m=settings.grid_resolution_m,
        length_scale_m=settings.kernel_length_scale_m,
    )
    captured_warnings.extend(resolution_diagnostics.warnings)
    lolo = gp.leave_one_location_out()

    metadata_issues = _metadata_gate_issues(datasets)
    metadata_issues.extend(
        _calibration_metadata_issues(
            datasets, calibrations, calibration_documents
        )
    )
    captured_warnings.extend(
        f"Obstacle inference gate: {issue}" for issue in metadata_issues
    )
    calibrated_links = [
        item
        for item in observations
        if item.ap_id is not None
        and item.ap_id in calibrations
        and item.ap_id in transmitter_positions
    ]
    complete_calibration = len(calibrated_links) == len(observations)
    ray_matrix = np.zeros((0, int(np.prod(shape))), dtype=float)
    ray_transmitters = np.empty((0, 2), dtype=float)
    ray_receivers = np.empty((0, 2), dtype=float)
    ray_ids: list[str] = []
    excess = np.empty(0, dtype=float)
    ray_noise = np.empty(0, dtype=float)
    attenuation = np.zeros(shape, dtype=float)
    evidence = np.zeros(shape, dtype=float)
    support = _empty_support(shape)
    attenuation_result: AttenuationResult | None = None
    bootstrap_result: BootstrapEvidenceResult | None = None
    sensitivity_runs: list[dict[str, Any]] = []
    ray_coverage_ok = True
    if complete_calibration and calibrated_links:
        ray_element_count = len(calibrated_links) * int(np.prod(shape))
        if ray_element_count > MAX_RAY_MATRIX_ELEMENT_COUNT:
            raise ValueError(
                f"The dense ray model would contain {ray_element_count} elements; "
                f"the prototype limit is {MAX_RAY_MATRIX_ELEMENT_COUNT}. Increase "
                "--grid-resolution-cm or analyze a smaller trial."
            )
        ray_transmitters = np.asarray(
            [transmitter_positions[item.ap_id][:2] for item in calibrated_links]
        )
        ray_receivers = np.asarray([item.receiver_xyz_m[:2] for item in calibrated_links])
        ray_ids = [str(item.ap_id) for item in calibrated_links]
        ray_matrix = build_ray_matrix(
            ray_transmitters, ray_receivers, x_centers, y_centers
        )
        nonzero_links = np.linalg.norm(ray_receivers - ray_transmitters, axis=1) > 1e-9
        if not np.all(nonzero_links):
            captured_warnings.append(
                f"Dropped {np.count_nonzero(~nonzero_links)} zero-length projected RF links."
            )
            calibrated_links = [
                item for item, keep in zip(calibrated_links, nonzero_links) if keep
            ]
            ray_transmitters = ray_transmitters[nonzero_links]
            ray_receivers = ray_receivers[nonzero_links]
            ray_matrix = ray_matrix[nonzero_links]
            ray_ids = [identifier for identifier, keep in zip(ray_ids, nonzero_links) if keep]
        if not calibrated_links:
            raise ValueError(
                "All calibrated transmitter-receiver links have zero projected 2D "
                "length; collect spatially separated measurements."
            )
        projected_lengths = np.linalg.norm(ray_receivers - ray_transmitters, axis=1)
        traced_lengths = np.sum(ray_matrix, axis=1)
        ray_coverage_ok = bool(
            np.allclose(traced_lengths, projected_lengths, rtol=1e-8, atol=1e-10)
        )
        if not ray_coverage_ok:
            captured_warnings.append(
                "One or more RF links are not fully covered by the analysis grid; "
                "component claims were suppressed."
            )
        predicted_path_loss: list[float] = []
        noise_values: list[float] = []
        for item in calibrated_links:
            calibration = calibrations[str(item.ap_id)]
            distance = float(
                np.linalg.norm(
                    np.asarray(item.receiver_xyz_m) - transmitter_positions[str(item.ap_id)]
                )
            )
            predicted_path_loss.append(float(calibration.predict_rssi_dbm(distance)))
            noise_values.append(
                math.sqrt(
                    item.variance_db2
                    + calibration.residual_sigma_db**2
                    + calibration.between_pass_drift_sigma_db**2
                )
            )
            if not calibration.minimum_distance_m <= distance <= calibration.maximum_distance_m:
                issue = (
                    f"link for AP {item.ap_id} at {distance:.3f} m is outside its "
                    "calibration fitting range"
                )
                metadata_issues.append(issue)
                captured_warnings.append(issue + "; component claims were suppressed.")
        excess = np.asarray(predicted_path_loss) - np.asarray(
            [item.rssi_dbm for item in calibrated_links]
        )
        ray_noise = np.maximum(np.asarray(noise_values), 0.1)
        attenuation_result = fit_attenuation_map(
            ray_matrix, excess, ray_noise, shape, **_fit_options(settings)
        )
        attenuation = attenuation_result.attenuation_db_per_m
        bootstrap_result = bootstrap_attenuation_evidence_with_diagnostics(
            ray_matrix,
            attenuation_result.predicted_excess_db,
            ray_noise,
            shape,
            seed=settings.seed,
            bootstrap_count=settings.bootstrap_count,
            attenuation_threshold_db_per_m=settings.attenuation_threshold_db_per_m,
            fit_options=_fit_options(settings),
        )
        evidence = bootstrap_result.evidence_frequency
        support = calculate_support(
            ray_matrix,
            ray_transmitters,
            ray_receivers,
            ray_ids,
            ray_noise,
            x_centers,
            y_centers,
            link_pass_consistency=np.asarray(
                [item.pass_consistency for item in calibrated_links]
            ),
            link_pass_counts=np.asarray([item.pass_count for item in calibrated_links]),
            config=settings.observability_config(),
        )
        sensitivity_runs = _regularization_sensitivity(
            ray_matrix, excess, ray_noise, shape, settings, attenuation_result
        )

    observable = support.observable_mask.copy()
    convergence_ok = (
        attenuation_result is not None
        and attenuation_result.converged
        and bootstrap_result is not None
        and bootstrap_result.converged_fit_count == bootstrap_result.fit_count
        and ray_coverage_ok
    )
    if metadata_issues or not complete_calibration or not convergence_ok:
        observable[:] = False
    if attenuation_result is not None and not convergence_ok:
        captured_warnings.append(
            "MAP or bootstrap refits did not all meet the convergence rule; "
            "component claims were suppressed."
        )
    pose_complete = not any(
        "pose" in issue or "receiver height/orientation" in issue
        for issue in metadata_issues
    )
    receiver_free = (
        point_clearance_mask(
            np.asarray([item.receiver_xyz_m[:2] for item in observations]),
            x_centers,
            y_centers,
            settings.receiver_clearance_radius_m,
        )
        if pose_complete
        else np.zeros(shape, dtype=bool)
    )
    ap_free = (
        point_clearance_mask(
            np.asarray([position[:2] for position in transmitter_positions.values()]),
            x_centers,
            y_centers,
            0.0,
        )
        if pose_complete and transmitter_positions
        else np.zeros(shape, dtype=bool)
    )
    occupancy_score, occupancy_state = occupancy_from_evidence(
        evidence,
        observable,
        receiver_free,
        ap_free,
        occupied_activation=settings.evidence_threshold,
    )
    component_evidence = np.where(
        attenuation >= settings.attenuation_threshold_db_per_m, evidence, 0.0
    )
    labels, components = extract_components(
        component_evidence,
        observable,
        ray_matrix,
        ray_ids,
        x_centers,
        y_centers,
        evidence_threshold=settings.evidence_threshold,
        minimum_cells=settings.minimum_component_cells,
    ) if ray_matrix.shape[0] else (np.zeros(shape, dtype=int), [])

    if not calibration_paths:
        status = "uncalibrated_inference_disabled"
    elif not complete_calibration or not transmitter_positions:
        status = "missing_link_geometry"
    elif not convergence_ok or not np.any(observable):
        status = "insufficient_observability"
    elif components:
        status = "experimental_components_detected"
    else:
        status = "sufficient_observability_no_component"

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    figure_path = output / "inference.png"
    arrays_path = output / "inference_arrays.npz"
    report_path = output / "inference_report.json"
    existing = [path for path in (figure_path, arrays_path, report_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite existing inference outputs: "
            + ", ".join(path.name for path in existing)
            + ". Use --overwrite or choose another --output-dir."
        )

    ap_ids_for_plot = sorted(transmitter_positions)
    ap_positions_for_plot = (
        np.asarray([transmitter_positions[key][:2] for key in ap_ids_for_plot])
        if ap_ids_for_plot
        else np.empty((0, 2))
    )
    if ray_matrix.shape[0]:
        displayed_support = support.link_count.astype(float)
        support_label = "Independent RF links through cell (count)"
    else:
        displayed_support = gp_density
        support_label = "GP effective sample density (relative units)"
    save_inference_figure(
        output_path=figure_path,
        grid_x_centers_m=x_centers,
        grid_y_centers_m=y_centers,
        measured_receiver_xy_m=field_positions[:, :2],
        measured_rssi_dbm=field_rssi,
        posterior_mean_dbm=posterior_mean,
        posterior_standard_deviation_db=posterior_std,
        support_density=displayed_support,
        support_label=support_label,
        extrapolation_mask=extrapolation,
        excess_attenuation_map=attenuation,
        excess_attenuation_units="dB/m",
        bootstrap_evidence_frequency=evidence,
        occupancy_state=occupancy_state,
        ap_positions_xy_m=ap_positions_for_plot,
        ap_ids=ap_ids_for_plot,
        ray_start_xy_m=ray_transmitters,
        ray_end_xy_m=ray_receivers,
        component_labels=labels,
        field_ap_id=selected_ap_id,
        show=show,
    )
    write_deterministic_npz(
        arrays_path,
        {
            "angle_bin_count": support.angle_bin_count,
            "attenuation_db_per_m": attenuation,
            "bootstrap_evidence_frequency": evidence,
            "component_labels": labels,
            "conditioning_score": support.conditioning_score,
            "distance_to_receiver_m": support.distance_to_receiver_m,
            "distance_to_sample_m": posterior.support.distance_to_sample_m.reshape(shape),
            "extrapolation_mask": extrapolation,
            "field_support_density": gp_density,
            "link_count": support.link_count,
            "observable_mask": observable,
            "occupancy_evidence_score": occupancy_score,
            "occupancy_state": occupancy_state,
            "pass_consistency": support.pass_consistency,
            "posterior_mean_dbm": posterior_mean,
            "posterior_standard_deviation_db": posterior_std,
            "repeated_link_count": support.repeated_link_count,
            "sensitivity": support.sensitivity,
            "transmitter_count": support.transmitter_count,
            "x_m": x_centers,
            "y_m": y_centers,
        },
    )
    residual_diagnostics = []
    if attenuation_result is not None:
        residual_diagnostics = [
            {
                "ap_id": item.ap_id,
                "receiver_xyz_m": item.receiver_xyz_m,
                "measured_rssi_dbm": item.rssi_dbm,
                "excess_attenuation_db": float(excess[index]),
                "predicted_excess_attenuation_db": float(
                    attenuation_result.predicted_excess_db[index]
                ),
                "residual_db": float(attenuation_result.residuals_db[index]),
                "noise_standard_deviation_db": float(ray_noise[index]),
            }
            for index, item in enumerate(calibrated_links)
        ]
    report = json_safe(
        {
            "schema_version": "1.0",
            "deliverable": "probabilistic RF-assisted mapping",
            "status": status,
            "seed": settings.seed,
            "software": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "matplotlib": matplotlib.__version__,
                "platform": platform.platform(),
            },
            "inputs": [
                {
                    "csv": str(dataset.source_path),
                    "csv_sha256": dataset.input_sha256,
                    "metadata": str(dataset.metadata.source_path)
                    if dataset.metadata
                    else None,
                    "metadata_sha256": file_sha256(dataset.metadata.source_path)
                    if dataset.metadata
                    else None,
                    "schema_version": dataset.schema_version,
                }
                for dataset in datasets
            ],
            "parameters": asdict(settings),
            "field_model": {
                "selected_ap_id": selected_ap_id,
                "calibrated_path_loss_mean": calibrated_field,
                "kernel": "isotropic squared exponential",
                "jitter_used_db2": gp.jitter_used_db2,
                "leave_one_location_out": None
                if lolo is None
                else {
                    "location_count": len(lolo.observed_mean_dbm),
                    "rmse_db": lolo.rmse_db,
                    "mae_db": lolo.mae_db,
                    "residuals_db": lolo.residual_db,
                },
                "resolution_diagnostics": asdict(resolution_diagnostics),
            },
            "calibrations": calibration_documents,
            "sample_statistics": {
                "link_location_count": len(observations),
                "sample_count": sum(item.sample_count for item in observations),
                "outlier_count": sum(item.outlier_count for item in observations),
                "links": [asdict(item) for item in observations],
            },
            "attenuation_model": {
                "forward_model": "2D projected link length times nonnegative dB/m cell density",
                "objective": "weighted Gaussian residual + L1 + smoothed anisotropic total variation",
                "optimizer": "projected gradient with backtracking",
                "convergence_rule": (
                    "relative iterate change or relative objective change <= "
                    "optimizer_relative_tolerance"
                ),
                "iterations": attenuation_result.iterations if attenuation_result else 0,
                "converged": attenuation_result.converged if attenuation_result else False,
                "objective_history": attenuation_result.objective_history
                if attenuation_result
                else [],
                "regularization_sensitivity": sensitivity_runs,
                "bootstrap_converged_fit_count": (
                    bootstrap_result.converged_fit_count if bootstrap_result else 0
                ),
                "bootstrap_fit_count": bootstrap_result.fit_count if bootstrap_result else 0,
                "all_projected_links_fully_covered": ray_coverage_ok,
                "bootstrap_iterations": bootstrap_result.iterations
                if bootstrap_result
                else [],
                "bootstrap_interpretation": (
                    "Parametric refit frequency above attenuation_threshold_db_per_m; "
                    "not a physical occupancy posterior."
                ),
                "residuals": residual_diagnostics,
            },
            "observability": {
                "status": status,
                "thresholds": asdict(settings.observability_config()),
                "metadata_gate_issues": metadata_issues,
                "failed_criteria_cell_counts": support.failed_criteria_counts,
                "observable_cell_count": int(np.count_nonzero(observable)),
                "total_cell_count": int(observable.size),
            },
            "occupancy_semantics": {
                "interpretation": "relative evidence bookkeeping, not posterior probability",
                "unknown_score": UNKNOWN_EVIDENCE_SCORE,
                "limited_free_score": LIMITED_FREE_EVIDENCE_SCORE,
                "attenuation_activation_frequency": settings.evidence_threshold,
                "state_codes": {
                    "0": "unknown",
                    "1": "sampled/AP cell with limited free evidence",
                    "2": "observable attenuation evidence",
                    "3": "conflicting free and attenuation evidence",
                },
            },
            "components": [
                {"label": "potential attenuation-causing obstacle", **asdict(component)}
                for component in components
            ],
            "warnings": list(dict.fromkeys(captured_warnings)),
            "supported_conclusions": (
                [
                    "Measured RSSI and a model-estimated RF field with conditional uncertainty are available.",
                    "Potential attenuation components passed the configured experimental support gate.",
                ]
                if components
                else [
                    "Measured RSSI and a model-estimated RF field with conditional uncertainty are available.",
                    "No obstacle location, polygon, or dimensions are supported by this run.",
                ]
            ),
            "safety": (
                "Unknown RF cells and RF-inferred clear areas are not collision-safe free space; "
                "camera/IMU/VIO/SfM geometry remains authoritative for navigation."
            ),
        }
    )
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return InferenceArtifacts(
        figure_path=figure_path,
        arrays_path=arrays_path,
        report_path=report_path,
        status=status,
        component_count=len(components),
        warnings=tuple(report["warnings"]),
    )
