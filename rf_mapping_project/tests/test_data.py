from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
import uuid
import warnings
from pathlib import Path

from rf_mapping.data import (
    LEGACY_CSV_FIELDS,
    V2_CSV_FIELDS,
    MetadataUnavailableWarning,
    SurveySample,
    compute_inference_aggregates,
    compute_location_statistics,
    load_survey_csv,
    load_survey_metadata,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKED_IN_SURVEY = REPOSITORY_ROOT / "survey_output/raw_samples_20260831_184759.csv"


class SurveyDataTests(unittest.TestCase):
    def test_checked_in_legacy_statistics_match_existing_plot_exactly(self) -> None:
        expected = {
            (0, 0): (-25.0, -25.22, 1.19, 1.00),
            (50, 0): (-40.0, -40.00, 0.94, 1.75),
            (100, 0): (-48.0, -47.64, 1.11, 1.00),
            (0, 50): (-38.0, -38.02, 1.24, 2.00),
            (50, 50): (-48.0, -48.18, 1.86, 1.00),
            (100, 50): (-41.0, -41.48, 0.83, 1.00),
            (0, 100): (-46.5, -46.34, 3.77, 5.75),
            (50, 100): (-48.0, -48.46, 1.42, 1.75),
            (100, 100): (-56.0, -56.32, 1.76, 3.00),
        }
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            dataset = load_survey_csv(CHECKED_IN_SURVEY)

        self.assertEqual(dataset.schema_version, "legacy-1")
        self.assertEqual(len(dataset.samples), 450)
        self.assertTrue(
            any(issubclass(item.category, MetadataUnavailableWarning) for item in caught)
        )
        summaries = compute_location_statistics(dataset)
        self.assertEqual(set(summaries), set(expected))
        for coordinate, expected_values in expected.items():
            summary = summaries[coordinate].raw
            self.assertEqual(summary.sample_count, 50)
            actual = (
                summary.median_rssi_dbm,
                summary.mean_rssi_dbm,
                round(summary.standard_deviation_db, 2),
                summary.iqr_db,
            )
            self.assertEqual(actual, expected_values)

    def test_strict_numeric_and_sequence_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            malformed_path = temporary_path / "malformed.csv"
            malformed_path.write_text(
                ",".join(LEGACY_CSV_FIELDS)
                + "\n1,0,0,0,100,not-a-number\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "rssi_dbm.*row 2"):
                load_survey_csv(malformed_path)

            bad_sequence_path = temporary_path / "bad_sequence.csv"
            bad_sequence_path.write_text(
                ",".join(LEGACY_CSV_FIELDS)
                + "\n1,0,0,0,100,-50\n1,0,0,2,200,-51\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "sample_index"):
                load_survey_csv(bad_sequence_path)

    def test_v2_rows_and_metadata_are_retained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            csv_path = temporary_path / "survey.csv"
            csv_path.write_text(
                ",".join(V2_CSV_FIELDS)
                + "\n"
                + "1,10.5,-2.5,0,100,-52.5,2026-09-01T12:00:00Z,1000,7,ap-hash,80,10,0,-5\n"
                + "1,10.5,-2.5,1,200,-51.5,2026-09-01T12:00:00.1Z,1100,8,ap-hash,80,10,0,-5\n",
                encoding="utf-8",
            )
            document = self._valid_metadata_document()
            document["hardware"] = {"board_model": "unknown-board-marking"}
            document["transmitters"] = [
                {"ap_id": "ap-hash", "x_cm": 0, "y_cm": 0, "z_cm": 100}
            ]
            metadata_path = temporary_path / "metadata.json"
            metadata_path.write_text(json.dumps(document), encoding="utf-8")

            dataset = load_survey_csv(csv_path, metadata_path)

        self.assertEqual(dataset.schema_version, "2.0")
        self.assertEqual(dataset.samples[0].x_cm, 10.5)
        self.assertEqual(dataset.samples[0].host_monotonic_ns, 1000)
        self.assertEqual(dataset.samples[0].ap_id, "ap-hash")
        self.assertEqual(dataset.metadata.document["hardware"]["board_model"], "unknown-board-marking")
        self.assertEqual(dataset.metadata.document["transmitters"][0]["z_cm"], 100)

    def test_metadata_rejects_contradictory_units_and_sensitive_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata_path = Path(temporary_directory) / "metadata.json"
            contradictory = self._valid_metadata_document()
            contradictory["units"]["position"] = "m"
            metadata_path.write_text(json.dumps(contradictory), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "contradicts"):
                load_survey_metadata(metadata_path)

            sensitive = self._valid_metadata_document()
            sensitive["hardware"] = {"hotspot_password": "must-not-be-stored"}
            metadata_path.write_text(json.dumps(sensitive), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "forbidden"):
                load_survey_metadata(metadata_path)

    def test_metadata_rejects_invalid_pose_channel_and_transmitters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            metadata_path = Path(temporary_directory) / "metadata.json"

            bad_covariance = self._valid_metadata_document()
            bad_covariance["pose"] = {"covariance_cm2": [[1.0, 2.0], [0.0, 1.0]]}
            metadata_path.write_text(json.dumps(bad_covariance), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "symmetric"):
                load_survey_metadata(metadata_path)

            bad_channel = self._valid_metadata_document()
            bad_channel["channel"] = {"channel": 0}
            metadata_path.write_text(json.dumps(bad_channel), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "at least 1"):
                load_survey_metadata(metadata_path)

            duplicate_transmitters = self._valid_metadata_document()
            duplicate_transmitters["transmitters"] = [
                {"ap_id": "ap-a", "x_cm": 0, "y_cm": 0, "z_cm": 100},
                {"ap_id": "ap-a", "x_cm": 100, "y_cm": 0, "z_cm": 100},
            ]
            metadata_path.write_text(
                json.dumps(duplicate_transmitters), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "repeats transmitter"):
                load_survey_metadata(metadata_path)

    def test_metadata_hash_schema_and_count_must_match_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            csv_path = root / "survey.csv"
            csv_path.write_text(
                ",".join(V2_CSV_FIELDS)
                + "\n1,0,0,0,100,-50,2026-09-01T12:00:00Z,1000,0,ap-a,80,0,0,0\n",
                encoding="utf-8",
            )
            document = self._valid_metadata_document()
            document["transmitters"] = [
                {"ap_id": "ap-a", "x_cm": 0, "y_cm": 0, "z_cm": 100}
            ]
            document["data"] = {
                "csv_schema": "2.0",
                "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                "received_sample_count": 1,
            }
            metadata_path = root / "metadata.json"
            metadata_path.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(len(load_survey_csv(csv_path, metadata_path).samples), 1)

            document["data"]["received_sample_count"] = 2
            metadata_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "received_sample_count"):
                load_survey_csv(csv_path, metadata_path)

            document["data"]["received_sample_count"] = 1
            document["data"]["csv_sha256"] = "0" * 64
            metadata_path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sha256 does not match"):
                load_survey_csv(csv_path, metadata_path)

    def test_fixed_pose_metadata_must_match_v2_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            csv_path = root / "survey.csv"
            csv_path.write_text(
                ",".join(V2_CSV_FIELDS)
                + "\n1,0,0,0,100,-50,2026-09-01T12:00:00Z,1000,0,ap-a,80,0,0,0\n",
                encoding="utf-8",
            )
            document = self._valid_metadata_document()
            document["pose"] = {"receiver_z_cm": 90}
            document["transmitters"] = [
                {"ap_id": "ap-a", "x_cm": 0, "y_cm": 0, "z_cm": 100}
            ]
            metadata_path = root / "metadata.json"
            metadata_path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "receiver_z_cm contradicts"):
                load_survey_csv(csv_path, metadata_path)

    def test_per_pass_outliers_and_drift_remain_auditable(self) -> None:
        samples = []
        for pass_index, values in (
            (1, (-50.0, -50.0, -49.0, -100.0)),
            (2, (-55.0, -55.0, -54.0, -53.0)),
        ):
            samples.extend(
                SurveySample(pass_index, 0.0, 0.0, index, index * 100, value)
                for index, value in enumerate(values)
            )

        summary = compute_location_statistics(samples)[(0.0, 0.0)]

        self.assertEqual(summary.raw.sample_count, 8)
        self.assertEqual(summary.robust.sample_count, 7)
        self.assertEqual(summary.outlier_count, 1)
        self.assertEqual(summary.per_pass[0].outlier_mask, (False, False, False, True))
        self.assertEqual(summary.raw_values_dbm[-1], -53.0)
        self.assertAlmostEqual(summary.pass_drift_db, -4.5)
        self.assertAlmostEqual(summary.between_pass_standard_deviation_db, 2.25)

    def test_inference_aggregates_never_mix_transmitters_or_heights(self) -> None:
        samples = []
        for ap_id, z_cm, center in (
            ("ap-a", 80.0, -40.0),
            ("ap-b", 80.0, -60.0),
            ("ap-a", 120.0, -50.0),
        ):
            for pass_index, drift in ((1, 0.0), (2, -2.0)):
                samples.extend(
                    SurveySample(
                        pass_index,
                        10.0,
                        20.0,
                        sample_index,
                        sample_index * 100,
                        center + drift + offset,
                        ap_id=ap_id,
                        z_cm=z_cm,
                    )
                    for sample_index, offset in enumerate((-1.0, 0.0, 1.0))
                )

        aggregates = compute_inference_aggregates(samples)

        self.assertEqual(len(aggregates), 3)
        ap_a = aggregates[("ap-a", 10.0, 20.0, 80.0, None, None, None)]
        self.assertEqual(ap_a.pass_count, 2)
        self.assertEqual(ap_a.sample_count, 6)
        self.assertEqual(ap_a.robust_central_rssi_dbm, -41.0)
        self.assertEqual(ap_a.between_pass_variance_db2, 1.0)
        self.assertEqual(ap_a.pass_median_range_db, 2.0)
        self.assertGreater(ap_a.within_pass_variance_db2, 0.0)

    def test_inference_aggregates_do_not_mix_antenna_orientations(self) -> None:
        samples = [
            SurveySample(
                1,
                10.0,
                20.0,
                0,
                index * 100,
                -40.0 - index,
                ap_id="ap-a",
                z_cm=80.0,
                yaw_deg=yaw,
                pitch_deg=0.0,
                roll_deg=0.0,
            )
            for index, yaw in enumerate((0.0, 90.0))
        ]

        aggregates = compute_inference_aggregates(samples)

        self.assertEqual(len(aggregates), 2)

    def test_zero_mad_keeps_quantization_but_flags_large_deviation(self) -> None:
        samples = [
            SurveySample(1, 0.0, 0.0, index, index * 100, value)
            for index, value in enumerate((-50.0, -50.0, -50.0, -49.0, -100.0))
        ]

        summary = compute_location_statistics(samples)[(0.0, 0.0)].per_pass[0]

        self.assertEqual(summary.outlier_mask, (False, False, False, False, True))

    @staticmethod
    def _valid_metadata_document() -> dict[str, object]:
        return {
            "schema_version": "2.0",
            "run_uuid": str(uuid.uuid4()),
            "units": {
                "position": "cm",
                "orientation": "deg",
                "rssi": "dBm",
                "device_time": "ms",
                "host_monotonic": "ns",
            },
        }


if __name__ == "__main__":
    unittest.main()
