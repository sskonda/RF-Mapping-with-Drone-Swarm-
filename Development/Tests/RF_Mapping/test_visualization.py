import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from rf_mapping.visualization import save_inference_figure


class InferenceFigureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x_centers = np.array([0.0, 0.5, 1.0])
        self.y_centers = np.array([0.0, 0.5, 1.0])
        self.grid = np.arange(9, dtype=float).reshape(3, 3)
        self.arguments = {
            "grid_x_centers_m": self.x_centers,
            "grid_y_centers_m": self.y_centers,
            "measured_receiver_xy_m": np.array(
                [[0.0, 0.0], [0.5, 0.5], [1.0, 1.0]]
            ),
            "measured_rssi_dbm": np.array([-35.0, -45.0, -55.0]),
            "posterior_mean_dbm": -35.0 - self.grid,
            "posterior_standard_deviation_db": 0.5 + self.grid / 4.0,
            "support_density": self.grid[::-1] + 1.0,
            "support_label": "Independent links (count)",
            "extrapolation_mask": np.array(
                [
                    [False, False, True],
                    [False, False, True],
                    [True, True, True],
                ]
            ),
            "excess_attenuation_map": self.grid / 3.0,
            "excess_attenuation_units": "dB/m",
            "bootstrap_evidence_frequency": self.grid / 8.0,
            "occupancy_state": np.array(
                [[1, 1, 0], [1, 2, 0], [0, 2, 0]], dtype=int
            ),
            "ap_positions_xy_m": np.array([[-0.25, 0.5], [1.25, 0.5]]),
            "ap_ids": ["AP-A", "AP-B"],
            "field_ap_id": "AP-A",
            "ray_start_xy_m": np.array([[-0.25, 0.5], [1.25, 0.5]]),
            "ray_end_xy_m": np.array([[1.0, 1.0], [0.0, 0.0]]),
            "component_labels": np.array(
                [[0, 0, 0], [0, 1, 0], [0, 1, 0]], dtype=int
            ),
            "show": False,
        }

    def test_creates_png_in_new_parent_without_showing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "nested" / "inference.png"
            with patch("rf_mapping.visualization.plt.show") as show:
                result = save_inference_figure(output_path=output, **self.arguments)
            self.assertEqual(result, output)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)
            show.assert_not_called()

    def test_panel_titles_are_exact(self) -> None:
        expected = {
            "Measured RSSI",
            "Estimated RF posterior mean",
            "Posterior standard deviation",
            "Data/link support",
            "Excess attenuation estimate",
            "Obstacle/attenuation evidence",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "figure.pdf"
            with patch("rf_mapping.visualization.plt.close"):
                save_inference_figure(output_path=output, **self.arguments)
                figure = plt.figure(plt.get_fignums()[-1])
                titles = {axis.get_title() for axis in figure.axes if axis.get_title()}
            plt.close(figure)
        self.assertEqual(titles, expected)

    def test_pdf_output_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.pdf"
            second = Path(directory) / "second.pdf"
            save_inference_figure(output_path=first, **self.arguments)
            save_inference_figure(output_path=second, **self.arguments)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_rejects_grid_shape_mismatch_and_nonfinite_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "figure.png"
            bad_shape = dict(self.arguments)
            bad_shape["posterior_mean_dbm"] = np.zeros((2, 3))
            with self.assertRaisesRegex(
                ValueError, "posterior_mean_dbm must have shape"
            ):
                save_inference_figure(output_path=output, **bad_shape)

            nonfinite = dict(self.arguments)
            nonfinite["support_density"] = self.grid.copy()
            nonfinite["support_density"][0, 0] = np.nan
            with self.assertRaisesRegex(
                ValueError, "support_density must contain only finite"
            ):
                save_inference_figure(output_path=output, **nonfinite)

    def test_rejects_invalid_state_and_frequency_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "figure.png"
            bad_state = dict(self.arguments)
            bad_state["occupancy_state"] = np.full((3, 3), 4)
            with self.assertRaisesRegex(ValueError, "occupancy_state values"):
                save_inference_figure(output_path=output, **bad_state)

            bad_frequency = dict(self.arguments)
            bad_frequency["bootstrap_evidence_frequency"] = np.full((3, 3), 1.01)
            with self.assertRaisesRegex(ValueError, r"must be in \[0, 1\]"):
                save_inference_figure(output_path=output, **bad_frequency)


if __name__ == "__main__":
    unittest.main()
