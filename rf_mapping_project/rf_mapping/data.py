"""Validated survey loading and statistics without altering raw measurements."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import uuid
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


LEGACY_CSV_FIELDS = (
    "pass_index",
    "x_cm",
    "y_cm",
    "sample_index",
    "device_time_ms",
    "rssi_dbm",
)
V2_CSV_FIELDS = LEGACY_CSV_FIELDS + (
    "host_time_utc",
    "host_monotonic_ns",
    "packet_sequence",
    "ap_id",
    "z_cm",
    "yaw_deg",
    "pitch_deg",
    "roll_deg",
)
MAD_OUTLIER_THRESHOLD = 3.5
ZERO_SCALE_OUTLIER_DEVIATION_DB = 10.0

_MAX_COORDINATE_CM = 10_000_000.0
_MAX_DEVICE_TIME_MS = 2**32 - 1
_BSSID_KEYS = {"bssid", "bssid_hash"}
_SENSITIVE_KEY_FRAGMENTS = ("ssid", "password", "token", "credential")
_EXPECTED_METADATA_UNITS = {
    "position": "cm",
    "orientation": "deg",
    "rssi": "dbm",
    "device_time": "ms",
    "host_monotonic": "ns",
}


class MetadataUnavailableWarning(UserWarning):
    """Raised when a survey has no versioned metadata sidecar."""


@dataclass(frozen=True)
class SurveySample:
    pass_index: int
    x_cm: float
    y_cm: float
    sample_index: int
    device_time_ms: int
    rssi_dbm: float
    host_time_utc: str | None = None
    host_monotonic_ns: int | None = None
    packet_sequence: int | None = None
    ap_id: str | None = None
    z_cm: float | None = None
    yaw_deg: float | None = None
    pitch_deg: float | None = None
    roll_deg: float | None = None


@dataclass(frozen=True)
class SurveyMetadata:
    schema_version: str
    run_uuid: str
    document: Mapping[str, Any]
    source_path: Path


@dataclass(frozen=True)
class SurveyDataset:
    samples: tuple[SurveySample, ...]
    schema_version: str
    input_sha256: str
    source_path: Path
    metadata: SurveyMetadata | None


@dataclass(frozen=True)
class DistributionStatistics:
    sample_count: int
    median_rssi_dbm: float
    mean_rssi_dbm: float
    standard_deviation_db: float
    iqr_db: float
    mad_db: float


@dataclass(frozen=True)
class PassStatistics:
    pass_index: int
    raw: DistributionStatistics
    robust: DistributionStatistics
    outlier_count: int
    raw_values_dbm: tuple[float, ...]
    outlier_mask: tuple[bool, ...]


@dataclass(frozen=True)
class LocationStatistics:
    x_cm: float
    y_cm: float
    raw: DistributionStatistics
    robust: DistributionStatistics
    per_pass: tuple[PassStatistics, ...]
    outlier_count: int
    between_pass_standard_deviation_db: float
    pass_drift_db: float
    pass_median_range_db: float
    raw_values_dbm: tuple[float, ...]
    outlier_mask: tuple[bool, ...]


@dataclass(frozen=True)
class InferenceAggregate:
    """One AP/receiver-location observation with temporal noise kept separate."""

    ap_id: str | None
    x_cm: float
    y_cm: float
    z_cm: float | None
    yaw_deg: float | None
    pitch_deg: float | None
    roll_deg: float | None
    robust_central_rssi_dbm: float
    robust_median_rssi_dbm: float
    sample_count: int
    retained_sample_count: int
    pass_count: int
    outlier_count: int
    within_pass_variance_db2: float
    between_pass_variance_db2: float
    central_estimate_variance_db2: float
    pass_median_range_db: float
    pass_drift_db: float
    between_to_within_standard_deviation_ratio: float | None
    per_pass: tuple[PassStatistics, ...]


def validate_no_sensitive_keys(value: Any, *, context: str = "metadata") -> None:
    """Reject secret-bearing key names recursively; BSSID identifiers are not SSIDs."""

    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{context} keys must be strings.")
            normalized_key = key.casefold().replace("-", "_")
            if normalized_key not in _BSSID_KEYS and any(
                fragment in normalized_key for fragment in _SENSITIVE_KEY_FRAGMENTS
            ):
                raise ValueError(
                    f"{context} key {key!r} is forbidden because datasets must not "
                    "contain SSIDs, passwords, tokens, or credentials."
                )
            validate_no_sensitive_keys(nested_value, context=context)
    elif isinstance(value, (list, tuple)):
        for nested_value in value:
            validate_no_sensitive_keys(nested_value, context=context)


def validate_acquisition_metadata_fields(document: Mapping[str, Any]) -> None:
    """Validate optional acquisition sections before a hardware survey starts."""

    if not isinstance(document, dict):
        raise ValueError("Acquisition metadata must be a JSON object.")
    validate_no_sensitive_keys(document, context="acquisition metadata")
    _validate_json_numbers(document, "acquisition metadata")
    _validate_optional_metadata_fields(document)


def load_survey_metadata(path: str | Path) -> SurveyMetadata:
    metadata_path = Path(path)
    try:
        document = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid survey metadata JSON in {metadata_path}: {error.msg}."
        ) from error
    if not isinstance(document, dict):
        raise ValueError("Survey metadata must be a JSON object.")

    return validate_survey_metadata_document(document, metadata_path)


def validate_survey_metadata_document(
    document: Mapping[str, Any],
    source_path: str | Path,
) -> SurveyMetadata:
    """Validate an in-memory v2 sidecar before it is written or consumed."""

    if not isinstance(document, dict):
        raise ValueError("Survey metadata must be a JSON object.")

    validate_acquisition_metadata_fields(document)
    version = document.get("schema_version")
    if version not in (2, "2", "2.0"):
        raise ValueError("Survey metadata schema_version must be 2 or '2.0'.")

    run_uuid = document.get("run_uuid")
    if not isinstance(run_uuid, str):
        raise ValueError("Survey metadata run_uuid must be a UUID string.")
    try:
        uuid.UUID(run_uuid)
    except ValueError as error:
        raise ValueError("Survey metadata run_uuid is not a valid UUID.") from error

    units = document.get("units")
    if not isinstance(units, dict):
        raise ValueError(
            "Survey metadata units must be an object containing position, "
            "orientation, rssi, device_time, and host_monotonic units."
        )
    for quantity, expected_unit in _EXPECTED_METADATA_UNITS.items():
        actual_unit = units.get(quantity)
        if not isinstance(actual_unit, str):
            raise ValueError(f"Survey metadata units.{quantity} is required.")
        if actual_unit.casefold() != expected_unit:
            raise ValueError(
                f"Survey metadata units.{quantity}={actual_unit!r} contradicts "
                f"the CSV schema; expected {expected_unit!r}."
            )

    for object_name in (
        "run",
        "pose",
        "hardware",
        "channel",
        "calibration",
        "data",
        "measurement",
        "sampling",
        "environment",
    ):
        if object_name in document and not isinstance(document[object_name], dict):
            raise ValueError(f"Survey metadata {object_name} must be an object.")
    if "transmitter" in document and not isinstance(document["transmitter"], dict):
        raise ValueError("Survey metadata transmitter must be an object.")
    if "transmitters" in document:
        transmitters = document["transmitters"]
        if not isinstance(transmitters, list) or not all(
            isinstance(item, dict) for item in transmitters
        ):
            raise ValueError("Survey metadata transmitters must be a list of objects.")

    return SurveyMetadata("2.0", run_uuid, document, Path(source_path))


def load_survey_csv(
    path: str | Path,
    metadata_path: str | Path | None = None,
) -> SurveyDataset:
    """Load legacy or v2 rows, preserving legacy meaning and raw row order."""

    csv_path = Path(path)
    try:
        raw_bytes = csv_path.read_bytes()
    except OSError:
        raise

    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"Survey CSV {csv_path} must be UTF-8 encoded.") from error

    reader = csv.DictReader(text.splitlines())
    header = tuple(reader.fieldnames or ())
    if header == LEGACY_CSV_FIELDS:
        schema_version = "legacy-1"
        row_parser = _parse_legacy_row
    elif header == V2_CSV_FIELDS:
        schema_version = "2.0"
        row_parser = _parse_v2_row
    else:
        raise ValueError(
            f"Unexpected CSV header in {csv_path}. Expected exactly "
            f"{list(LEGACY_CSV_FIELDS)} (legacy) or {list(V2_CSV_FIELDS)} (v2)."
        )

    samples: list[SurveySample] = []
    try:
        for row_number, row in enumerate(reader, start=2):
            if None in row or any(value is None or value == "" for value in row.values()):
                raise ValueError(
                    f"Malformed survey row {row_number}: every schema field requires a value."
                )
            samples.append(row_parser(row, row_number))
    except csv.Error as error:
        raise ValueError(f"Malformed CSV in {csv_path}: {error}.") from error

    if not samples:
        raise ValueError(f"Survey CSV {csv_path} does not contain any samples.")
    _validate_sample_sequences(samples, schema_version)

    metadata: SurveyMetadata | None
    if metadata_path is None:
        metadata = None
        warnings.warn(
            f"Survey metadata unavailable for {csv_path}; pose, transmitter, "
            "hardware, channel, and timing metadata were not inferred.",
            MetadataUnavailableWarning,
            stacklevel=2,
        )
    else:
        metadata = load_survey_metadata(metadata_path)
        _validate_metadata_against_csv(metadata, schema_version, samples, raw_bytes)

    return SurveyDataset(
        tuple(samples),
        schema_version,
        hashlib.sha256(raw_bytes).hexdigest(),
        csv_path,
        metadata,
    )


def compute_location_statistics(
    samples_or_dataset: SurveyDataset | Iterable[SurveySample],
    *,
    mad_threshold: float = MAD_OUTLIER_THRESHOLD,
) -> dict[tuple[float, float], LocationStatistics]:
    """Summarize each pass separately, then aggregate without erasing pass drift.

    A sample is excluded only from the ``robust`` summaries when its modified
    MAD z-score exceeds ``mad_threshold``. Raw values and masks are retained.
    Zero MAD falls back to an IQR scale; if both are zero, only a deviation
    greater than 10 dB is flagged so ordinary quantized RSSI is retained.
    """

    if not math.isfinite(mad_threshold) or mad_threshold <= 0:
        raise ValueError("mad_threshold must be finite and greater than zero.")
    samples = (
        samples_or_dataset.samples
        if isinstance(samples_or_dataset, SurveyDataset)
        else tuple(samples_or_dataset)
    )
    if not samples:
        raise ValueError("At least one survey sample is required for statistics.")

    grouped: dict[tuple[float, float], dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for sample in samples:
        grouped[(sample.x_cm, sample.y_cm)][sample.pass_index].append(sample.rssi_dbm)

    results: dict[tuple[float, float], LocationStatistics] = {}
    for coordinate in sorted(grouped, key=lambda item: (item[1], item[0])):
        pass_summaries: list[PassStatistics] = []
        aggregate_values: list[float] = []
        aggregate_mask: list[bool] = []
        for pass_index in sorted(grouped[coordinate]):
            values = tuple(grouped[coordinate][pass_index])
            pass_summary = _pass_statistics(pass_index, values, mad_threshold)
            pass_summaries.append(pass_summary)
            aggregate_values.extend(values)
            aggregate_mask.extend(pass_summary.outlier_mask)

        retained_values = tuple(
            value
            for value, flagged in zip(aggregate_values, aggregate_mask)
            if not flagged
        )
        pass_medians = [summary.robust.median_rssi_dbm for summary in pass_summaries]
        results[coordinate] = LocationStatistics(
            coordinate[0],
            coordinate[1],
            _distribution_statistics(aggregate_values),
            _distribution_statistics(retained_values),
            tuple(pass_summaries),
            sum(aggregate_mask),
            float(statistics.pstdev(pass_medians)) if len(pass_medians) > 1 else 0.0,
            pass_medians[-1] - pass_medians[0],
            max(pass_medians) - min(pass_medians),
            tuple(aggregate_values),
            tuple(aggregate_mask),
        )
    return results


def compute_inference_aggregates(
    samples_or_dataset: SurveyDataset | Iterable[SurveySample],
    *,
    mad_threshold: float = MAD_OUTLIER_THRESHOLD,
    zero_scale_absolute_threshold_db: float = ZERO_SCALE_OUTLIER_DEVIATION_DB,
) -> dict[
    tuple[
        str | None,
        float,
        float,
        float | None,
        float | None,
        float | None,
        float | None,
    ],
    InferenceAggregate,
]:
    """Aggregate without mixing transmitters, heights, or passes.

    Within-pass variance describes short-term RSSI scatter. Between-pass
    variance and median range expose temporal drift. Their ratio is a numeric
    consistency diagnostic (lower is more repeatable), not a pass/fail claim.
    ``central_estimate_variance_db2`` combines the variance of the retained
    sample mean and pass-to-pass mean; downstream models may impose a separate
    calibrated noise floor.
    """

    if not math.isfinite(mad_threshold) or mad_threshold <= 0.0:
        raise ValueError("mad_threshold must be finite and greater than zero.")
    if (
        not math.isfinite(zero_scale_absolute_threshold_db)
        or zero_scale_absolute_threshold_db <= 0.0
    ):
        raise ValueError(
            "zero_scale_absolute_threshold_db must be finite and greater than zero."
        )
    samples = (
        samples_or_dataset.samples
        if isinstance(samples_or_dataset, SurveyDataset)
        else tuple(samples_or_dataset)
    )
    if not samples:
        raise ValueError("At least one survey sample is required for statistics.")

    grouped: dict[
        tuple[
            str | None,
            float,
            float,
            float | None,
            float | None,
            float | None,
            float | None,
        ],
        dict[int, list[float]],
    ] = defaultdict(lambda: defaultdict(list))
    for sample in samples:
        key = (
            sample.ap_id,
            sample.x_cm,
            sample.y_cm,
            sample.z_cm,
            sample.yaw_deg,
            sample.pitch_deg,
            sample.roll_deg,
        )
        grouped[key][sample.pass_index].append(sample.rssi_dbm)

    output: dict[
        tuple[
            str | None,
            float,
            float,
            float | None,
            float | None,
            float | None,
            float | None,
        ],
        InferenceAggregate,
    ] = {}
    sort_key = lambda key: (
        "" if key[0] is None else key[0],
        key[2],
        key[1],
        -math.inf if key[3] is None else key[3],
        -math.inf if key[4] is None else key[4],
        -math.inf if key[5] is None else key[5],
        -math.inf if key[6] is None else key[6],
    )
    for key in sorted(grouped, key=sort_key):
        pass_summaries = tuple(
            _pass_statistics(
                pass_index,
                grouped[key][pass_index],
                mad_threshold,
                zero_scale_absolute_threshold_db,
            )
            for pass_index in sorted(grouped[key])
        )
        retained_values = tuple(
            value
            for summary in pass_summaries
            for value, flagged in zip(summary.raw_values_dbm, summary.outlier_mask)
            if not flagged
        )
        pass_medians = np.asarray(
            [summary.robust.median_rssi_dbm for summary in pass_summaries], dtype=float
        )
        retained_count = len(retained_values)
        within_variance = float(
            sum(
                summary.robust.sample_count
                * summary.robust.standard_deviation_db**2
                for summary in pass_summaries
            )
            / retained_count
        )
        between_variance = float(np.var(pass_medians, ddof=0))
        within_standard_deviation = math.sqrt(within_variance)
        between_standard_deviation = math.sqrt(between_variance)
        if within_standard_deviation > 0.0:
            consistency_ratio = between_standard_deviation / within_standard_deviation
        elif between_standard_deviation == 0.0:
            consistency_ratio = 0.0
        else:
            consistency_ratio = None
        output[key] = InferenceAggregate(
            key[0],
            key[1],
            key[2],
            key[3],
            key[4],
            key[5],
            key[6],
            float(np.mean(np.asarray(retained_values, dtype=float))),
            float(np.median(np.asarray(retained_values, dtype=float))),
            sum(summary.raw.sample_count for summary in pass_summaries),
            retained_count,
            len(pass_summaries),
            sum(summary.outlier_count for summary in pass_summaries),
            within_variance,
            between_variance,
            within_variance / retained_count
            + between_variance / len(pass_summaries),
            float(np.ptp(pass_medians)),
            float(pass_medians[-1] - pass_medians[0]),
            consistency_ratio,
            pass_summaries,
        )
    return output


def _parse_legacy_row(row: Mapping[str, str], row_number: int) -> SurveySample:
    return SurveySample(
        _parse_int(row["pass_index"], "pass_index", row_number, minimum=1),
        _parse_int(
            row["x_cm"],
            "x_cm",
            row_number,
            minimum=-int(_MAX_COORDINATE_CM),
            maximum=int(_MAX_COORDINATE_CM),
        ),
        _parse_int(
            row["y_cm"],
            "y_cm",
            row_number,
            minimum=-int(_MAX_COORDINATE_CM),
            maximum=int(_MAX_COORDINATE_CM),
        ),
        _parse_int(row["sample_index"], "sample_index", row_number, minimum=0),
        _parse_int(
            row["device_time_ms"],
            "device_time_ms",
            row_number,
            minimum=0,
            maximum=_MAX_DEVICE_TIME_MS,
        ),
        _parse_int(row["rssi_dbm"], "rssi_dbm", row_number, minimum=-127, maximum=0),
    )


def _parse_v2_row(row: Mapping[str, str], row_number: int) -> SurveySample:
    host_time = row["host_time_utc"]
    _validate_utc_timestamp(host_time, row_number)
    ap_id = row["ap_id"].strip()
    if not ap_id or len(ap_id) > 256 or any(ord(character) < 32 for character in ap_id):
        raise ValueError(f"Invalid ap_id at survey row {row_number}.")
    return SurveySample(
        _parse_int(row["pass_index"], "pass_index", row_number, minimum=1),
        _parse_float(
            row["x_cm"], "x_cm", row_number, -_MAX_COORDINATE_CM, _MAX_COORDINATE_CM
        ),
        _parse_float(
            row["y_cm"], "y_cm", row_number, -_MAX_COORDINATE_CM, _MAX_COORDINATE_CM
        ),
        _parse_int(row["sample_index"], "sample_index", row_number, minimum=0),
        _parse_int(
            row["device_time_ms"],
            "device_time_ms",
            row_number,
            minimum=0,
            maximum=_MAX_DEVICE_TIME_MS,
        ),
        _parse_float(row["rssi_dbm"], "rssi_dbm", row_number, -127.0, 0.0),
        host_time,
        _parse_int(
            row["host_monotonic_ns"], "host_monotonic_ns", row_number, minimum=0
        ),
        _parse_int(row["packet_sequence"], "packet_sequence", row_number, minimum=0),
        ap_id,
        _parse_float(
            row["z_cm"], "z_cm", row_number, -_MAX_COORDINATE_CM, _MAX_COORDINATE_CM
        ),
        _parse_float(row["yaw_deg"], "yaw_deg", row_number, -180.0, 180.0),
        _parse_float(row["pitch_deg"], "pitch_deg", row_number, -90.0, 90.0),
        _parse_float(row["roll_deg"], "roll_deg", row_number, -180.0, 180.0),
    )


def _parse_int(
    value: str,
    field: str,
    row_number: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid {field} at survey row {row_number}: expected an integer, got {value!r}."
        ) from error
    if minimum is not None and parsed < minimum:
        raise ValueError(f"Invalid {field} at survey row {row_number}: minimum is {minimum}.")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"Invalid {field} at survey row {row_number}: maximum is {maximum}.")
    return parsed


def _parse_float(
    value: str,
    field: str,
    row_number: int,
    minimum: float,
    maximum: float,
) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise ValueError(
            f"Invalid {field} at survey row {row_number}: expected a number, got {value!r}."
        ) from error
    if not math.isfinite(parsed) or not minimum <= parsed <= maximum:
        raise ValueError(
            f"Invalid {field} at survey row {row_number}: expected a finite value "
            f"from {minimum} through {maximum}."
        )
    return parsed


def _validate_utc_timestamp(value: str, row_number: int) -> None:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(
            f"Invalid host_time_utc at survey row {row_number}: use ISO 8601 UTC."
        ) from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(
            f"Invalid host_time_utc at survey row {row_number}: timestamp must be UTC."
        )


def _validate_sample_sequences(samples: Sequence[SurveySample], schema_version: str) -> None:
    pass_indices = sorted({sample.pass_index for sample in samples})
    if pass_indices != list(range(1, pass_indices[-1] + 1)):
        raise ValueError("Survey pass_index values must be consecutive and start at 1.")

    groups: dict[
        tuple[
            int,
            float,
            float,
            float | None,
            float | None,
            float | None,
            float | None,
            str | None,
        ],
        list[SurveySample],
    ] = defaultdict(list)
    for sample in samples:
        groups[
            (
                sample.pass_index,
                sample.x_cm,
                sample.y_cm,
                sample.z_cm,
                sample.yaw_deg,
                sample.pitch_deg,
                sample.roll_deg,
                sample.ap_id,
            )
        ].append(sample)
    for key, group in groups.items():
        sample_indices = [sample.sample_index for sample in group]
        if sample_indices != list(range(len(group))):
            raise ValueError(
                "sample_index must start at 0 and be contiguous in file order for "
                f"pass/location/AP group {key}; got {sample_indices}."
            )
        for earlier, later in zip(group, group[1:]):
            if not _device_time_advances(earlier.device_time_ms, later.device_time_ms):
                raise ValueError(
                    "device_time_ms must increase within each measurement dwell "
                    f"(32-bit wrap is supported); group {key} is invalid."
                )

    if schema_version == "2.0":
        streams: dict[tuple[int, str | None], list[SurveySample]] = defaultdict(list)
        for sample in samples:
            streams[(sample.pass_index, sample.ap_id)].append(sample)
        for key, stream in streams.items():
            packet_sequences = [sample.packet_sequence for sample in stream]
            host_times = [sample.host_monotonic_ns for sample in stream]
            if any(
                current is None or previous is None or current <= previous
                for previous, current in zip(packet_sequences, packet_sequences[1:])
            ):
                raise ValueError(
                    f"packet_sequence must strictly increase for pass/AP stream {key}."
                )
            if any(
                current is None or previous is None or current <= previous
                for previous, current in zip(host_times, host_times[1:])
            ):
                raise ValueError(
                    f"host_monotonic_ns must strictly increase for pass/AP stream {key}."
                )


def _device_time_advances(previous: int, current: int) -> bool:
    if current > previous:
        return True
    return previous >= 0xF0000000 and current <= 0x0FFFFFFF


def _pass_statistics(
    pass_index: int,
    values: Sequence[float],
    mad_threshold: float,
    zero_scale_absolute_threshold_db: float = ZERO_SCALE_OUTLIER_DEVIATION_DB,
) -> PassStatistics:
    raw_values = tuple(values)
    mask = _mad_outlier_mask(
        raw_values, mad_threshold, zero_scale_absolute_threshold_db
    )
    retained = tuple(
        value for value, flagged in zip(raw_values, mask) if not flagged
    )
    return PassStatistics(
        pass_index,
        _distribution_statistics(raw_values),
        _distribution_statistics(retained),
        sum(mask),
        raw_values,
        mask,
    )


def _mad_outlier_mask(
    values: Sequence[float],
    threshold: float,
    zero_scale_absolute_threshold_db: float = ZERO_SCALE_OUTLIER_DEVIATION_DB,
) -> tuple[bool, ...]:
    if len(values) < 3:
        return (False,) * len(values)
    array = np.asarray(values, dtype=float)
    median = float(np.median(array))
    deviations = np.abs(array - median)
    mad = float(np.median(deviations))
    if mad == 0.0:
        first_quartile, third_quartile = np.percentile(array, [25.0, 75.0])
        iqr_scale = float(third_quartile - first_quartile) / 1.3489795003921634
        if iqr_scale > 0.0:
            return tuple(bool(value > threshold) for value in deviations / iqr_scale)
        return tuple(
            bool(deviation > zero_scale_absolute_threshold_db)
            for deviation in deviations
        )
    modified_z = 0.6744897501960817 * deviations / mad
    return tuple(bool(value > threshold) for value in modified_z)


def _distribution_statistics(values: Sequence[float]) -> DistributionStatistics:
    if not values:
        raise ValueError("Robust filtering removed every sample; inspect the raw values.")
    array = np.asarray(values, dtype=float)
    first_quartile, third_quartile = np.percentile(array, [25.0, 75.0])
    median = float(np.median(array))
    return DistributionStatistics(
        len(values),
        median,
        float(np.mean(array)),
        float(np.std(array, ddof=0)),
        float(third_quartile - first_quartile),
        float(np.median(np.abs(array - median))),
    )


def _validate_optional_metadata_fields(document: Mapping[str, Any]) -> None:
    run = document.get("run", {})
    if isinstance(run, Mapping):
        timestamps = {}
        for key in ("host_started_utc", "host_finished_utc"):
            if key in run:
                timestamps[key] = _metadata_utc_timestamp(run[key], f"run.{key}")
        if (
            "host_started_utc" in timestamps
            and "host_finished_utc" in timestamps
            and timestamps["host_finished_utc"] < timestamps["host_started_utc"]
        ):
            raise ValueError("Survey metadata run finishes before it starts.")
    if "created_utc" in document:
        _metadata_utc_timestamp(document["created_utc"], "created_utc")

    pose = document.get("pose", {})
    if isinstance(pose, Mapping):
        if "source" in pose and (
            not isinstance(pose["source"], str) or not pose["source"].strip()
        ):
            raise ValueError("Survey metadata pose.source must be a non-empty string.")
        for key in ("receiver_z_cm", "yaw_deg", "pitch_deg", "roll_deg"):
            if key in pose and pose[key] is not None:
                minimum, maximum = {
                    "receiver_z_cm": (-_MAX_COORDINATE_CM, _MAX_COORDINATE_CM),
                    "yaw_deg": (-180.0, 180.0),
                    "pitch_deg": (-90.0, 90.0),
                    "roll_deg": (-180.0, 180.0),
                }[key]
                _metadata_number(pose[key], f"pose.{key}", minimum, maximum)
        for key in ("position_standard_deviation_cm", "orientation_standard_deviation_deg"):
            if key in pose:
                values = pose[key]
                if not isinstance(values, list) or len(values) != 3:
                    raise ValueError(f"Survey metadata pose.{key} must have three values.")
                for index, value in enumerate(values):
                    _metadata_number(value, f"pose.{key}[{index}]", 0.0, None)
        for key in ("standard_deviation_cm",):
            if key in pose:
                _metadata_number(pose[key], f"pose.{key}", 0.0, None)
        for key in ("covariance_cm2", "covariance"):
            if key in pose:
                _validate_covariance(pose[key], f"pose.{key}")

    transmitter_items: list[Mapping[str, Any]] = []
    singular = document.get("transmitter")
    if isinstance(singular, Mapping):
        transmitter_items.append(singular)
    plural = document.get("transmitters")
    if isinstance(plural, list):
        transmitter_items.extend(plural)
    identifiers: set[str] = set()
    for index, transmitter in enumerate(transmitter_items):
        label = f"transmitters[{index}]"
        identifier = transmitter.get("ap_id")
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or len(identifier) > 256
            or any(ord(character) < 32 for character in identifier)
        ):
            raise ValueError(f"Survey metadata {label}.ap_id must be a non-empty string.")
        if identifier in identifiers:
            raise ValueError(f"Survey metadata repeats transmitter ap_id {identifier!r}.")
        identifiers.add(identifier)
        nested_position = transmitter.get("position_cm")
        flat_present = any(f"{axis}_cm" in transmitter for axis in ("x", "y", "z"))
        if nested_position is not None:
            if not isinstance(nested_position, Mapping):
                raise ValueError(f"Survey metadata {label}.position_cm must be an object.")
            nested_values = [nested_position.get(axis) for axis in ("x", "y", "z")]
            if any(value is None for value in nested_values):
                raise ValueError(f"Survey metadata {label}.position_cm requires x, y, and z.")
        else:
            nested_values = []
        if flat_present:
            flat_values = [transmitter.get(f"{axis}_cm") for axis in ("x", "y", "z")]
            if any(value is None for value in flat_values):
                raise ValueError(f"Survey metadata {label} requires x_cm, y_cm, and z_cm.")
        else:
            flat_values = []
        if not nested_values and not flat_values:
            raise ValueError(f"Survey metadata {label} requires a complete 3D position.")
        for coordinate_index, value in enumerate(nested_values or flat_values):
            _metadata_number(
                value,
                f"{label}.position[{coordinate_index}]",
                -_MAX_COORDINATE_CM,
                _MAX_COORDINATE_CM,
            )
        if nested_values and flat_values:
            nested_array = np.asarray(nested_values, dtype=float)
            flat_array = np.asarray(flat_values, dtype=float)
            if not np.allclose(nested_array, flat_array, rtol=0.0, atol=1e-9):
                raise ValueError(
                    f"Survey metadata {label} has contradictory nested and flat positions."
                )

    channel = document.get("channel", {})
    if isinstance(channel, Mapping):
        channel_values = [
            channel[key] for key in ("channel", "channel_number") if key in channel
        ]
        if channel_values:
            parsed_channels = [
                _metadata_integer(value, "channel.channel", 1, 233)
                for value in channel_values
            ]
            if len(set(parsed_channels)) != 1:
                raise ValueError("Survey metadata channel fields contradict each other.")
        if "bandwidth_mhz" in channel:
            _metadata_number(channel["bandwidth_mhz"], "channel.bandwidth_mhz", 1.0, 320.0)
        if "phy_mode" in channel and (
            not isinstance(channel["phy_mode"], str) or not channel["phy_mode"].strip()
        ):
            raise ValueError("Survey metadata channel.phy_mode must be a non-empty string.")

    hardware = document.get("hardware", {})
    if isinstance(hardware, Mapping):
        for key in (
            "board_model",
            "chip_model",
            "antenna_type",
            "antenna_id",
            "antenna_orientation",
            "orientation_convention",
        ):
            if key in hardware and (
                not isinstance(hardware[key], str) or not hardware[key].strip()
            ):
                raise ValueError(
                    f"Survey metadata hardware.{key} must be a non-empty string."
                )

    for section_name in ("measurement", "sampling"):
        section = document.get(section_name, {})
        if not isinstance(section, Mapping):
            continue
        for key in (
            "samples_per_point",
            "pass_count",
            "samples_per_location",
            "sample_interval_ms",
            "packet_loss_count",
        ):
            if key in section:
                minimum = 0 if key == "packet_loss_count" else 1
                _metadata_integer(section[key], f"{section_name}.{key}", minimum, None)
        for key in (
            "nominal_sample_rate_hz",
            "nominal_dwell_time_s",
            "sample_rate_hz",
            "dwell_time_s",
        ):
            if key in section:
                _metadata_number(section[key], f"{section_name}.{key}", 0.0, None)
                if float(section[key]) == 0.0:
                    raise ValueError(
                        f"Survey metadata {section_name}.{key} must be greater than zero."
                    )
        if "packet_success_fraction" in section:
            _metadata_number(
                section["packet_success_fraction"],
                f"{section_name}.packet_success_fraction",
                0.0,
                1.0,
            )

    data = document.get("data", {})
    if isinstance(data, Mapping):
        if "csv_schema" in data and data["csv_schema"] not in {"legacy-1", "2.0"}:
            raise ValueError("Survey metadata data.csv_schema must be 'legacy-1' or '2.0'.")
        if "csv_sha256" in data:
            _validate_sha256(data["csv_sha256"], "data.csv_sha256")
        for key in (
            "received_sample_count",
            "expected_sample_count_for_completed_points",
            "packet_loss_count",
        ):
            if key in data:
                _metadata_integer(data[key], f"data.{key}", 0, None)
        for key in ("csi_available", "noise_floor_available"):
            if key in data and not isinstance(data[key], bool):
                raise ValueError(f"Survey metadata data.{key} must be true or false.")
        expected = data.get("expected_sample_count_for_completed_points")
        received = data.get("received_sample_count")
        losses = data.get("packet_loss_count")
        if expected is not None and received is not None and int(expected) < int(received):
            raise ValueError("Survey metadata expected sample count is below received count.")
        if expected is not None and received is not None and losses is not None:
            if int(losses) != int(expected) - int(received):
                raise ValueError("Survey metadata packet_loss_count contradicts sample counts.")

    calibration = document.get("calibration", {})
    if isinstance(calibration, Mapping):
        if calibration.get("sha256") is not None:
            _validate_sha256(calibration["sha256"], "calibration.sha256")
        for key in ("file", "version"):
            if calibration.get(key) is not None and not isinstance(calibration[key], str):
                raise ValueError(f"Survey metadata calibration.{key} must be a string or null.")


def _validate_metadata_against_csv(
    metadata: SurveyMetadata,
    schema_version: str,
    samples: Sequence[SurveySample],
    raw_bytes: bytes,
) -> None:
    data = metadata.document.get("data")
    if isinstance(data, Mapping):
        declared_schema = data.get("csv_schema")
        if declared_schema is not None and declared_schema != schema_version:
            raise ValueError(
                f"Survey metadata declares CSV schema {declared_schema!r}, but the file is "
                f"{schema_version!r}."
            )
        declared_hash = data.get("csv_sha256")
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
        if declared_hash is not None and declared_hash != actual_hash:
            raise ValueError("Survey metadata data.csv_sha256 does not match the survey CSV.")
        declared_count = data.get("received_sample_count")
        if declared_count is not None and declared_count != len(samples):
            raise ValueError(
                "Survey metadata received_sample_count does not match the survey CSV."
            )
    if schema_version == "2.0":
        pose = metadata.document.get("pose", {})
        if isinstance(pose, Mapping):
            for metadata_key, sample_attribute in (
                ("receiver_z_cm", "z_cm"),
                ("yaw_deg", "yaw_deg"),
                ("pitch_deg", "pitch_deg"),
                ("roll_deg", "roll_deg"),
            ):
                declared = pose.get(metadata_key)
                if declared is not None and any(
                    not math.isclose(
                        float(declared),
                        float(getattr(sample, sample_attribute)),
                        rel_tol=0.0,
                        abs_tol=1e-9,
                    )
                    for sample in samples
                ):
                    raise ValueError(
                        f"Survey metadata pose.{metadata_key} contradicts the CSV."
                    )
        sampling = metadata.document.get("sampling", {})
        if isinstance(sampling, Mapping) and "pass_count" in sampling:
            actual_pass_count = len({sample.pass_index for sample in samples})
            if sampling["pass_count"] != actual_pass_count:
                raise ValueError(
                    "Survey metadata sampling.pass_count contradicts the CSV."
                )
        transmitters = metadata.document.get("transmitters")
        if transmitters is None and isinstance(metadata.document.get("transmitter"), dict):
            transmitters = [metadata.document["transmitter"]]
        if isinstance(transmitters, list) and transmitters:
            declared_ids = {item["ap_id"] for item in transmitters}
            sample_ids = {sample.ap_id for sample in samples}
            missing_ids = sorted(str(value) for value in sample_ids - declared_ids)
            if missing_ids:
                raise ValueError(
                    "Survey CSV contains AP IDs absent from metadata: "
                    + ", ".join(missing_ids)
                )


def _metadata_number(
    value: Any,
    name: str,
    minimum: float | None,
    maximum: float | None,
) -> float:
    if isinstance(value, bool):
        raise ValueError(f"Survey metadata {name} must be a finite number.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Survey metadata {name} must be a finite number.") from error
    if not math.isfinite(parsed):
        raise ValueError(f"Survey metadata {name} must be a finite number.")
    if minimum is not None and parsed < minimum:
        raise ValueError(f"Survey metadata {name} must be at least {minimum}.")
    if maximum is not None and parsed > maximum:
        raise ValueError(f"Survey metadata {name} must be at most {maximum}.")
    return parsed


def _metadata_integer(
    value: Any,
    name: str,
    minimum: int | None,
    maximum: int | None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Survey metadata {name} must be an integer.")
    if minimum is not None and value < minimum:
        raise ValueError(f"Survey metadata {name} must be at least {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"Survey metadata {name} must be at most {maximum}.")
    return value


def _metadata_utc_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Survey metadata {name} must be an ISO 8601 UTC string.")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"Survey metadata {name} must be ISO 8601 UTC.") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"Survey metadata {name} must be UTC.")
    return parsed


def _validate_covariance(value: Any, name: str) -> None:
    if isinstance(value, list) and any(
        isinstance(item, bool)
        for row in value
        for item in (row if isinstance(row, list) else [row])
    ):
        raise ValueError(f"Survey metadata {name} must contain numeric values, not booleans.")
    try:
        matrix = np.asarray(value, dtype=float)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Survey metadata {name} must be a numeric 2x2 or 3x3 matrix.") from error
    if matrix.shape not in {(2, 2), (3, 3)} or not np.isfinite(matrix).all():
        raise ValueError(f"Survey metadata {name} must be a finite 2x2 or 3x3 matrix.")
    if not np.allclose(matrix, matrix.T, rtol=0.0, atol=1e-9):
        raise ValueError(f"Survey metadata {name} must be symmetric.")
    if float(np.min(np.linalg.eigvalsh(matrix))) < -1e-9:
        raise ValueError(f"Survey metadata {name} must be positive semidefinite.")


def _validate_sha256(value: Any, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"Survey metadata {name} must be a lowercase SHA-256 digest.")


def _validate_json_numbers(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            _validate_json_numbers(nested_value, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested_value in enumerate(value):
            _validate_json_numbers(nested_value, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} contains a non-finite number.")
