from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import serial
from serial.tools import list_ports

from rf_mapping.data import (
    V2_CSV_FIELDS,
    load_survey_csv,
    validate_acquisition_metadata_fields,
    validate_survey_metadata_document,
)


SERIAL_BAUD = 115200
SERIAL_READ_TIMEOUT_SECONDS = 0.25
DEVICE_READY_TIMEOUT_SECONDS = 45.0
POINT_MEASUREMENT_TIMEOUT_SECONDS = 20.0
PING_INTERVAL_SECONDS = 1.0
DEVICE_RESET_DELAY_SECONDS = 2.0
ANNOTATION_CELL_LIMIT = 100
PLOT_DPI = 180
SINGLE_CELL_HALF_WIDTH_METERS = 0.25
SAMPLES_PER_POINT = 50
MAX_DEVICE_TIME_MS = 2**32 - 1
MAX_COORDINATE_CM = 100_000

RAW_HEADER = [
    "pass_index",
    "x_cm",
    "y_cm",
    "sample_index",
    "device_time_ms",
    "rssi_dbm",
]
RICH_RAW_HEADER = list(V2_CSV_FIELDS)


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value cannot be negative")
    return parsed


def bounded_float(minimum: float, maximum: float):
    def parse(value: str) -> float:
        parsed = float(value)
        if not np.isfinite(parsed) or not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(
                f"value must be finite and from {minimum} through {maximum}"
            )
        return parsed

    return parse


def positive_float(value: str) -> float:
    parsed = float(value)
    if not np.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("value must be finite and greater than zero")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if not np.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be finite and nonnegative")
    return parsed


def select_serial_port(requested_port: str | None) -> str:
    if requested_port:
        return requested_port

    ports = list(list_ports.comports())
    if not ports:
        raise RuntimeError("No serial ports were found.")

    if len(ports) == 1:
        print(f"Using serial port {ports[0].device}: {ports[0].description}")
        return ports[0].device

    print("Available serial ports:")
    for index, port in enumerate(ports, start=1):
        print(f"  {index}: {port.device} - {port.description}")

    while True:
        selection = input("Select the ESP32 port number: ").strip()
        try:
            selected_index = int(selection) - 1
        except ValueError:
            print("Enter one of the listed numbers.")
            continue

        if 0 <= selected_index < len(ports):
            return ports[selected_index].device

        print("Enter one of the listed numbers.")


def read_device_line(connection: serial.Serial) -> str | None:
    raw_line = connection.readline()
    if not raw_line:
        return None

    return raw_line.decode("utf-8", errors="replace").strip()


def wait_for_device(connection: serial.Serial) -> None:
    deadline = time.monotonic() + DEVICE_READY_TIMEOUT_SECONDS
    next_ping_time = time.monotonic()

    while time.monotonic() < deadline:
        now = time.monotonic()
        if now >= next_ping_time:
            connection.write(b"PING\n")
            next_ping_time = now + PING_INTERVAL_SECONDS

        line = read_device_line(connection)
        if not line:
            continue

        print(f"ESP32: {line}")
        if line == "READY":
            return

    raise RuntimeError(
        "The ESP32 did not become ready. Check the hotspot credentials, "
        "2.4 GHz compatibility setting, and serial port."
    )


def parse_data_line(line: str) -> dict[str, int]:
    fields = line.split(",")
    if len(fields) != 6 or fields[0] != "DATA":
        raise ValueError(f"Malformed data line: {line}")

    parsed = {
        "x_cm": int(fields[1]),
        "y_cm": int(fields[2]),
        "sample_index": int(fields[3]),
        "device_time_ms": int(fields[4]),
        "rssi_dbm": int(fields[5]),
    }
    if not 0 <= parsed["x_cm"] <= MAX_COORDINATE_CM or not 0 <= parsed["y_cm"] <= MAX_COORDINATE_CM:
        raise ValueError(f"DATA coordinates must be from 0 through {MAX_COORDINATE_CM} cm.")
    if parsed["sample_index"] < 0 or not 0 <= parsed["device_time_ms"] <= MAX_DEVICE_TIME_MS:
        raise ValueError("DATA sample index must be nonnegative and device time uint32.")
    if not -127 <= parsed["rssi_dbm"] <= 0:
        raise ValueError("DATA RSSI must be between -127 and 0 dBm.")
    return parsed


def device_time_advances(previous: int, current: int) -> bool:
    elapsed = (current - previous) & MAX_DEVICE_TIME_MS
    return 0 < elapsed < 2**31


def measure_point(
    connection: serial.Serial,
    x_cm: int,
    y_cm: int,
) -> list[dict[str, int | str]]:
    connection.reset_input_buffer()
    connection.write(f"MEASURE,{x_cm},{y_cm}\n".encode("ascii"))

    deadline = time.monotonic() + POINT_MEASUREMENT_TIMEOUT_SECONDS
    samples: list[dict[str, int | str]] = []
    expected_count: int | None = None
    previous_device_time_ms: int | None = None

    while time.monotonic() < deadline:
        line = read_device_line(connection)
        if not line:
            continue

        if line.startswith("START,"):
            fields = line.split(",")
            if len(fields) != 4:
                raise RuntimeError(f"Malformed start line: {line}")

            start_x = int(fields[1])
            start_y = int(fields[2])
            expected_count = int(fields[3])
            if (start_x, start_y) != (x_cm, y_cm):
                raise RuntimeError("The ESP32 acknowledged the wrong coordinate.")
            continue

        if line.startswith("DATA,"):
            if expected_count is None:
                raise RuntimeError("Data arrived before the measurement started.")
            sample = parse_data_line(line)
            if (sample["x_cm"], sample["y_cm"]) != (x_cm, y_cm):
                raise RuntimeError("The ESP32 returned data for the wrong coordinate.")
            if sample["sample_index"] != len(samples):
                raise RuntimeError(
                    "The ESP32 returned an out-of-order or duplicate sample index."
                )
            if (
                previous_device_time_ms is not None
                and not device_time_advances(
                    previous_device_time_ms, int(sample["device_time_ms"])
                )
            ):
                raise RuntimeError("ESP32 sample timestamps were not increasing.")
            previous_device_time_ms = sample["device_time_ms"]
            sample["host_time_utc"] = datetime.now(timezone.utc).isoformat()
            sample["host_monotonic_ns"] = time.monotonic_ns()
            samples.append(sample)
            continue

        if line.startswith("DONE,"):
            fields = line.split(",")
            if len(fields) != 4:
                raise RuntimeError(f"Malformed completion line: {line}")

            completed_x = int(fields[1])
            completed_y = int(fields[2])
            completed_count = int(fields[3])

            if (completed_x, completed_y) != (x_cm, y_cm):
                raise RuntimeError("The ESP32 completed the wrong coordinate.")

            if expected_count is None:
                raise RuntimeError("Completion arrived before the measurement started.")

            if completed_count != expected_count or len(samples) != expected_count:
                raise RuntimeError(
                    f"Expected {expected_count} samples but received {len(samples)}."
                )

            return samples

        if line.startswith("ERROR,"):
            raise RuntimeError(f"ESP32 reported {line}")

    raise RuntimeError(f"Measurement at ({x_cm}, {y_cm}) timed out.")


def validate_grid(width_cm: int, height_cm: int, spacing_cm: int) -> None:
    if max(width_cm, height_cm, spacing_cm) > MAX_COORDINATE_CM:
        raise ValueError(
            f"Survey dimensions and spacing cannot exceed {MAX_COORDINATE_CM} cm."
        )
    if width_cm % spacing_cm != 0 or height_cm % spacing_cm != 0:
        raise ValueError(
            "Width and height must each be exact multiples of the grid spacing."
        )


def generate_serpentine_grid(
    width_cm: int,
    height_cm: int,
    spacing_cm: int,
) -> list[tuple[int, int]]:
    x_values = list(range(0, width_cm + 1, spacing_cm))
    y_values = list(range(0, height_cm + 1, spacing_cm))
    points: list[tuple[int, int]] = []

    for row_index, y_cm in enumerate(y_values):
        row_x_values = x_values if row_index % 2 == 0 else reversed(x_values)
        points.extend((x_cm, y_cm) for x_cm in row_x_values)

    return points


def point_statistics(
    samples: list[dict[str, int | str]],
) -> tuple[float, float, float]:
    rssi_values = [int(sample["rssi_dbm"]) for sample in samples]
    median_rssi = float(statistics.median(rssi_values))
    mean_rssi = float(statistics.fmean(rssi_values))
    standard_deviation = (
        float(statistics.pstdev(rssi_values)) if len(rssi_values) > 1 else 0.0
    )
    return median_rssi, mean_rssi, standard_deviation


def load_grouped_samples(
    raw_csv_path: Path,
    ap_id: str | None = None,
) -> dict[tuple[float, float], list[float]]:
    dataset = load_survey_csv(raw_csv_path)
    available_ap_ids = sorted(
        {sample.ap_id for sample in dataset.samples if sample.ap_id is not None}
    )
    if ap_id is not None and not available_ap_ids:
        raise ValueError("--ap-id cannot be used with a legacy single-AP CSV.")
    if ap_id is None and len(available_ap_ids) > 1:
        raise ValueError(
            "This version 2 CSV contains multiple APs; select one with --ap-id. "
            f"Available IDs: {available_ap_ids}."
        )
    selected_ap_id = ap_id or (available_ap_ids[0] if available_ap_ids else None)
    if ap_id is not None and ap_id not in available_ap_ids:
        raise ValueError(
            f"AP {ap_id!r} is absent from the CSV; available IDs: {available_ap_ids}."
        )

    grouped: dict[tuple[float, float], list[float]] = defaultdict(list)
    for sample in dataset.samples:
        if sample.ap_id == selected_ap_id:
            grouped[(sample.x_cm, sample.y_cm)].append(sample.rssi_dbm)

    if not grouped:
        raise ValueError("The CSV file does not contain any samples.")

    return grouped


def coordinate_edges(values: np.ndarray) -> np.ndarray:
    if values.size == 1:
        return np.array(
            [
                values[0] - SINGLE_CELL_HALF_WIDTH_METERS,
                values[0] + SINGLE_CELL_HALF_WIDTH_METERS,
            ]
        )

    midpoints = (values[:-1] + values[1:]) / 2.0
    first_edge = values[0] - (midpoints[0] - values[0])
    last_edge = values[-1] + (values[-1] - midpoints[-1])
    return np.concatenate(([first_edge], midpoints, [last_edge]))


def derived_output_path(raw_csv_path: Path, output_prefix: str, suffix: str) -> Path:
    if raw_csv_path.stem.startswith("raw_samples"):
        stem = raw_csv_path.stem.replace("raw_samples", output_prefix, 1)
    else:
        stem = f"{raw_csv_path.stem}_{output_prefix}"
    return raw_csv_path.with_name(stem + suffix)


def write_summary_and_heatmap(
    raw_csv_path: Path,
    title: str,
    ap_x_cm: int | None,
    ap_y_cm: int | None,
    show_plot: bool,
    ap_id: str | None = None,
) -> tuple[Path, Path]:
    grouped = load_grouped_samples(raw_csv_path, ap_id)
    x_values_cm = sorted({coordinate[0] for coordinate in grouped})
    y_values_cm = sorted({coordinate[1] for coordinate in grouped})

    ap_suffix = (
        "" if ap_id is None else "_ap_" + hashlib.sha256(ap_id.encode()).hexdigest()[:8]
    )
    summary_path = derived_output_path(
        raw_csv_path, "point_summary" + ap_suffix, ".csv"
    )
    heatmap_path = derived_output_path(
        raw_csv_path, "rssi_heatmap" + ap_suffix, ".png"
    )

    x_indices = {value: index for index, value in enumerate(x_values_cm)}
    y_indices = {value: index for index, value in enumerate(y_values_cm)}
    median_grid = np.full((len(y_values_cm), len(x_values_cm)), np.nan)

    with summary_path.open("w", newline="", encoding="utf-8") as summary_file:
        fieldnames = [
            "x_cm",
            "y_cm",
            "sample_count",
            "median_rssi_dbm",
            "mean_rssi_dbm",
            "standard_deviation_db",
            "iqr_db",
        ]
        writer = csv.DictWriter(summary_file, fieldnames=fieldnames)
        writer.writeheader()

        for coordinate in sorted(grouped, key=lambda item: (item[1], item[0])):
            rssi_values = grouped[coordinate]
            median_rssi = float(statistics.median(rssi_values))
            mean_rssi = float(statistics.fmean(rssi_values))
            standard_deviation = (
                float(statistics.pstdev(rssi_values))
                if len(rssi_values) > 1
                else 0.0
            )
            first_quartile, third_quartile = np.percentile(
                np.asarray(rssi_values, dtype=float),
                [25, 75],
            )
            interquartile_range = float(third_quartile - first_quartile)

            writer.writerow(
                {
                    "x_cm": coordinate[0],
                    "y_cm": coordinate[1],
                    "sample_count": len(rssi_values),
                    "median_rssi_dbm": f"{median_rssi:.2f}",
                    "mean_rssi_dbm": f"{mean_rssi:.2f}",
                    "standard_deviation_db": f"{standard_deviation:.2f}",
                    "iqr_db": f"{interquartile_range:.2f}",
                }
            )

            median_grid[
                y_indices[coordinate[1]],
                x_indices[coordinate[0]],
            ] = median_rssi

    x_values_m = np.asarray(x_values_cm, dtype=float) / 100.0
    y_values_m = np.asarray(y_values_cm, dtype=float) / 100.0
    x_edges_m = coordinate_edges(x_values_m)
    y_edges_m = coordinate_edges(y_values_m)

    figure, axis = plt.subplots(figsize=(9, 7), constrained_layout=True)
    color_map = plt.get_cmap("turbo").with_extremes(bad="lightgray")

    image = axis.pcolormesh(
        x_edges_m,
        y_edges_m,
        np.ma.masked_invalid(median_grid),
        cmap=color_map,
        shading="flat",
    )

    if median_grid.size <= ANNOTATION_CELL_LIMIT:
        for y_index, y_value_m in enumerate(y_values_m):
            for x_index, x_value_m in enumerate(x_values_m):
                cell_value = median_grid[y_index, x_index]
                if np.isnan(cell_value):
                    continue
                axis.text(
                    x_value_m,
                    y_value_m,
                    f"{cell_value:.0f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    bbox={
                        "boxstyle": "round,pad=0.15",
                        "facecolor": "white",
                        "edgecolor": "none",
                        "alpha": 0.65,
                    },
                )

    if ap_x_cm is not None and ap_y_cm is not None:
        axis.scatter(
            [ap_x_cm / 100.0],
            [ap_y_cm / 100.0],
            marker="*",
            s=240,
            color="white",
            edgecolor="black",
            linewidth=1.2,
            label="Phone hotspot",
            zorder=3,
        )
        axis.legend(loc="best")

    axis.set_title(title)
    axis.set_xlabel("x position (m)")
    axis.set_ylabel("y position (m)")
    axis.set_aspect("equal", adjustable="box")
    axis.grid(color="black", alpha=0.15, linewidth=0.5)

    color_bar = figure.colorbar(image, ax=axis)
    color_bar.set_label("Median RSSI (dBm; less negative is stronger)")

    figure.savefig(heatmap_path, dpi=PLOT_DPI)
    if show_plot:
        plt.show()
    plt.close(figure)

    return summary_path, heatmap_path


def _load_acquisition_metadata_config(path: str | None) -> dict[str, Any]:
    if path is None:
        return {}
    config_path = Path(path)
    try:
        document = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid acquisition metadata JSON in {config_path}: {error.msg}."
        ) from error
    if not isinstance(document, dict):
        raise ValueError("Acquisition metadata config must be a JSON object.")
    allowed_sections = {
        "hardware",
        "channel",
        "pose",
        "environment",
        "measurement",
    }
    unsupported = sorted(set(document) - allowed_sections)
    if unsupported:
        raise ValueError(
            f"Unsupported acquisition metadata sections: {unsupported}; expected "
            f"only {sorted(allowed_sections)}."
        )
    if any(not isinstance(value, dict) for value in document.values()):
        raise ValueError("Every acquisition metadata section must be a JSON object.")
    validate_acquisition_metadata_fields(document)
    return document


def _rich_survey_enabled(arguments: argparse.Namespace) -> bool:
    new_pose_values = (
        arguments.ap_id,
        arguments.ap_z_cm,
        arguments.receiver_z_cm,
        arguments.yaw_deg,
        arguments.pitch_deg,
        arguments.roll_deg,
    )
    if not any(value is not None for value in new_pose_values):
        return False
    required = {
        "--ap-id": arguments.ap_id,
        "--ap-x-cm": arguments.ap_x_cm,
        "--ap-y-cm": arguments.ap_y_cm,
        "--ap-z-cm": arguments.ap_z_cm,
        "--receiver-z-cm": arguments.receiver_z_cm,
        "--yaw-deg": arguments.yaw_deg,
        "--pitch-deg": arguments.pitch_deg,
        "--roll-deg": arguments.roll_deg,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError(
            "Version 2 survey rows require complete AP and receiver pose metadata; "
            f"missing {', '.join(missing)}."
        )
    return True


def _write_survey_metadata(
    *,
    path: Path,
    raw_csv_path: Path,
    arguments: argparse.Namespace,
    config: dict[str, Any],
    run_uuid: str,
    started_utc: str,
    finished_utc: str,
    rich_schema: bool,
    completed_measurements: int,
    received_samples: int,
) -> None:
    expected_samples = completed_measurements * SAMPLES_PER_POINT
    transmitter: dict[str, Any] = {
        "ap_id": arguments.ap_id,
        "position_cm": {
            "x": arguments.ap_x_cm,
            "y": arguments.ap_y_cm,
            "z": arguments.ap_z_cm,
        },
    }
    calibration: dict[str, Any] = {"file": None, "version": None, "sha256": None}
    if arguments.calibration_file:
        calibration_path = Path(arguments.calibration_file)
        calibration_bytes = calibration_path.read_bytes()
        calibration_document = json.loads(calibration_bytes)
        calibration = {
            "file": str(calibration_path),
            "version": calibration_document.get("schema_version"),
            "sha256": hashlib.sha256(calibration_bytes).hexdigest(),
        }
    pose_config = dict(config.get("pose", {}))
    pose_config.update(
        {
            "source": arguments.pose_source,
            "receiver_z_cm": arguments.receiver_z_cm,
            "yaw_deg": arguments.yaw_deg,
            "pitch_deg": arguments.pitch_deg,
            "roll_deg": arguments.roll_deg,
            "orientation_convention": (
                "right-handed yaw about +z, pitch about +y, roll about +x"
                if rich_schema
                else None
            ),
        }
    )
    document = {
        "schema_version": "2.0",
        "run_uuid": run_uuid,
        "units": {
            "position": "cm",
            "orientation": "deg",
            "rssi": "dbm",
            "device_time": "ms",
            "host_monotonic": "ns",
        },
        "run": {
            "host_started_utc": started_utc,
            "host_finished_utc": finished_utc,
            "trial_label": config.get("environment", {}).get("trial_label"),
            "environment_label": config.get("environment", {}).get(
                "environment_label"
            ),
            "notes": config.get("environment", {}).get("notes"),
        },
        "data": {
            "csv_file": raw_csv_path.name,
            "csv_schema": "2.0" if rich_schema else "legacy-1",
            "csv_sha256": hashlib.sha256(raw_csv_path.read_bytes()).hexdigest(),
            "received_sample_count": received_samples,
            "expected_sample_count_for_completed_points": expected_samples,
            "packet_loss_count": expected_samples - received_samples,
            "csi_available": False,
            "noise_floor_available": False,
        },
        "measurement": {
            **config.get("measurement", {}),
            "samples_per_point": SAMPLES_PER_POINT,
            "nominal_sample_rate_hz": 10.0,
            "nominal_dwell_time_s": 5.0,
        },
        "pose": pose_config,
        "transmitters": [transmitter] if arguments.ap_id is not None else [],
        "hardware": dict(config.get("hardware", {})),
        "channel": dict(config.get("channel", {})),
        "calibration": calibration,
    }
    validate_survey_metadata_document(document, path)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_survey(arguments: argparse.Namespace) -> int:
    validate_grid(arguments.width_cm, arguments.height_cm, arguments.spacing_cm)
    points = generate_serpentine_grid(
        arguments.width_cm,
        arguments.height_cm,
        arguments.spacing_cm,
    )

    output_directory = Path(arguments.output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    raw_csv_path = output_directory / f"raw_samples_{timestamp}.csv"
    metadata_path = output_directory / f"survey_metadata_{timestamp}.json"
    metadata_config = _load_acquisition_metadata_config(arguments.metadata_config)
    rich_schema = _rich_survey_enabled(arguments)
    if arguments.calibration_file:
        from rf_mapping.calibration import load_calibration

        load_calibration(arguments.calibration_file)
    output_header = RICH_RAW_HEADER if rich_schema else RAW_HEADER
    run_uuid = str(uuid.uuid4())
    started_utc = datetime.now(timezone.utc).isoformat()
    selected_port = select_serial_port(arguments.port)

    print(f"Opening {selected_port} at {SERIAL_BAUD} baud.")
    print("Close Arduino Serial Monitor before continuing.")

    stop_requested = False

    with serial.Serial(
        selected_port,
        SERIAL_BAUD,
        timeout=SERIAL_READ_TIMEOUT_SECONDS,
    ) as connection, raw_csv_path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as raw_file:
        time.sleep(DEVICE_RESET_DELAY_SECONDS)
        connection.reset_input_buffer()
        wait_for_device(connection)

        writer = csv.DictWriter(raw_file, fieldnames=output_header)
        writer.writeheader()
        raw_file.flush()

        total_measurements = len(points) * arguments.passes
        completed_measurements = 0
        packet_sequence = 0
        received_samples = 0

        for pass_index in range(1, arguments.passes + 1):
            print(f"\nStarting pass {pass_index} of {arguments.passes}.")

            pass_points = points if pass_index % 2 == 1 else list(reversed(points))
            for x_cm, y_cm in pass_points:
                prompt = (
                    f"Move the ESP32 to ({x_cm}, {y_cm}) cm "
                    "and press Enter [s=skip, q=finish]: "
                )
                response = input(prompt).strip().lower()

                if response == "q":
                    stop_requested = True
                    break

                if response == "s":
                    print("Point skipped.")
                    continue

                samples = measure_point(connection, x_cm, y_cm)
                for sample in samples:
                    row: dict[str, Any] = {"pass_index": pass_index, **sample}
                    if rich_schema:
                        row.update(
                            {
                                "packet_sequence": packet_sequence,
                                "ap_id": arguments.ap_id,
                                "z_cm": arguments.receiver_z_cm,
                                "yaw_deg": arguments.yaw_deg,
                                "pitch_deg": arguments.pitch_deg,
                                "roll_deg": arguments.roll_deg,
                            }
                        )
                    writer.writerow({field: row[field] for field in output_header})
                    packet_sequence += 1
                    received_samples += 1
                raw_file.flush()

                median_rssi, mean_rssi, standard_deviation = point_statistics(samples)
                completed_measurements += 1
                print(
                    f"Saved {len(samples)} samples: median={median_rssi:.1f} dBm, "
                    f"mean={mean_rssi:.1f} dBm, stddev={standard_deviation:.2f} dB "
                    f"[{completed_measurements}/{total_measurements}]"
                )

            if stop_requested:
                break

    if completed_measurements == 0:
        print(f"No measurements were saved. Empty file: {raw_csv_path}")
        return 1

    _write_survey_metadata(
        path=metadata_path,
        raw_csv_path=raw_csv_path,
        arguments=arguments,
        config=metadata_config,
        run_uuid=run_uuid,
        started_utc=started_utc,
        finished_utc=datetime.now(timezone.utc).isoformat(),
        rich_schema=rich_schema,
        completed_measurements=completed_measurements,
        received_samples=received_samples,
    )

    summary_path, heatmap_path = write_summary_and_heatmap(
        raw_csv_path,
        arguments.title,
        arguments.ap_x_cm,
        arguments.ap_y_cm,
        arguments.show,
        arguments.ap_id,
    )

    print(f"\nRaw samples: {raw_csv_path.resolve()}")
    print(f"Survey metadata: {metadata_path.resolve()}")
    print(f"Point summary: {summary_path.resolve()}")
    print(f"Heatmap: {heatmap_path.resolve()}")
    return 0


def run_plot(arguments: argparse.Namespace) -> int:
    raw_csv_path = Path(arguments.raw_csv)
    if not raw_csv_path.is_file():
        raise FileNotFoundError(raw_csv_path)

    summary_path, heatmap_path = write_summary_and_heatmap(
        raw_csv_path,
        arguments.title,
        arguments.ap_x_cm,
        arguments.ap_y_cm,
        arguments.show,
        arguments.ap_id,
    )
    print(f"Point summary: {summary_path.resolve()}")
    print(f"Heatmap: {heatmap_path.resolve()}")
    return 0


def run_calibrate(arguments: argparse.Namespace) -> int:
    from rf_mapping.calibration import (
        fit_log_distance_calibration,
        load_calibration_csv,
        save_calibration,
    )

    input_path = Path(arguments.calibration_csv)
    output_path = Path(arguments.output)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Calibration output must not overwrite the source CSV.")
    dataset = load_calibration_csv(input_path)
    result = fit_log_distance_calibration(
        dataset,
        reference_distance_m=arguments.reference_distance_m,
        huber_delta=arguments.huber_delta,
        maximum_iterations=arguments.max_iterations,
        tolerance=arguments.tolerance,
    )
    if not result.converged:
        raise RuntimeError(
            "Calibration did not meet the convergence tolerance; increase "
            "--max-iterations or inspect the sweep before saving a model."
        )
    if output_path.exists() and not arguments.overwrite:
        raise FileExistsError(
            f"Refusing to overwrite {output_path}; use --overwrite or another --output."
        )
    save_calibration(result, output_path)
    print(f"Calibration: {output_path.resolve()}")
    print(
        f"P0={result.p0_dbm:.3f} dBm at {result.reference_distance_m:.3f} m, "
        f"n={result.path_loss_exponent:.4f}, residual sigma={result.residual_sigma_db:.3f} dB"
    )
    print(
        f"Huber IRLS converged={result.converged} in {result.iterations} iterations; "
        f"down-weighted {result.downweighted_count}/{result.sample_count} samples."
    )
    return 0


def run_infer(arguments: argparse.Namespace) -> int:
    from rf_mapping.inference import InferenceConfig, run_offline_inference

    config = InferenceConfig(
        grid_resolution_m=arguments.grid_resolution_cm / 100.0,
        kernel_length_scale_m=arguments.kernel_length_scale_cm / 100.0,
        gp_signal_std_db=arguments.gp_signal_std_db,
        gp_noise_floor_db=arguments.gp_noise_floor_db,
        lambda_l1=arguments.lambda_l1,
        lambda_tv=arguments.lambda_tv,
        tv_epsilon=arguments.tv_epsilon,
        optimizer_max_iterations=arguments.max_iterations,
        optimizer_relative_tolerance=arguments.tolerance,
        bootstrap_count=arguments.bootstrap_samples,
        attenuation_threshold_db_per_m=arguments.attenuation_threshold_db_per_m,
        evidence_threshold=arguments.evidence_threshold,
        minimum_component_cells=arguments.minimum_component_cells,
        receiver_clearance_radius_m=arguments.receiver_clearance_cm / 100.0,
        seed=arguments.seed,
        min_links=arguments.min_links,
        min_transmitters=arguments.min_transmitters,
        min_angle_bins=arguments.min_angle_bins,
        angle_bin_count=arguments.angle_bins,
        max_receiver_distance_m=arguments.max_receiver_distance_cm / 100.0,
        min_sensitivity=arguments.min_sensitivity,
        min_conditioning_score=arguments.min_conditioning,
        min_pass_consistency=arguments.min_pass_consistency,
        min_repeated_links=arguments.min_repeated_links,
    )
    artifacts = run_offline_inference(
        arguments.raw_csv,
        metadata_paths=arguments.metadata or (),
        calibration_paths=arguments.calibration or (),
        output_directory=arguments.output_dir,
        field_ap_id=arguments.field_ap_id,
        config=config,
        allow_shared_calibration=arguments.allow_shared_calibration,
        overwrite=arguments.overwrite,
        show=arguments.show,
    )
    print(f"Inference status: {artifacts.status}")
    print(f"Potential attenuation components: {artifacts.component_count}")
    if artifacts.component_count == 0:
        print("Supported conclusion: no obstacle polygon or dimensions can be claimed.")
    else:
        print(
            "Supported conclusion: experimental potential attenuation-causing "
            "components passed the configured observability gate; they are not "
            "collision-safe geometry."
        )
    print(f"Figure: {artifacts.figure_path.resolve()}")
    print(f"Grid arrays: {artifacts.arrays_path.resolve()}")
    print(f"Report: {artifacts.report_path.resolve()}")
    for warning in artifacts.warnings:
        print(f"Warning: {warning}")
    return 0


def run_simulate(arguments: argparse.Namespace) -> int:
    from rf_mapping.simulation import SimulationConfig, generate_synthetic_dataset

    config = SimulationConfig(
        scene=arguments.scene,
        link_geometry=arguments.geometry,
        seed=arguments.seed,
        grid_resolution_m=arguments.grid_resolution_cm / 100.0,
        receiver_spacing_m=arguments.receiver_spacing_cm / 100.0,
        bootstrap_count=arguments.bootstrap_samples,
        optimizer_max_iterations=arguments.max_iterations,
    )
    artifacts = generate_synthetic_dataset(
        arguments.output,
        config,
        overwrite=arguments.overwrite,
    )
    metrics = artifacts.validation.metrics
    print(f"Synthetic status: {artifacts.validation.status}")
    print(
        f"IoU={metrics['iou']:.3f}, precision={metrics['precision']:.3f}, "
        f"recall={metrics['recall']:.3f}, attenuation RMSE="
        f"{metrics['attenuation_rmse_db_per_m']:.3f} dB/m"
    )
    print(f"Survey CSV: {artifacts.survey_csv.resolve()}")
    print(f"Metadata: {artifacts.metadata_json.resolve()}")
    print(f"Calibration: {artifacts.calibration_json.resolve()}")
    print(f"Ground truth: {artifacts.ground_truth_npz.resolve()}")
    print(f"Validation report: {artifacts.validation_json.resolve()}")
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect ESP32 RSSI measurements and run offline probabilistic "
            "RF-assisted mapping."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    survey_parser = subparsers.add_parser(
        "survey",
        help="Collect a new survey over the serial connection.",
    )
    survey_parser.add_argument("--port", help="ESP32 serial port, such as COM5.")
    survey_parser.add_argument(
        "--width-cm",
        required=True,
        type=positive_integer,
        help="Survey width in centimeters.",
    )
    survey_parser.add_argument(
        "--height-cm",
        required=True,
        type=positive_integer,
        help="Survey height in centimeters.",
    )
    survey_parser.add_argument(
        "--spacing-cm",
        required=True,
        type=positive_integer,
        help="Distance between measurement points in centimeters.",
    )
    survey_parser.add_argument(
        "--passes",
        type=positive_integer,
        default=1,
        help="Number of times to repeat the full grid.",
    )
    survey_parser.add_argument(
        "--output-dir",
        default="survey_output",
        help="Directory for CSV and PNG output.",
    )
    survey_parser.add_argument(
        "--title",
        default="Measured RSSI",
        help="Heatmap title.",
    )
    survey_parser.add_argument(
        "--ap-x-cm",
        type=nonnegative_integer,
        help="Optional phone hotspot x coordinate in centimeters.",
    )
    survey_parser.add_argument(
        "--ap-y-cm",
        type=nonnegative_integer,
        help="Optional phone hotspot y coordinate in centimeters.",
    )
    survey_parser.add_argument(
        "--ap-id",
        help="Privacy-preserving stable AP identifier (never an SSID or password).",
    )
    survey_parser.add_argument(
        "--ap-z-cm",
        type=bounded_float(0.0, 10_000_000.0),
        help="AP height in centimeters for version 2 survey metadata.",
    )
    survey_parser.add_argument(
        "--receiver-z-cm",
        type=bounded_float(0.0, 10_000_000.0),
        help="Fixed receiver height in centimeters for version 2 rows.",
    )
    survey_parser.add_argument(
        "--yaw-deg",
        type=bounded_float(-180.0, 180.0),
        help="Fixed receiver yaw in degrees.",
    )
    survey_parser.add_argument(
        "--pitch-deg",
        type=bounded_float(-90.0, 90.0),
        help="Fixed receiver pitch in degrees.",
    )
    survey_parser.add_argument(
        "--roll-deg",
        type=bounded_float(-180.0, 180.0),
        help="Fixed receiver roll in degrees.",
    )
    survey_parser.add_argument(
        "--pose-source",
        default="manual",
        help="Pose source recorded in metadata, such as manual or VIO.",
    )
    survey_parser.add_argument(
        "--metadata-config",
        help="Optional hardware/channel/environment acquisition JSON.",
    )
    survey_parser.add_argument(
        "--calibration-file",
        help="Optional calibration artifact to hash and reference in metadata.",
    )
    survey_parser.add_argument(
        "--show",
        action="store_true",
        help="Open the heatmap window after saving it.",
    )
    survey_parser.set_defaults(function=run_survey)

    plot_parser = subparsers.add_parser(
        "plot",
        help="Rebuild a summary and heatmap from an existing raw CSV file.",
    )
    plot_parser.add_argument("raw_csv", help="Path to raw_samples_*.csv.")
    plot_parser.add_argument(
        "--title",
        default="Measured RSSI",
        help="Heatmap title.",
    )
    plot_parser.add_argument(
        "--ap-x-cm",
        type=nonnegative_integer,
        help="Optional phone hotspot x coordinate in centimeters.",
    )
    plot_parser.add_argument(
        "--ap-y-cm",
        type=nonnegative_integer,
        help="Optional phone hotspot y coordinate in centimeters.",
    )
    plot_parser.add_argument(
        "--ap-id",
        help="AP ID to plot when a version 2 CSV contains more than one AP.",
    )
    plot_parser.add_argument(
        "--show",
        action="store_true",
        help="Open the heatmap window after saving it.",
    )
    plot_parser.set_defaults(function=run_plot)

    calibration_parser = subparsers.add_parser(
        "calibrate",
        help="Fit a robust open-space log-distance calibration.",
    )
    calibration_parser.add_argument(
        "calibration_csv", help="CSV beginning distance_m,rssi_dbm,pass_index."
    )
    calibration_parser.add_argument(
        "--output", required=True, help="Calibration JSON output path."
    )
    calibration_parser.add_argument(
        "--reference-distance-m",
        type=positive_float,
        default=1.0,
        help="Reference distance d0 in metres (default: 1).",
    )
    calibration_parser.add_argument(
        "--huber-delta",
        type=positive_float,
        default=1.345,
        help="Huber IRLS standardized residual cutoff (default: 1.345).",
    )
    calibration_parser.add_argument(
        "--max-iterations", type=positive_integer, default=100
    )
    calibration_parser.add_argument(
        "--tolerance", type=positive_float, default=1e-10
    )
    calibration_parser.add_argument("--overwrite", action="store_true")
    calibration_parser.set_defaults(function=run_calibrate)

    infer_parser = subparsers.add_parser(
        "infer",
        help="Estimate an RF field and gated experimental attenuation evidence.",
    )
    infer_parser.add_argument(
        "raw_csv", nargs="+", help="One or more legacy or version 2 survey CSV files."
    )
    infer_parser.add_argument(
        "--metadata",
        action="append",
        help="Metadata JSON, repeated once per survey CSV in the same order.",
    )
    infer_parser.add_argument(
        "--calibration",
        action="append",
        help="Calibration JSON; repeat for separately calibrated APs.",
    )
    infer_parser.add_argument("--field-ap-id", help="AP ID for the RF field panel.")
    infer_parser.add_argument("--output-dir", default="inference_output")
    infer_parser.add_argument(
        "--grid-resolution-cm", type=positive_float, default=10.0
    )
    infer_parser.add_argument(
        "--kernel-length-scale-cm", type=positive_float, default=50.0
    )
    infer_parser.add_argument("--gp-signal-std-db", type=positive_float, default=6.0)
    infer_parser.add_argument("--gp-noise-floor-db", type=positive_float, default=1.0)
    infer_parser.add_argument("--lambda-l1", type=nonnegative_float, default=0.2)
    infer_parser.add_argument("--lambda-tv", type=nonnegative_float, default=0.5)
    infer_parser.add_argument("--tv-epsilon", type=positive_float, default=0.05)
    infer_parser.add_argument("--max-iterations", type=positive_integer, default=600)
    infer_parser.add_argument("--tolerance", type=positive_float, default=1e-5)
    infer_parser.add_argument(
        "--bootstrap-samples", type=positive_integer, default=20
    )
    infer_parser.add_argument(
        "--attenuation-threshold-db-per-m", type=positive_float, default=2.0
    )
    infer_parser.add_argument(
        "--evidence-threshold", type=bounded_float(0.0, 1.0), default=0.7
    )
    infer_parser.add_argument(
        "--minimum-component-cells", type=positive_integer, default=2
    )
    infer_parser.add_argument(
        "--receiver-clearance-cm", type=nonnegative_float, default=0.0
    )
    infer_parser.add_argument("--seed", type=nonnegative_integer, default=0)
    infer_parser.add_argument("--min-links", type=positive_integer, default=4)
    infer_parser.add_argument("--min-transmitters", type=positive_integer, default=2)
    infer_parser.add_argument("--min-angle-bins", type=positive_integer, default=2)
    infer_parser.add_argument("--angle-bins", type=positive_integer, default=12)
    infer_parser.add_argument(
        "--max-receiver-distance-cm", type=positive_float, default=100.0
    )
    infer_parser.add_argument(
        "--min-sensitivity", type=nonnegative_float, default=0.5
    )
    infer_parser.add_argument(
        "--min-conditioning", type=bounded_float(0.0, 1.0), default=0.1
    )
    infer_parser.add_argument(
        "--min-pass-consistency", type=bounded_float(0.0, 1.0), default=0.5
    )
    infer_parser.add_argument(
        "--min-repeated-links", type=positive_integer, default=3
    )
    infer_parser.add_argument(
        "--allow-shared-calibration",
        action="store_true",
        help="Explicitly reuse one calibration for multiple APs.",
    )
    infer_parser.add_argument("--overwrite", action="store_true")
    infer_parser.add_argument("--show", action="store_true")
    infer_parser.set_defaults(function=run_infer)

    simulate_parser = subparsers.add_parser(
        "simulate", help="Generate and validate deterministic synthetic RF data."
    )
    simulate_parser.add_argument(
        "--scene", choices=("empty", "one-rectangle"), default="one-rectangle"
    )
    simulate_parser.add_argument(
        "--geometry", choices=("single-ap", "crossing"), default="crossing"
    )
    simulate_parser.add_argument("--seed", type=nonnegative_integer, default=0)
    simulate_parser.add_argument("--output", default="synthetic_output")
    simulate_parser.add_argument(
        "--grid-resolution-cm", type=positive_float, default=25.0
    )
    simulate_parser.add_argument(
        "--receiver-spacing-cm", type=positive_float, default=50.0
    )
    simulate_parser.add_argument(
        "--bootstrap-samples", type=positive_integer, default=8
    )
    simulate_parser.add_argument(
        "--max-iterations", type=positive_integer, default=1000
    )
    simulate_parser.add_argument("--overwrite", action="store_true")
    simulate_parser.set_defaults(function=run_simulate)

    return parser


def main() -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args()

    if arguments.command in {"survey", "plot"} and (
        (arguments.ap_x_cm is None) != (arguments.ap_y_cm is None)
    ):
        parser.error("--ap-x-cm and --ap-y-cm must be supplied together.")

    try:
        return arguments.function(arguments)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
