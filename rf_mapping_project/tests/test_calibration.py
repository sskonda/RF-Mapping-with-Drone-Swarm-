from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from rf_mapping.calibration import (
    fit_log_distance_calibration,
    load_calibration,
    load_calibration_csv,
    save_calibration,
)


class CalibrationTests(unittest.TestCase):
    def test_documented_example_is_valid_and_recoverable(self) -> None:
        example_path = (
            Path(__file__).resolve().parents[1]
            / "examples/calibration_samples.example.csv"
        )
        result = fit_log_distance_calibration(load_calibration_csv(example_path))
        self.assertTrue(result.converged)
        self.assertAlmostEqual(result.p0_dbm, -37.95, delta=0.01)
        self.assertAlmostEqual(result.path_loss_exponent, 1.9965, delta=0.001)

    def test_deterministic_robust_parameter_recovery_and_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            csv_path = temporary_path / "calibration.csv"
            self._write_calibration(csv_path, include_outlier=True)
            dataset = load_calibration_csv(csv_path)

            first = fit_log_distance_calibration(dataset)
            second = fit_log_distance_calibration(dataset)

            self.assertEqual(first.to_document(), second.to_document())
            self.assertAlmostEqual(first.p0_dbm, -38.0, delta=0.4)
            self.assertAlmostEqual(first.path_loss_exponent, 2.2, delta=0.08)
            self.assertGreater(first.downweighted_count, 0)
            self.assertLess(
                abs(first.path_loss_exponent - 2.2),
                abs(first.ols_path_loss_exponent - 2.2),
            )
            self.assertEqual(first.metadata["board_model"], "generic-esp32")
            self.assertEqual(len(first.input_sha256), 64)
            self.assertEqual(set(first.pass_residual_mean_db), {"1", "2"})

            output_path = temporary_path / "calibration.json"
            save_calibration(first, output_path)
            loaded = load_calibration(output_path)
            self.assertEqual(loaded.to_document(), first.to_document())
            predicted = loaded.predict_rssi_dbm([1.0, 2.0])
            self.assertEqual(predicted.shape, (2,))
            self.assertAlmostEqual(predicted[0], loaded.p0_dbm)

    def test_rejects_inconsistent_hardware_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path = Path(temporary_directory) / "calibration.csv"
            csv_path.write_text(
                "distance_m,rssi_dbm,pass_index,board_model\n"
                "1,-40,1,board-a\n"
                "2,-46,1,board-b\n"
                "4,-52,1,board-a\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must be constant"):
                load_calibration_csv(csv_path)

    def test_rejects_invalid_channel_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path = Path(temporary_directory) / "calibration.csv"
            csv_path.write_text(
                "distance_m,rssi_dbm,pass_index,channel\n"
                "1,-40,1,0\n2,-46,1,0\n4,-52,1,0\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "channel must be"):
                load_calibration_csv(csv_path)

    def test_rejects_non_decreasing_propagation_sweep(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path = Path(temporary_directory) / "calibration.csv"
            csv_path.write_text(
                "distance_m,rssi_dbm,pass_index\n"
                "1,-60,1\n2,-50,1\n4,-40,1\n",
                encoding="utf-8",
            )
            dataset = load_calibration_csv(csv_path)
            with self.assertRaisesRegex(ValueError, "non-positive path-loss exponent"):
                fit_log_distance_calibration(dataset)

    def test_each_pass_must_cover_the_same_distances(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path = Path(temporary_directory) / "calibration.csv"
            csv_path.write_text(
                "distance_m,rssi_dbm,pass_index\n"
                "1,-40,1\n2,-46,1\n4,-52,1\n"
                "1,-41,2\n2,-47,2\n8,-59,2\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "same known distances"):
                load_calibration_csv(csv_path)

    @staticmethod
    def _write_calibration(path: Path, *, include_outlier: bool) -> None:
        rows = ["distance_m,rssi_dbm,pass_index,board_model"]
        distances = (0.5, 1.0, 2.0, 4.0, 8.0)
        noise_values = (-0.3, 0.0, 0.2)
        for pass_index, pass_bias in ((1, -0.25), (2, 0.25)):
            for distance in distances:
                expected = -38.0 - 10.0 * 2.2 * math.log10(distance)
                for repeat_index, noise in enumerate(noise_values):
                    rssi = expected + pass_bias + noise
                    if include_outlier and pass_index == 1 and distance == 8.0 and repeat_index == 0:
                        rssi -= 20.0
                    rows.append(f"{distance},{rssi:.12f},{pass_index},generic-esp32")
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
