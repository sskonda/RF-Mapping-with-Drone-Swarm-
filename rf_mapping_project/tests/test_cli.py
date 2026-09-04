from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from rf_mapper import (
    _load_acquisition_metadata_config,
    _rich_survey_enabled,
    _write_survey_metadata,
    build_argument_parser,
    run_calibrate,
)


class CommandLineTests(unittest.TestCase):
    def test_documented_acquisition_metadata_config_is_accepted(self) -> None:
        example_path = (
            Path(__file__).resolve().parents[1]
            / "examples/acquisition_metadata.example.json"
        )
        config = _load_acquisition_metadata_config(str(example_path))
        self.assertEqual(config["hardware"]["antenna_type"], "pcb_trace")

    def test_invalid_acquisition_metadata_is_rejected_before_collection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "metadata.json"
            path.write_text('{"channel": {"channel": 0}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "channel.channel"):
                _load_acquisition_metadata_config(str(path))

    def test_simulation_default_has_verified_optimizer_budget(self) -> None:
        arguments = build_argument_parser().parse_args(["simulate"])
        self.assertEqual(arguments.max_iterations, 1000)

    def test_calibration_never_overwrites_source_or_saves_unconverged_fit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "calibration.csv"
            source.write_text(
                "distance_m,rssi_dbm,pass_index\n"
                "0.5,-31,1\n1,-38,1\n2,-45,1\n4,-52,1\n8,-79,1\n",
                encoding="utf-8",
            )
            parser = build_argument_parser()
            same_path = parser.parse_args(
                ["calibrate", str(source), "--output", str(source), "--overwrite"]
            )
            with self.assertRaisesRegex(ValueError, "must not overwrite"):
                run_calibrate(same_path)

            output = root / "calibration.json"
            unconverged = parser.parse_args(
                [
                    "calibrate",
                    str(source),
                    "--output",
                    str(output),
                    "--max-iterations",
                    "1",
                    "--tolerance",
                    "1e-15",
                ]
            )
            with self.assertRaisesRegex(RuntimeError, "did not meet"):
                run_calibrate(unconverged)
            self.assertFalse(output.exists())

    def test_generated_metadata_keeps_canonical_sampling_facts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            raw_csv = root / "raw.csv"
            raw_csv.write_text(
                "pass_index,x_cm,y_cm,sample_index,device_time_ms,rssi_dbm\n"
                "1,0,0,0,100,-50\n",
                encoding="utf-8",
            )
            metadata_path = root / "metadata.json"
            arguments = Namespace(
                ap_id=None,
                ap_x_cm=None,
                ap_y_cm=None,
                ap_z_cm=None,
                receiver_z_cm=None,
                yaw_deg=None,
                pitch_deg=None,
                roll_deg=None,
                pose_source="manual",
                calibration_file=None,
            )
            _write_survey_metadata(
                path=metadata_path,
                raw_csv_path=raw_csv,
                arguments=arguments,
                config={
                    "measurement": {
                        "samples_per_point": 999,
                        "nominal_sample_rate_hz": 999,
                        "operator_note": "fixed orientation",
                    }
                },
                run_uuid="8c1441be-6a2c-4f9d-8592-271be906b6a5",
                started_utc="2026-09-03T12:00:00+00:00",
                finished_utc="2026-09-03T12:01:00+00:00",
                rich_schema=False,
                completed_measurements=1,
                received_samples=1,
            )
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertEqual(metadata["measurement"]["samples_per_point"], 50)
        self.assertEqual(metadata["measurement"]["nominal_sample_rate_hz"], 10.0)
        self.assertEqual(metadata["measurement"]["operator_note"], "fixed orientation")
        self.assertEqual(metadata["transmitters"], [])

    def test_generated_metadata_is_validated_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            raw_csv = root / "raw.csv"
            raw_csv.write_text(
                "pass_index,x_cm,y_cm,sample_index,device_time_ms,rssi_dbm\n"
                "1,0,0,0,100,-50\n",
                encoding="utf-8",
            )
            metadata_path = root / "metadata.json"
            arguments = Namespace(
                ap_id=None,
                ap_x_cm=None,
                ap_y_cm=None,
                ap_z_cm=None,
                receiver_z_cm=None,
                yaw_deg=None,
                pitch_deg=None,
                roll_deg=None,
                pose_source="manual",
                calibration_file=None,
            )
            with self.assertRaisesRegex(ValueError, "channel.channel"):
                _write_survey_metadata(
                    path=metadata_path,
                    raw_csv_path=raw_csv,
                    arguments=arguments,
                    config={"channel": {"channel": 0}},
                    run_uuid="8c1441be-6a2c-4f9d-8592-271be906b6a5",
                    started_utc="2026-09-03T12:00:00+00:00",
                    finished_utc="2026-09-03T12:01:00+00:00",
                    rich_schema=False,
                    completed_measurements=1,
                    received_samples=1,
                )
            self.assertFalse(metadata_path.exists())

    def test_partial_version_two_pose_is_rejected(self) -> None:
        arguments = Namespace(
            ap_id="ap-a",
            ap_x_cm=0,
            ap_y_cm=0,
            ap_z_cm=None,
            receiver_z_cm=100,
            yaw_deg=0,
            pitch_deg=0,
            roll_deg=0,
        )
        with self.assertRaisesRegex(ValueError, "--ap-z-cm"):
            _rich_survey_enabled(arguments)


if __name__ == "__main__":
    unittest.main()
