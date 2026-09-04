from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from rf_mapping.inference import InferenceConfig, run_offline_inference
from rf_mapping.simulation import SimulationConfig, generate_synthetic_dataset


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CHECKED_IN_SURVEY = REPOSITORY_ROOT / "survey_output/raw_samples_20260831_184759.csv"


def _synthetic_inference_config(seed: int) -> InferenceConfig:
    return InferenceConfig(
        grid_resolution_m=0.5,
        kernel_length_scale_m=0.5,
        lambda_l1=0.08,
        lambda_tv=0.12,
        optimizer_max_iterations=1000,
        optimizer_relative_tolerance=5e-5,
        bootstrap_count=4,
        evidence_threshold=0.625,
        minimum_component_cells=1,
        seed=seed,
        min_links=2,
        min_transmitters=2,
        min_angle_bins=2,
        max_receiver_distance_m=1.5,
        min_sensitivity=0.0,
        min_conditioning_score=0.0,
        min_pass_consistency=0.0,
        min_repeated_links=2,
    )


class OfflineInferenceTests(unittest.TestCase):
    def test_checked_in_legacy_data_is_deterministic_and_makes_no_shape_claim(self) -> None:
        config = InferenceConfig(
            grid_resolution_m=0.25,
            kernel_length_scale_m=0.5,
            bootstrap_count=2,
            optimizer_max_iterations=50,
            seed=11,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            first = run_offline_inference(
                [CHECKED_IN_SURVEY], output_directory=root / "first", config=config
            )
            second = run_offline_inference(
                [CHECKED_IN_SURVEY], output_directory=root / "second", config=config
            )

            self.assertEqual(first.status, "uncalibrated_inference_disabled")
            self.assertEqual(first.component_count, 0)
            self.assertEqual(
                first.arrays_path.read_bytes(), second.arrays_path.read_bytes()
            )
            self.assertEqual(
                first.figure_path.read_bytes(), second.figure_path.read_bytes()
            )
            first_report = json.loads(first.report_path.read_text(encoding="utf-8"))
            second_report = json.loads(second.report_path.read_text(encoding="utf-8"))
            self.assertEqual(first_report, second_report)
            self.assertEqual(first_report["observability"]["observable_cell_count"], 0)
            self.assertFalse(first_report["components"])
            arrays = np.load(first.arrays_path)
            self.assertTrue(
                {
                    "posterior_mean_dbm",
                    "posterior_standard_deviation_db",
                    "distance_to_sample_m",
                    "distance_to_receiver_m",
                    "link_count",
                    "repeated_link_count",
                    "observable_mask",
                    "bootstrap_evidence_frequency",
                    "occupancy_state",
                }.issubset(arrays.files)
            )
            self.assertTrue(np.all(arrays["occupancy_state"] == 0))
            self.assertTrue(np.all(arrays["occupancy_evidence_score"] == 0.5))

    def test_crossing_synthetic_links_recover_a_tentative_component(self) -> None:
        simulation_config = SimulationConfig(
            seed=7,
            grid_resolution_m=0.5,
            receiver_spacing_m=0.5,
            bootstrap_count=4,
            optimizer_max_iterations=600,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            synthetic = generate_synthetic_dataset(root / "synthetic", simulation_config)
            result = run_offline_inference(
                [synthetic.survey_csv],
                metadata_paths=[synthetic.metadata_json],
                calibration_paths=[synthetic.calibration_json],
                output_directory=root / "inference",
                config=_synthetic_inference_config(simulation_config.seed),
                allow_shared_calibration=True,
            )
            report = json.loads(result.report_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, "experimental_components_detected")
        self.assertGreaterEqual(result.component_count, 1)
        self.assertTrue(report["attenuation_model"]["converged"])
        self.assertEqual(
            report["attenuation_model"]["bootstrap_converged_fit_count"],
            report["attenuation_model"]["bootstrap_fit_count"],
        )
        self.assertGreater(report["observability"]["observable_cell_count"], 0)
        self.assertFalse(report["observability"]["metadata_gate_issues"])
        component = report["components"][0]
        self.assertAlmostEqual(component["axis_aligned_width_m"], 1.0, delta=0.5)
        self.assertAlmostEqual(component["axis_aligned_height_m"], 2.0, delta=0.5)
        self.assertIn("sha256", report["calibrations"][0])

    def test_single_ap_synthetic_geometry_suppresses_components(self) -> None:
        simulation_config = SimulationConfig(
            link_geometry="single-ap",
            seed=7,
            grid_resolution_m=0.5,
            receiver_spacing_m=0.5,
            bootstrap_count=3,
            optimizer_max_iterations=600,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            synthetic = generate_synthetic_dataset(root / "synthetic", simulation_config)
            result = run_offline_inference(
                [synthetic.survey_csv],
                metadata_paths=[synthetic.metadata_json],
                calibration_paths=[synthetic.calibration_json],
                output_directory=root / "inference",
                config=_synthetic_inference_config(simulation_config.seed),
            )
            report = json.loads(result.report_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, "insufficient_observability")
        self.assertEqual(result.component_count, 0)
        self.assertEqual(report["observability"]["observable_cell_count"], 0)

    def test_explicitly_mismatched_calibration_is_not_implicitly_assigned(self) -> None:
        simulation_config = SimulationConfig(
            link_geometry="single-ap",
            seed=5,
            grid_resolution_m=0.5,
            receiver_spacing_m=1.0,
            bootstrap_count=2,
            optimizer_max_iterations=300,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            synthetic = generate_synthetic_dataset(root / "synthetic", simulation_config)
            artifact = json.loads(synthetic.calibration_json.read_text(encoding="utf-8"))
            artifact["input"]["metadata"]["ap_id"] = "different-ap"
            mismatched_path = root / "mismatched.json"
            mismatched_path.write_text(
                json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            result = run_offline_inference(
                [synthetic.survey_csv],
                metadata_paths=[synthetic.metadata_json],
                calibration_paths=[mismatched_path],
                output_directory=root / "inference",
                config=_synthetic_inference_config(simulation_config.seed),
            )

        self.assertEqual(result.status, "missing_link_geometry")
        self.assertTrue(any("Missing calibration" in item for item in result.warnings))

    def test_recorded_calibration_hash_mismatch_suppresses_shape(self) -> None:
        simulation_config = SimulationConfig(
            seed=9,
            grid_resolution_m=0.5,
            receiver_spacing_m=0.5,
            bootstrap_count=2,
            optimizer_max_iterations=600,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            synthetic = generate_synthetic_dataset(root / "synthetic", simulation_config)
            metadata = json.loads(synthetic.metadata_json.read_text(encoding="utf-8"))
            metadata["calibration"]["sha256"] = "0" * 64
            mismatched_metadata = root / "mismatched_metadata.json"
            mismatched_metadata.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = run_offline_inference(
                [synthetic.survey_csv],
                metadata_paths=[mismatched_metadata],
                calibration_paths=[synthetic.calibration_json],
                output_directory=root / "inference",
                config=_synthetic_inference_config(simulation_config.seed),
                allow_shared_calibration=True,
            )
            report = json.loads(result.report_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, "insufficient_observability")
        self.assertEqual(result.component_count, 0)
        self.assertTrue(
            any(
                "recorded calibration hash" in issue
                for issue in report["observability"]["metadata_gate_issues"]
            )
        )

    def test_placeholder_hardware_metadata_suppresses_shape(self) -> None:
        simulation_config = SimulationConfig(
            seed=10,
            grid_resolution_m=0.5,
            receiver_spacing_m=0.5,
            bootstrap_count=2,
            optimizer_max_iterations=600,
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            synthetic = generate_synthetic_dataset(root / "synthetic", simulation_config)
            metadata = json.loads(synthetic.metadata_json.read_text(encoding="utf-8"))
            metadata["hardware"]["board_model"] = "REPLACE_WITH_EXACT_BOARD_MARKING"
            unresolved_metadata = root / "unresolved_metadata.json"
            unresolved_metadata.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = run_offline_inference(
                [synthetic.survey_csv],
                metadata_paths=[unresolved_metadata],
                calibration_paths=[synthetic.calibration_json],
                output_directory=root / "inference",
                config=_synthetic_inference_config(simulation_config.seed),
                allow_shared_calibration=True,
            )
            report = json.loads(result.report_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, "insufficient_observability")
        self.assertEqual(result.component_count, 0)
        self.assertTrue(
            any(
                "hardware.board_model is missing or unresolved" in issue
                for issue in report["observability"]["metadata_gate_issues"]
            )
        )


if __name__ == "__main__":
    unittest.main()
