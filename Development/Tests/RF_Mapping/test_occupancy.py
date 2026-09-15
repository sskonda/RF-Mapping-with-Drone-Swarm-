import unittest

import numpy as np

from rf_mapping.occupancy import (
    attenuation_objective,
    bootstrap_attenuation_evidence,
    fit_attenuation_map,
    line_grid_intersection_lengths,
    occupancy_from_evidence,
)


class RayIntersectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.centers = np.array([0.5, 1.5])

    def test_horizontal_vertical_and_diagonal_lengths(self) -> None:
        horizontal = line_grid_intersection_lengths(
            (0.0, 0.5), (2.0, 0.5), self.centers, self.centers
        )
        vertical = line_grid_intersection_lengths(
            (0.5, 0.0), (0.5, 2.0), self.centers, self.centers
        )
        diagonal = line_grid_intersection_lengths(
            (0.0, 0.0), (2.0, 2.0), self.centers, self.centers
        )
        np.testing.assert_allclose(horizontal, [[1.0, 1.0], [0.0, 0.0]])
        np.testing.assert_allclose(vertical, [[1.0, 0.0], [1.0, 0.0]])
        np.testing.assert_allclose(
            diagonal, [[np.sqrt(2.0), 0.0], [0.0, np.sqrt(2.0)]]
        )

    def test_boundary_clipping_and_zero_length(self) -> None:
        boundary = line_grid_intersection_lengths(
            (0.0, 1.0), (2.0, 1.0), self.centers, self.centers
        )
        clipped = line_grid_intersection_lengths(
            (-1.0, 0.5), (1.0, 0.5), self.centers, self.centers
        )
        zero = line_grid_intersection_lengths(
            (0.5, 0.5), (0.5, 0.5), self.centers, self.centers
        )
        np.testing.assert_allclose(boundary, [[0.0, 0.0], [1.0, 1.0]])
        np.testing.assert_allclose(clipped, [[1.0, 0.0], [0.0, 0.0]])
        self.assertEqual(float(np.sum(zero)), 0.0)


class AttenuationMapTests(unittest.TestCase):
    def test_map_is_nonnegative_convergent_and_matches_one_cell_solution(self) -> None:
        matrix = np.ones((2, 1))
        observed = np.array([2.0, 2.0])
        noise = np.ones(2)
        result = fit_attenuation_map(
            matrix,
            observed,
            noise,
            (1, 1),
            lambda_l1=0.0,
            lambda_tv=0.0,
            max_iterations=500,
        )
        self.assertTrue(result.converged)
        self.assertAlmostEqual(float(result.attenuation_db_per_m[0, 0]), 2.0, places=4)
        self.assertTrue(np.all(result.attenuation_db_per_m >= 0))
        self.assertTrue(
            all(
                current <= previous + 1e-10
                for previous, current in zip(
                    result.objective_history, result.objective_history[1:]
                )
            )
        )
        self.assertAlmostEqual(
            attenuation_objective(
                result.attenuation_db_per_m,
                matrix,
                observed,
                noise,
                0.0,
                0.0,
                0.05,
                (1, 1),
            ),
            result.objective_history[-1],
        )

    def test_negative_excess_does_not_create_negative_attenuation(self) -> None:
        result = fit_attenuation_map(
            np.ones((1, 1)),
            np.array([-3.0]),
            np.ones(1),
            (1, 1),
            lambda_l1=0.0,
            lambda_tv=0.0,
        )
        self.assertEqual(float(result.attenuation_db_per_m[0, 0]), 0.0)

    def test_bootstrap_is_deterministic(self) -> None:
        arguments = dict(
            ray_matrix_m=np.ones((2, 1)),
            excess_attenuation_db=np.array([3.0, 3.0]),
            noise_standard_deviation_db=np.array([0.2, 0.2]),
            grid_shape=(1, 1),
            seed=7,
            bootstrap_count=5,
            attenuation_threshold_db_per_m=1.0,
            fit_options={"lambda_l1": 0.0, "lambda_tv": 0.0},
        )
        np.testing.assert_array_equal(
            bootstrap_attenuation_evidence(**arguments),
            bootstrap_attenuation_evidence(**arguments),
        )


class OccupancySemanticsTests(unittest.TestCase):
    def test_unknown_free_and_supported_evidence_are_distinct(self) -> None:
        evidence = np.array([[0.9, 0.9], [0.2, 0.8]])
        observable = np.array([[False, True], [True, True]])
        traversed = np.array([[False, False], [True, False]])
        ap_cells = np.array([[False, True], [False, False]])
        occupancy, states = occupancy_from_evidence(
            evidence, observable, traversed, ap_cells
        )
        self.assertEqual(occupancy[0, 0], 0.5)
        self.assertEqual(states[0, 0], 0)
        self.assertEqual(occupancy[1, 0], 0.05)
        self.assertEqual(states[1, 0], 1)
        self.assertEqual(occupancy[0, 1], 0.5)
        self.assertEqual(states[0, 1], 3)
        self.assertGreater(occupancy[1, 1], 0.5)
        self.assertEqual(states[1, 1], 2)

        threshold_occupancy, threshold_states = occupancy_from_evidence(
            np.array([[0.7]]),
            np.array([[True]]),
            np.array([[False]]),
            np.array([[False]]),
            occupied_activation=0.7,
        )
        self.assertEqual(threshold_occupancy[0, 0], 0.5)
        self.assertEqual(threshold_states[0, 0], 2)


if __name__ == "__main__":
    unittest.main()
