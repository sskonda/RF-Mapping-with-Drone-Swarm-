import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from rf_mapping.calibration import load_calibration
from rf_mapping.data import load_survey_csv
from rf_mapping.simulation import (
    SimulationConfig,
    binary_overlap_metrics,
    boundary_distance_metrics,
    bounding_box_dimension_error,
    generate_synthetic_dataset,
    root_mean_square_error,
    simulate_survey,
    validate_synthetic_survey,
)


class SyntheticOutputTests(unittest.TestCase):
    def test_default_optimizer_budget_reaches_convergence(self) -> None:
        config = SimulationConfig()
        result = validate_synthetic_survey(simulate_survey(config))
        self.assertTrue(result.attenuation_result.converged)
        self.assertEqual(result.bootstrap_converged_fit_count, result.bootstrap_fit_count)

    def test_same_seed_reproduces_arrays_and_files_exactly(self) -> None:
        config = SimulationConfig(
            scene="empty",
            link_geometry="crossing",
            seed=19,
            grid_resolution_m=0.5,
            receiver_spacing_m=0.5,
            bootstrap_count=2,
            optimizer_max_iterations=300,
        )
        first_data = simulate_survey(config)
        second_data = simulate_survey(config)
        np.testing.assert_array_equal(
            first_data.rssi_samples_dbm, second_data.rssi_samples_dbm
        )
        np.testing.assert_array_equal(first_data.ray_matrix_m, second_data.ray_matrix_m)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = generate_synthetic_dataset(root / "first", config)
            generate_synthetic_dataset(root / "second", config)
            for filename in (
                "survey_samples.csv",
                "survey_metadata.json",
                "calibration_samples.csv",
                "calibration.json",
                "ground_truth.npz",
                "validation.json",
            ):
                self.assertEqual(
                    (root / "first" / filename).read_bytes(),
                    (root / "second" / filename).read_bytes(),
                    filename,
                )

            loaded_survey = load_survey_csv(first.survey_csv, first.metadata_json)
            loaded_calibration = load_calibration(first.calibration_json)
            self.assertEqual(loaded_survey.schema_version, "2.0")
            metadata = loaded_survey.metadata.document
            self.assertIn("position_standard_deviation_cm", metadata["pose"])
            self.assertEqual(metadata["channel"]["channel"], 6)
            self.assertIn("position_cm", metadata["transmitters"][0])
            self.assertAlmostEqual(loaded_calibration.p0_dbm, config.p0_dbm, delta=0.3)
            self.assertAlmostEqual(
                loaded_calibration.path_loss_exponent,
                config.path_loss_exponent,
                delta=0.08,
            )
            report = json.loads(first.validation_json.read_text(encoding="utf-8"))
            calibration_document = json.loads(
                first.calibration_json.read_text(encoding="utf-8")
            )
            self.assertEqual(
                calibration_document["shared_model_for_ap_ids"],
                list(first.dataset.transmitter_ids),
            )
            self.assertEqual(report["seed"], config.seed)
            self.assertEqual(len(report["input_sha256"]), 5)
            self.assertEqual(
                metadata["calibration"]["sha256"],
                report["input_sha256"]["calibration_json"],
            )

    def test_generated_csv_preserves_subcentimetre_receiver_pose(self) -> None:
        config = SimulationConfig(
            scene="empty",
            link_geometry="single-ap",
            grid_resolution_m=0.5,
            receiver_spacing_m=0.333,
            bootstrap_count=1,
            optimizer_max_iterations=5,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifacts = generate_synthetic_dataset(temporary_directory, config)
            loaded = load_survey_csv(
                artifacts.survey_csv, artifacts.metadata_json
            )

        self.assertAlmostEqual(loaded.samples[0].x_cm, 16.65, places=10)
        self.assertAlmostEqual(loaded.samples[0].y_cm, 16.65, places=10)


class SyntheticInferenceTests(unittest.TestCase):
    def test_empty_scene_has_low_false_evidence_and_no_component(self) -> None:
        config = SimulationConfig(
            scene="empty",
            link_geometry="crossing",
            seed=4,
            grid_resolution_m=0.5,
            receiver_spacing_m=0.5,
            bootstrap_count=6,
            optimizer_max_iterations=500,
        )
        result = validate_synthetic_survey(simulate_survey(config))
        self.assertTrue(result.attenuation_result.converged)
        self.assertEqual(
            result.bootstrap_converged_fit_count, result.bootstrap_fit_count
        )
        self.assertEqual(result.status, "no_supported_component")
        self.assertFalse(result.components)
        self.assertLess(float(np.max(result.evidence_frequency)), 0.5)
        self.assertEqual(result.metrics["iou"], 1.0)
        self.assertEqual(result.metrics["false_positive_rate"], 0.0)

    def test_crossing_links_recover_aligned_rectangle_at_grid_tolerance(self) -> None:
        config = SimulationConfig(
            scene="one-rectangle",
            link_geometry="crossing",
            seed=7,
            grid_resolution_m=0.5,
            receiver_spacing_m=0.5,
            bootstrap_count=6,
            optimizer_max_iterations=500,
        )
        result = validate_synthetic_survey(simulate_survey(config))
        self.assertTrue(result.attenuation_result.converged)
        self.assertEqual(
            result.bootstrap_converged_fit_count, result.bootstrap_fit_count
        )
        self.assertEqual(result.status, "potential_attenuation_components")
        self.assertGreater(int(np.count_nonzero(result.support.observable_mask)), 0)
        self.assertGreaterEqual(result.metrics["iou"], 0.5)
        self.assertGreaterEqual(result.metrics["precision"], 0.6)
        self.assertGreaterEqual(result.metrics["recall"], 0.6)
        self.assertLessEqual(
            result.metrics["boundary"]["hausdorff_m"],
            2.0 * config.grid_resolution_m,
        )
        self.assertLessEqual(
            result.metrics["bounding_box"]["absolute_width_error_m"],
            config.grid_resolution_m,
        )
        self.assertLessEqual(
            result.metrics["bounding_box"]["absolute_height_error_m"],
            config.grid_resolution_m,
        )

    def test_single_ap_rectangle_is_suppressed_by_observability(self) -> None:
        config = SimulationConfig(
            scene="one-rectangle",
            link_geometry="single-ap",
            seed=7,
            grid_resolution_m=0.5,
            receiver_spacing_m=0.5,
            bootstrap_count=4,
            optimizer_max_iterations=500,
        )
        result = validate_synthetic_survey(simulate_survey(config))
        self.assertEqual(result.status, "insufficient_observability")
        self.assertFalse(np.any(result.support.observable_mask))
        self.assertFalse(result.components)
        self.assertFalse(np.any(result.component_labels))


class MetricTests(unittest.TestCase):
    def test_metrics_have_physical_units_and_expected_values(self) -> None:
        x_centers = np.array([0.25, 0.75, 1.25, 1.75])
        y_centers = x_centers.copy()
        reference = np.zeros((4, 4), dtype=bool)
        reference[1:3, 1:3] = True
        estimate = np.zeros((4, 4), dtype=bool)
        estimate[1:3, 2:4] = True

        self.assertAlmostEqual(root_mean_square_error(reference, estimate), 0.5)
        overlap = binary_overlap_metrics(reference, estimate)
        self.assertAlmostEqual(overlap["iou"], 1.0 / 3.0)
        self.assertAlmostEqual(overlap["precision"], 0.5)
        self.assertAlmostEqual(overlap["recall"], 0.5)
        self.assertAlmostEqual(overlap["false_positive_rate"], 1.0 / 6.0)
        boundary = boundary_distance_metrics(reference, estimate, x_centers, y_centers)
        self.assertAlmostEqual(boundary["hausdorff_m"], 0.5)
        dimensions = bounding_box_dimension_error(
            reference, estimate, x_centers, y_centers
        )
        self.assertEqual(dimensions["absolute_width_error_m"], 0.0)
        self.assertEqual(dimensions["absolute_height_error_m"], 0.0)


if __name__ == "__main__":
    unittest.main()
