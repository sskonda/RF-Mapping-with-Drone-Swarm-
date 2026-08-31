from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import serial
from serial.tools import list_ports


SERIAL_BAUD = 115200
SERIAL_READ_TIMEOUT_SECONDS = 0.25
DEVICE_READY_TIMEOUT_SECONDS = 45.0
POINT_MEASUREMENT_TIMEOUT_SECONDS = 20.0
PING_INTERVAL_SECONDS = 1.0
DEVICE_RESET_DELAY_SECONDS = 2.0
ANNOTATION_CELL_LIMIT = 100
PLOT_DPI = 180
SINGLE_CELL_HALF_WIDTH_METERS = 0.25

RAW_HEADER = [
    "pass_index",
    "x_cm",
    "y_cm",
    "sample_index",
    "device_time_ms",
    "rssi_dbm",
]


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

    return {
        "x_cm": int(fields[1]),
        "y_cm": int(fields[2]),
        "sample_index": int(fields[3]),
        "device_time_ms": int(fields[4]),
        "rssi_dbm": int(fields[5]),
    }


def measure_point(
    connection: serial.Serial,
    x_cm: int,
    y_cm: int,
) -> list[dict[str, int]]:
    connection.reset_input_buffer()
    connection.write(f"MEASURE,{x_cm},{y_cm}\n".encode("ascii"))

    deadline = time.monotonic() + POINT_MEASUREMENT_TIMEOUT_SECONDS
    samples: list[dict[str, int]] = []
    expected_count: int | None = None

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
            sample = parse_data_line(line)
            if (sample["x_cm"], sample["y_cm"]) != (x_cm, y_cm):
                raise RuntimeError("The ESP32 returned data for the wrong coordinate.")
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


def point_statistics(samples: list[dict[str, int]]) -> tuple[float, float, float]:
    rssi_values = [sample["rssi_dbm"] for sample in samples]
    median_rssi = float(statistics.median(rssi_values))
    mean_rssi = float(statistics.fmean(rssi_values))
    standard_deviation = (
        float(statistics.pstdev(rssi_values)) if len(rssi_values) > 1 else 0.0
    )
    return median_rssi, mean_rssi, standard_deviation


def load_grouped_samples(raw_csv_path: Path) -> dict[tuple[int, int], list[int]]:
    grouped: dict[tuple[int, int], list[int]] = defaultdict(list)

    with raw_csv_path.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames != RAW_HEADER:
            raise ValueError(
                f"Unexpected CSV header in {raw_csv_path}. Expected {RAW_HEADER}."
            )

        for row in reader:
            coordinate = (int(row["x_cm"]), int(row["y_cm"]))
            grouped[coordinate].append(int(row["rssi_dbm"]))

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


def write_summary_and_heatmap(
    raw_csv_path: Path,
    title: str,
    ap_x_cm: int | None,
    ap_y_cm: int | None,
    show_plot: bool,
) -> tuple[Path, Path]:
    grouped = load_grouped_samples(raw_csv_path)
    x_values_cm = sorted({coordinate[0] for coordinate in grouped})
    y_values_cm = sorted({coordinate[1] for coordinate in grouped})

    summary_path = raw_csv_path.with_name(
        raw_csv_path.stem.replace("raw_samples", "point_summary") + ".csv"
    )
    heatmap_path = raw_csv_path.with_name(
        raw_csv_path.stem.replace("raw_samples", "rssi_heatmap") + ".png"
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
    color_map = plt.get_cmap("turbo").copy()
    color_map.set_bad("lightgray")

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


def run_survey(arguments: argparse.Namespace) -> int:
    validate_grid(arguments.width_cm, arguments.height_cm, arguments.spacing_cm)
    points = generate_serpentine_grid(
        arguments.width_cm,
        arguments.height_cm,
        arguments.spacing_cm,
    )

    output_directory = Path(arguments.output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_csv_path = output_directory / f"raw_samples_{timestamp}.csv"
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

        writer = csv.DictWriter(raw_file, fieldnames=RAW_HEADER)
        writer.writeheader()
        raw_file.flush()

        total_measurements = len(points) * arguments.passes
        completed_measurements = 0

        for pass_index in range(1, arguments.passes + 1):
            print(f"\nStarting pass {pass_index} of {arguments.passes}.")

            for x_cm, y_cm in points:
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
                    writer.writerow(
                        {
                            "pass_index": pass_index,
                            **sample,
                        }
                    )
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

    summary_path, heatmap_path = write_summary_and_heatmap(
        raw_csv_path,
        arguments.title,
        arguments.ap_x_cm,
        arguments.ap_y_cm,
        arguments.show,
    )

    print(f"\nRaw samples: {raw_csv_path.resolve()}")
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
    )
    print(f"Point summary: {summary_path.resolve()}")
    print(f"Heatmap: {heatmap_path.resolve()}")
    return 0


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect ESP32 hotspot RSSI measurements and create a 2D heatmap."
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
        default="ESP32 2.4 GHz RSSI Heatmap",
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
        default="ESP32 2.4 GHz RSSI Heatmap",
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
        "--show",
        action="store_true",
        help="Open the heatmap window after saving it.",
    )
    plot_parser.set_defaults(function=run_plot)

    return parser


def main() -> int:
    parser = build_argument_parser()
    arguments = parser.parse_args()

    if (arguments.ap_x_cm is None) != (arguments.ap_y_cm is None):
        parser.error("--ap-x-cm and --ap-y-cm must be supplied together.")

    try:
        return arguments.function(arguments)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
