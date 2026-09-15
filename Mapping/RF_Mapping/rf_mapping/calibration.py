"""Deterministic robust fitting for an unobstructed log-distance calibration."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .data import validate_no_sensitive_keys


CALIBRATION_CSV_FIELDS = ("distance_m", "rssi_dbm", "pass_index")
SAFE_CALIBRATION_METADATA_FIELDS = frozenset(
    {
        "antenna_id",
        "antenna_orientation",
        "antenna_type",
        "ap_id",
        "bandwidth_mhz",
        "board_model",
        "bssid_hash",
        "channel",
        "chip_model",
        "environment_label",
        "phy_mode",
        "receiver_height_cm",
        "transmitter_height_cm",
        "trial_label",
    }
)
CALIBRATION_SCHEMA_VERSION = "1.0"
CALIBRATION_ARTIFACT_TYPE = "rf_log_distance_calibration"


@dataclass(frozen=True)
class CalibrationSample:
    distance_m: float
    rssi_dbm: float
    pass_index: int


@dataclass(frozen=True)
class CalibrationDataset:
    samples: tuple[CalibrationSample, ...]
    metadata: Mapping[str, str]
    input_sha256: str
    source_path: Path


@dataclass(frozen=True)
class CalibrationResult:
    p0_dbm: float
    path_loss_exponent: float
    reference_distance_m: float
    residual_sigma_db: float
    within_pass_sigma_db: float
    between_pass_drift_sigma_db: float
    minimum_distance_m: float
    maximum_distance_m: float
    sample_count: int
    input_sha256: str
    metadata: Mapping[str, str]
    huber_delta: float
    iterations: int
    converged: bool
    downweighted_count: int
    effective_sample_count: float
    rmse_db: float
    weighted_rmse_db: float
    median_absolute_error_db: float
    r_squared: float
    pass_residual_mean_db: Mapping[str, float]
    residuals_db: tuple[float, ...]
    final_weights: tuple[float, ...]
    ols_p0_dbm: float
    ols_path_loss_exponent: float

    def predict_rssi_dbm(self, distance_m: float | Sequence[float]) -> np.ndarray:
        distances = np.asarray(distance_m, dtype=float)
        if not np.all(np.isfinite(distances)) or np.any(distances <= 0.0):
            raise ValueError("Prediction distances must be finite and greater than zero.")
        return self.p0_dbm - 10.0 * self.path_loss_exponent * np.log10(
            distances / self.reference_distance_m
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": CALIBRATION_SCHEMA_VERSION,
            "artifact_type": CALIBRATION_ARTIFACT_TYPE,
            "model": {
                "name": "log_distance_gaussian",
                "reference_distance_m": self.reference_distance_m,
                "p0_dbm": self.p0_dbm,
                "path_loss_exponent": self.path_loss_exponent,
            },
            "noise": {
                "residual_sigma_db": self.residual_sigma_db,
                "within_pass_sigma_db": self.within_pass_sigma_db,
                "between_pass_drift_sigma_db": self.between_pass_drift_sigma_db,
            },
            "fit_range_m": {
                "minimum": self.minimum_distance_m,
                "maximum": self.maximum_distance_m,
            },
            "input": {
                "sha256": self.input_sha256,
                "sample_count": self.sample_count,
                "metadata": dict(self.metadata),
            },
            "optimizer": {
                "method": "Huber IRLS",
                "huber_delta": self.huber_delta,
                "iterations": self.iterations,
                "converged": self.converged,
                "effective_sample_count": self.effective_sample_count,
            },
            "diagnostics": {
                "rmse_db": self.rmse_db,
                "weighted_rmse_db": self.weighted_rmse_db,
                "median_absolute_error_db": self.median_absolute_error_db,
                "r_squared": self.r_squared,
                "pass_residual_mean_db": dict(self.pass_residual_mean_db),
                "pass_count": len(self.pass_residual_mean_db),
                "between_pass_drift_observable": len(self.pass_residual_mean_db) > 1,
                "residuals_db": list(self.residuals_db),
                "final_weights": list(self.final_weights),
            },
            "outlier_sensitivity": {
                "downweighted_count": self.downweighted_count,
                "ols_p0_dbm": self.ols_p0_dbm,
                "ols_path_loss_exponent": self.ols_path_loss_exponent,
                "robust_minus_ols_p0_db": self.p0_dbm - self.ols_p0_dbm,
                "robust_minus_ols_path_loss_exponent": (
                    self.path_loss_exponent - self.ols_path_loss_exponent
                ),
            },
        }


def load_calibration_csv(path: str | Path) -> CalibrationDataset:
    csv_path = Path(path)
    raw_bytes = csv_path.read_bytes()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"Calibration CSV {csv_path} must be UTF-8 encoded.") from error

    reader = csv.DictReader(text.splitlines())
    header = tuple(reader.fieldnames or ())
    if header[: len(CALIBRATION_CSV_FIELDS)] != CALIBRATION_CSV_FIELDS:
        raise ValueError(
            "Calibration CSV must begin with the columns "
            "distance_m,rssi_dbm,pass_index in that order."
        )
    if len(set(header)) != len(header):
        raise ValueError("Calibration CSV column names must be unique.")
    extra_fields = header[len(CALIBRATION_CSV_FIELDS) :]
    unsupported = sorted(set(extra_fields) - SAFE_CALIBRATION_METADATA_FIELDS)
    if unsupported:
        raise ValueError(
            f"Unsupported calibration metadata columns: {unsupported}. Allowed extras are "
            f"{sorted(SAFE_CALIBRATION_METADATA_FIELDS)}."
        )
    validate_no_sensitive_keys({field: None for field in extra_fields}, context="calibration")

    samples: list[CalibrationSample] = []
    metadata_values: dict[str, set[str]] = {field: set() for field in extra_fields}
    try:
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None or value.strip() == "" for value in row.values()):
                raise ValueError(
                    f"Malformed calibration row {row_number}: every column requires a value."
                )
            distance = _finite_float(row["distance_m"], "distance_m", row_number)
            if distance <= 0.0 or distance > 10_000.0:
                raise ValueError(
                    f"Invalid distance_m at calibration row {row_number}: "
                    "expected a value greater than 0 and at most 10000."
                )
            rssi = _finite_float(row["rssi_dbm"], "rssi_dbm", row_number)
            if not -127.0 <= rssi <= 0.0:
                raise ValueError(
                    f"Invalid rssi_dbm at calibration row {row_number}: "
                    "expected a value from -127 through 0 dBm."
                )
            try:
                pass_index = int(row["pass_index"])
            except ValueError as error:
                raise ValueError(
                    f"Invalid pass_index at calibration row {row_number}: expected an integer."
                ) from error
            if pass_index < 1:
                raise ValueError(
                    f"Invalid pass_index at calibration row {row_number}: minimum is 1."
                )
            samples.append(CalibrationSample(distance, rssi, pass_index))
            for field in extra_fields:
                metadata_values[field].add(row[field].strip())
    except csv.Error as error:
        raise ValueError(f"Malformed CSV in {csv_path}: {error}.") from error

    if len(samples) < 3:
        raise ValueError("Calibration requires at least three samples.")
    if len({sample.distance_m for sample in samples}) < 3:
        raise ValueError("Calibration requires at least three distinct known distances.")
    pass_indices = sorted({sample.pass_index for sample in samples})
    if pass_indices != list(range(1, pass_indices[-1] + 1)):
        raise ValueError("Calibration pass_index values must be consecutive and start at 1.")
    distances_by_pass = {
        pass_index: {
            sample.distance_m for sample in samples if sample.pass_index == pass_index
        }
        for pass_index in pass_indices
    }
    if any(
        distances != distances_by_pass[pass_indices[0]]
        for distances in distances_by_pass.values()
    ):
        raise ValueError(
            "Every calibration pass must cover the same known distances so distance "
            "effects are not confounded with pass drift."
        )

    inconsistent = [
        field for field, observed_values in metadata_values.items() if len(observed_values) != 1
    ]
    if inconsistent:
        raise ValueError(
            "Calibration hardware/trial metadata must be constant within one file; "
            f"inconsistent columns: {inconsistent}."
        )
    metadata = {field: next(iter(values)) for field, values in metadata_values.items()}
    _validate_calibration_metadata(metadata)
    return CalibrationDataset(
        tuple(samples), metadata, hashlib.sha256(raw_bytes).hexdigest(), csv_path
    )


def fit_log_distance_calibration(
    dataset: CalibrationDataset,
    *,
    reference_distance_m: float = 1.0,
    huber_delta: float = 1.345,
    maximum_iterations: int = 100,
    tolerance: float = 1e-10,
) -> CalibrationResult:
    """Fit ``P0 - 10 n log10(d/d0)`` with deterministic Huber IRLS."""

    reference_distance = _positive_finite(reference_distance_m, "reference_distance_m")
    delta = _positive_finite(huber_delta, "huber_delta")
    if (
        isinstance(maximum_iterations, bool)
        or not isinstance(maximum_iterations, int)
        or maximum_iterations < 1
    ):
        raise ValueError("maximum_iterations must be a positive integer.")
    fit_tolerance = _positive_finite(tolerance, "tolerance")
    if len(dataset.samples) < 3:
        raise ValueError("Calibration requires at least three samples.")

    distances = np.asarray([sample.distance_m for sample in dataset.samples], dtype=float)
    observed = np.asarray([sample.rssi_dbm for sample in dataset.samples], dtype=float)
    if not np.all(np.isfinite(distances)) or np.any(distances <= 0.0):
        raise ValueError("Calibration distances must be finite and greater than zero.")
    if not np.all(np.isfinite(observed)) or np.any((observed < -127.0) | (observed > 0.0)):
        raise ValueError("Calibration RSSI must be finite and from -127 through 0 dBm.")

    log_distance = np.log10(distances / reference_distance)
    if np.ptp(log_distance) <= 1e-9:
        raise ValueError("Calibration distance span is too small to estimate path loss.")
    design = np.column_stack((np.ones(len(observed)), -10.0 * log_distance))
    ols_parameters = _weighted_least_squares(design, observed, np.ones(len(observed)))
    parameters = ols_parameters.copy()
    weights = np.ones(len(observed), dtype=float)
    converged = False

    for iteration in range(1, maximum_iterations + 1):
        residuals = observed - design @ parameters
        scale = _robust_residual_scale(residuals)
        standardized = np.abs(residuals) / scale
        new_weights = np.ones_like(standardized)
        beyond_delta = standardized > delta
        new_weights[beyond_delta] = delta / standardized[beyond_delta]
        new_parameters = _weighted_least_squares(design, observed, new_weights)
        parameter_change = float(np.max(np.abs(new_parameters - parameters)))
        parameter_scale = 1.0 + float(np.max(np.abs(parameters)))
        parameters = new_parameters
        weights = new_weights
        if parameter_change <= fit_tolerance * parameter_scale:
            converged = True
            break

    p0_dbm, path_loss_exponent = (float(value) for value in parameters)
    if path_loss_exponent <= 0.0:
        raise ValueError(
            "Calibration fit produced a non-positive path-loss exponent. Check that RSSI "
            "decreases with distance and that the sweep is unobstructed."
        )
    if not -127.0 <= p0_dbm <= 0.0:
        raise ValueError(
            "Calibration fit produced P0 outside the valid RSSI range; inspect distance "
            "units, antenna consistency, and outliers."
        )

    predicted = design @ parameters
    residuals = observed - predicted
    final_scale = _robust_residual_scale(residuals)
    standardized = np.abs(residuals) / final_scale
    weights = np.ones_like(standardized)
    beyond_delta = standardized > delta
    weights[beyond_delta] = delta / standardized[beyond_delta]
    residual_sigma = _robust_residual_scale(residuals)
    pass_indices = np.asarray([sample.pass_index for sample in dataset.samples], dtype=int)
    pass_means = {
        str(pass_index): float(np.mean(residuals[pass_indices == pass_index]))
        for pass_index in sorted(set(pass_indices.tolist()))
    }
    drift_sigma = float(np.std(list(pass_means.values()), ddof=0))
    centered_residuals = np.asarray(
        [residual - pass_means[str(pass_index)] for residual, pass_index in zip(residuals, pass_indices)]
    )
    within_pass_sigma = float(np.sqrt(np.mean(centered_residuals**2)))
    rmse = float(np.sqrt(np.mean(residuals**2)))
    weighted_rmse = float(np.sqrt(np.sum(weights * residuals**2) / np.sum(weights)))
    total_sum_squares = float(np.sum((observed - np.mean(observed)) ** 2))
    if total_sum_squares <= np.finfo(float).eps:
        raise ValueError(
            "Calibration RSSI has no usable variation; verify the distance sweep."
        )
    r_squared = 1.0 - float(np.sum(residuals**2)) / total_sum_squares

    return CalibrationResult(
        p0_dbm,
        path_loss_exponent,
        reference_distance,
        residual_sigma,
        within_pass_sigma,
        drift_sigma,
        float(np.min(distances)),
        float(np.max(distances)),
        len(dataset.samples),
        dataset.input_sha256,
        dict(dataset.metadata),
        delta,
        iteration,
        converged,
        int(np.count_nonzero(weights < 1.0 - 1e-12)),
        float(np.sum(weights)),
        rmse,
        weighted_rmse,
        float(np.median(np.abs(residuals))),
        r_squared,
        pass_means,
        tuple(float(value) for value in residuals),
        tuple(float(value) for value in weights),
        float(ols_parameters[0]),
        float(ols_parameters[1]),
    )


def save_calibration(result: CalibrationResult, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result.to_document(), indent=2, sort_keys=True, allow_nan=False)
    output_path.write_text(serialized + "\n", encoding="utf-8")
    return output_path


def load_calibration(path: str | Path) -> CalibrationResult:
    input_path = Path(path)
    try:
        document = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid calibration JSON in {input_path}: {error.msg}.") from error
    if not isinstance(document, dict):
        raise ValueError("Calibration artifact must be a JSON object.")
    validate_no_sensitive_keys(document, context="calibration artifact")
    if document.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        raise ValueError(
            f"Calibration schema_version must be {CALIBRATION_SCHEMA_VERSION!r}."
        )
    if document.get("artifact_type") != CALIBRATION_ARTIFACT_TYPE:
        raise ValueError(f"Calibration artifact_type must be {CALIBRATION_ARTIFACT_TYPE!r}.")

    model = _required_mapping(document, "model")
    noise = _required_mapping(document, "noise")
    fit_range = _required_mapping(document, "fit_range_m")
    input_information = _required_mapping(document, "input")
    optimizer = _required_mapping(document, "optimizer")
    diagnostics = _required_mapping(document, "diagnostics")
    sensitivity = _required_mapping(document, "outlier_sensitivity")
    if model.get("name") != "log_distance_gaussian":
        raise ValueError("Calibration model.name must be 'log_distance_gaussian'.")

    sample_count = _artifact_int(input_information, "sample_count", minimum=3)
    input_hash = input_information.get("sha256")
    if not isinstance(input_hash, str) or len(input_hash) != 64 or any(
        character not in "0123456789abcdef" for character in input_hash
    ):
        raise ValueError("Calibration input.sha256 must be a lowercase SHA-256 digest.")
    metadata = input_information.get("metadata")
    if not isinstance(metadata, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()
    ):
        raise ValueError("Calibration input.metadata must contain string keys and values.")
    _validate_calibration_metadata(metadata)

    residuals = _float_sequence(diagnostics, "residuals_db", sample_count)
    final_weights = _float_sequence(diagnostics, "final_weights", sample_count)
    if any(not 0.0 < weight <= 1.0 for weight in final_weights):
        raise ValueError("Calibration final_weights must be greater than 0 and at most 1.")
    pass_means = diagnostics.get("pass_residual_mean_db")
    if not isinstance(pass_means, dict) or not pass_means:
        raise ValueError("Calibration pass_residual_mean_db must be a non-empty object.")
    validated_pass_means = {
        str(key): _finite_artifact_float(value, f"pass_residual_mean_db.{key}")
        for key, value in pass_means.items()
    }

    minimum_distance = _positive_artifact_float(fit_range, "minimum")
    maximum_distance = _positive_artifact_float(fit_range, "maximum")
    if maximum_distance < minimum_distance:
        raise ValueError("Calibration fit_range_m.maximum must be at least minimum.")
    path_loss_exponent = _positive_artifact_float(model, "path_loss_exponent")
    p0_dbm = _finite_artifact_float(model.get("p0_dbm"), "model.p0_dbm")
    if not -127.0 <= p0_dbm <= 0.0:
        raise ValueError("Calibration model.p0_dbm must be from -127 through 0.")
    downweighted_count = _artifact_int(sensitivity, "downweighted_count", minimum=0)
    if downweighted_count > sample_count:
        raise ValueError("Calibration downweighted_count cannot exceed sample_count.")
    effective_sample_count = _positive_artifact_float(
        optimizer, "effective_sample_count"
    )
    if effective_sample_count > sample_count + 1e-9:
        raise ValueError(
            "Calibration effective_sample_count cannot exceed sample_count."
        )

    return CalibrationResult(
        p0_dbm,
        path_loss_exponent,
        _positive_artifact_float(model, "reference_distance_m"),
        _nonnegative_artifact_float(noise, "residual_sigma_db"),
        _nonnegative_artifact_float(noise, "within_pass_sigma_db"),
        _nonnegative_artifact_float(noise, "between_pass_drift_sigma_db"),
        minimum_distance,
        maximum_distance,
        sample_count,
        input_hash,
        metadata,
        _positive_artifact_float(optimizer, "huber_delta"),
        _artifact_int(optimizer, "iterations", minimum=1),
        _artifact_bool(optimizer, "converged"),
        downweighted_count,
        effective_sample_count,
        _nonnegative_artifact_float(diagnostics, "rmse_db"),
        _nonnegative_artifact_float(diagnostics, "weighted_rmse_db"),
        _nonnegative_artifact_float(diagnostics, "median_absolute_error_db"),
        _finite_artifact_float(diagnostics.get("r_squared"), "diagnostics.r_squared"),
        validated_pass_means,
        residuals,
        final_weights,
        _finite_artifact_float(sensitivity.get("ols_p0_dbm"), "outlier_sensitivity.ols_p0_dbm"),
        _finite_artifact_float(
            sensitivity.get("ols_path_loss_exponent"),
            "outlier_sensitivity.ols_path_loss_exponent",
        ),
    )


def _weighted_least_squares(
    design: np.ndarray, observed: np.ndarray, weights: np.ndarray
) -> np.ndarray:
    square_root_weights = np.sqrt(weights)
    parameters, _, rank, _ = np.linalg.lstsq(
        design * square_root_weights[:, np.newaxis],
        observed * square_root_weights,
        rcond=None,
    )
    if rank != design.shape[1] or not np.all(np.isfinite(parameters)):
        raise ValueError("Calibration design is singular; use a wider distance range.")
    return parameters


def _robust_residual_scale(residuals: np.ndarray) -> float:
    median = float(np.median(residuals))
    mad_scale = 1.482602218505602 * float(np.median(np.abs(residuals - median)))
    if mad_scale > 1e-9:
        return mad_scale
    rms_scale = float(np.sqrt(np.mean((residuals - median) ** 2)))
    return max(rms_scale, 1e-6)


def _finite_float(value: str, field: str, row_number: int) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid {field} at calibration row {row_number}: expected a number."
        ) from error
    if not math.isfinite(parsed):
        raise ValueError(f"Invalid {field} at calibration row {row_number}: must be finite.")
    return parsed


def _validate_calibration_metadata(metadata: Mapping[str, str]) -> None:
    unsupported = sorted(set(metadata) - SAFE_CALIBRATION_METADATA_FIELDS)
    if unsupported:
        raise ValueError(f"Unsupported calibration metadata fields: {unsupported}.")
    if "channel" in metadata:
        try:
            channel = int(metadata["channel"])
        except ValueError as error:
            raise ValueError("Calibration channel must be an integer.") from error
        if not 1 <= channel <= 233:
            raise ValueError("Calibration channel must be from 1 through 233.")
    for key, maximum in (
        ("bandwidth_mhz", 320.0),
        ("receiver_height_cm", 10_000_000.0),
        ("transmitter_height_cm", 10_000_000.0),
    ):
        if key not in metadata:
            continue
        try:
            parsed = float(metadata[key])
        except ValueError as error:
            raise ValueError(f"Calibration {key} must be numeric.") from error
        lower_bound = 1.0 if key == "bandwidth_mhz" else 0.0
        if not math.isfinite(parsed) or not lower_bound <= parsed <= maximum:
            raise ValueError(
                f"Calibration {key} must be finite and from {lower_bound:g} "
                f"through {maximum:g}."
            )


def _positive_finite(value: float, name: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(f"{name} must be finite and greater than zero.")
    return parsed


def _required_mapping(document: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Calibration {key} must be an object.")
    return value


def _finite_artifact_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Calibration {name} must be a finite number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Calibration {name} must be a finite number.") from error
    if not math.isfinite(parsed):
        raise ValueError(f"Calibration {name} must be a finite number.")
    return parsed


def _positive_artifact_float(document: Mapping[str, Any], key: str) -> float:
    parsed = _finite_artifact_float(document.get(key), key)
    if parsed <= 0.0:
        raise ValueError(f"Calibration {key} must be greater than zero.")
    return parsed


def _nonnegative_artifact_float(document: Mapping[str, Any], key: str) -> float:
    parsed = _finite_artifact_float(document.get(key), key)
    if parsed < 0.0:
        raise ValueError(f"Calibration {key} cannot be negative.")
    return parsed


def _artifact_int(document: Mapping[str, Any], key: str, *, minimum: int) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"Calibration {key} must be an integer of at least {minimum}.")
    return value


def _artifact_bool(document: Mapping[str, Any], key: str) -> bool:
    value = document.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"Calibration {key} must be true or false.")
    return value


def _float_sequence(
    document: Mapping[str, Any], key: str, expected_length: int
) -> tuple[float, ...]:
    value = document.get(key)
    if not isinstance(value, list) or len(value) != expected_length:
        raise ValueError(
            f"Calibration {key} must be a list with {expected_length} values."
        )
    return tuple(_finite_artifact_float(item, key) for item in value)
