import unittest

import numpy as np

from rf_mapping.observability import (
    ObservabilityConfig,
    calculate_support,
    extract_components,
)
from rf_mapping.occupancy import build_ray_matrix


class ObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.centers = np.array([0.5, 1.5, 2.5])
        self.config = ObservabilityConfig(
            min_links=2,
            min_transmitters=2,
            min_angle_bins=2,
            angle_bin_count=8,
            max_receiver_distance_m=10.0,
            min_sensitivity=0.0,
            min_conditioning_score=0.0,
            min_pass_consistency=0.5,
            min_repeated_links=2,
        )

    def test_one_or_collinear_geometry_is_suppressed(self) -> None:
        transmitters = np.array([[0.0, 1.5], [0.0, 1.5]])
        receivers = np.array([[3.0, 1.5], [2.5, 1.5]])
        matrix = build_ray_matrix(
            transmitters, receivers, self.centers, self.centers
        )
        metrics = calculate_support(
            matrix,
            transmitters,
            receivers,
            ["ap-a", "ap-a"],
            np.ones(2),
            self.centers,
            self.centers,
            link_pass_consistency=np.ones(2),
            link_pass_counts=np.full(2, 3),
            config=self.config,
        )
        self.assertFalse(np.any(metrics.observable_mask))
        self.assertGreater(metrics.failed_criteria_counts["transmitters"], 0)

    def test_crossing_multi_transmitter_geometry_can_pass(self) -> None:
        transmitters = np.array([[0.0, 1.5], [1.5, 0.0]])
        receivers = np.array([[3.0, 1.5], [1.5, 3.0]])
        matrix = build_ray_matrix(
            transmitters, receivers, self.centers, self.centers
        )
        metrics = calculate_support(
            matrix,
            transmitters,
            receivers,
            ["ap-a", "ap-b"],
            np.ones(2),
            self.centers,
            self.centers,
            link_pass_consistency=np.ones(2),
            link_pass_counts=np.full(2, 3),
            config=self.config,
        )
        self.assertTrue(metrics.observable_mask[1, 1])

    def test_distinct_but_collinear_transmitters_fail_angle_gate(self) -> None:
        transmitters = np.array([[0.0, 1.5], [3.0, 1.5]])
        receivers = np.array([[3.0, 1.5], [0.0, 1.5]])
        matrix = build_ray_matrix(
            transmitters, receivers, self.centers, self.centers
        )
        metrics = calculate_support(
            matrix,
            transmitters,
            receivers,
            ["ap-a", "ap-b"],
            np.ones(2),
            self.centers,
            self.centers,
            link_pass_consistency=np.ones(2),
            link_pass_counts=np.full(2, 3),
            config=self.config,
        )
        self.assertEqual(metrics.transmitter_count[1, 1], 2)
        self.assertEqual(metrics.angle_bin_count[1, 1], 1)
        self.assertFalse(metrics.observable_mask[1, 1])

    def test_inconsistent_passes_fail_repeatability_gate(self) -> None:
        transmitters = np.array([[0.0, 1.5], [1.5, 0.0]])
        receivers = np.array([[3.0, 1.5], [1.5, 3.0]])
        matrix = build_ray_matrix(
            transmitters, receivers, self.centers, self.centers
        )
        metrics = calculate_support(
            matrix,
            transmitters,
            receivers,
            ["ap-a", "ap-b"],
            np.ones(2),
            self.centers,
            self.centers,
            link_pass_consistency=np.array([0.1, 0.1]),
            link_pass_counts=np.full(2, 3),
            config=self.config,
        )
        self.assertFalse(metrics.observable_mask[1, 1])
        self.assertLess(metrics.pass_consistency[1, 1], 0.5)

    def test_duplicate_rows_do_not_count_as_independent_links(self) -> None:
        transmitters = np.array(
            [[0.0, 1.5], [0.0, 1.5], [1.5, 0.0], [1.5, 0.0]]
        )
        receivers = np.array(
            [[3.0, 1.5], [3.0, 1.5], [1.5, 3.0], [1.5, 3.0]]
        )
        matrix = build_ray_matrix(
            transmitters, receivers, self.centers, self.centers
        )
        config = ObservabilityConfig(
            min_links=4,
            min_transmitters=2,
            min_angle_bins=2,
            angle_bin_count=8,
            max_receiver_distance_m=10.0,
            min_sensitivity=0.0,
            min_conditioning_score=0.0,
            min_pass_consistency=0.5,
            min_repeated_links=2,
        )
        metrics = calculate_support(
            matrix,
            transmitters,
            receivers,
            ["ap-a", "ap-a", "ap-b", "ap-b"],
            np.ones(4),
            self.centers,
            self.centers,
            link_pass_consistency=np.ones(4),
            link_pass_counts=np.full(4, 3),
            config=config,
        )
        self.assertEqual(metrics.link_count[1, 1], 2)
        self.assertFalse(metrics.observable_mask[1, 1])


class ComponentMetricTests(unittest.TestCase):
    def test_known_rectangle_dimensions_match_grid_resolution(self) -> None:
        x_centers = np.arange(0.25, 2.0, 0.5)
        y_centers = np.arange(0.25, 1.5, 0.5)
        evidence = np.zeros((len(y_centers), len(x_centers)))
        evidence[1:3, 1:4] = 0.9
        observable = np.ones_like(evidence, dtype=bool)
        ray_matrix = np.ones((4, evidence.size))
        labels, components = extract_components(
            evidence,
            observable,
            ray_matrix,
            ["ap-a", "ap-b", "ap-a", "ap-b"],
            x_centers,
            y_centers,
            evidence_threshold=0.8,
        )
        self.assertEqual(int(np.max(labels)), 1)
        self.assertEqual(len(components), 1)
        component = components[0]
        self.assertAlmostEqual(component.axis_aligned_width_m, 1.5)
        self.assertAlmostEqual(component.axis_aligned_height_m, 1.0)
        self.assertAlmostEqual(component.area_m2, 1.5)
        self.assertAlmostEqual(component.perimeter_m, 5.0)
        self.assertEqual(component.supporting_links, 2)
        self.assertEqual(component.supporting_transmitters, 2)


if __name__ == "__main__":
    unittest.main()
