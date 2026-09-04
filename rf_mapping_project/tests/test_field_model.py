import unittest

import numpy as np

from rf_mapping.field_model import (
    RFFieldGP,
    display_resolution_diagnostics,
    path_loss_mean,
    support_metrics,
)


class PathLossTests(unittest.TestCase):
    def test_path_loss_uses_three_dimensional_distance(self) -> None:
        receivers = np.array([[1.0, 0.0, 0.0], [0.0, 6.0, 8.0]])
        result = path_loss_mean(
            receivers,
            np.zeros(3),
            p0_dbm=-30.0,
            path_loss_exponent=2.0,
        )
        np.testing.assert_allclose(result, [-30.0, -50.0])

    def test_path_loss_rejects_invalid_parameters(self) -> None:
        with self.assertRaises(ValueError):
            path_loss_mean(
                [[1.0, 0.0]],
                [0.0, 0.0],
                p0_dbm=-30.0,
                path_loss_exponent=0.0,
            )


class GaussianProcessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.positions = np.array(
            [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
        )
        baseline = path_loss_mean(
            self.positions,
            [-1.0, -1.0],
            p0_dbm=-30.0,
            path_loss_exponent=2.0,
        )
        self.rssi = baseline + np.array([1.0, -1.0, 0.5, -0.5])

    def make_model(self) -> RFFieldGP:
        return RFFieldGP(
            ap_position_m=np.array([-1.0, -1.0]),
            p0_dbm=-30.0,
            path_loss_exponent=2.0,
            length_scale_m=0.4,
            signal_std_db=4.0,
            noise_floor_db=0.2,
        )

    def test_posterior_dimensions_and_values_are_finite(self) -> None:
        model = self.make_model().fit(
            self.positions, self.rssi, np.array([0.1, 0.2, 0.3, 0.4])
        )
        queries = np.array([[0.2, 0.3], [0.5, 0.5], [1.5, 1.5]])
        posterior = model.predict(queries)
        self.assertEqual(posterior.mean_dbm.shape, (3,))
        self.assertEqual(posterior.standard_deviation_db.shape, (3,))
        self.assertEqual(posterior.support.distance_to_sample_m.shape, (3,))
        self.assertTrue(np.all(np.isfinite(posterior.mean_dbm)))
        self.assertTrue(np.all(np.isfinite(posterior.standard_deviation_db)))
        self.assertTrue(np.all(posterior.standard_deviation_db >= 0.0))

    def test_uncertainty_is_lower_near_observations(self) -> None:
        model = self.make_model().fit(self.positions, self.rssi, 0.01)
        posterior = model.predict([[0.0, 0.0], [3.0, 3.0]])
        self.assertLess(
            posterior.standard_deviation_db[0],
            posterior.standard_deviation_db[1],
        )

    def test_duplicate_points_are_numerically_stable(self) -> None:
        positions = np.array([[0.0, 0.0], [0.0, 0.0], [1.0, 0.0]])
        rssi = np.array([-40.0, -40.5, -48.0])
        model = RFFieldGP(
            ap_position_m=[-1.0, 0.0],
            p0_dbm=-30.0,
            path_loss_exponent=2.0,
            noise_floor_db=0.0,
            initial_jitter_db2=1e-12,
        ).fit(positions, rssi, 0.0)
        posterior = model.predict([[0.0, 0.0], [0.5, 0.0]])
        self.assertTrue(np.all(np.isfinite(posterior.mean_dbm)))
        self.assertTrue(np.all(np.isfinite(posterior.standard_deviation_db)))
        self.assertGreater(model.jitter_used_db2, 0.0)

    def test_repeated_fit_and_prediction_are_deterministic(self) -> None:
        first = self.make_model().fit(self.positions, self.rssi, 0.1).predict(
            [[0.25, 0.25], [0.75, 0.75]]
        )
        second = self.make_model().fit(self.positions, self.rssi, 0.1).predict(
            [[0.25, 0.25], [0.75, 0.75]]
        )
        np.testing.assert_array_equal(first.mean_dbm, second.mean_dbm)
        np.testing.assert_array_equal(
            first.standard_deviation_db, second.standard_deviation_db
        )

    def test_leave_one_location_out_requires_four_unique_locations(self) -> None:
        model = self.make_model().fit(self.positions, self.rssi, 0.1)
        diagnostics = model.leave_one_location_out()
        self.assertIsNotNone(diagnostics)
        assert diagnostics is not None
        self.assertEqual(diagnostics.locations_xyz_m.shape, (4, 3))
        self.assertTrue(np.isfinite(diagnostics.rmse_db))
        self.assertTrue(np.isfinite(diagnostics.mae_db))

        small_model = self.make_model().fit(
            self.positions[:3], self.rssi[:3], 0.1
        )
        self.assertIsNone(small_model.leave_one_location_out())

    def test_constant_mean_fallback_requires_no_fake_ap(self) -> None:
        model = RFFieldGP(
            ap_position_m=None,
            p0_dbm=-45.0,
            path_loss_exponent=None,
            length_scale_m=0.5,
            signal_std_db=4.0,
        ).fit(self.positions, self.rssi, 0.1)
        posterior = model.predict([[0.5, 0.5]])
        self.assertTrue(np.isfinite(posterior.mean_dbm[0]))
        with self.assertRaises(ValueError):
            RFFieldGP(
                ap_position_m=None,
                p0_dbm=-45.0,
                path_loss_exponent=2.0,
            )


class SupportTests(unittest.TestCase):
    def test_support_distance_density_and_extrapolation(self) -> None:
        observations = np.array(
            [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        )
        queries = np.array([[0.5, 0.5], [1.0, 0.5], [2.0, 0.5]])
        support = support_metrics(
            observations, queries, length_scale_m=0.5
        )
        np.testing.assert_array_equal(
            support.inside_convex_hull, [True, True, False]
        )
        np.testing.assert_array_equal(
            support.extrapolation_mask, [False, False, True]
        )
        self.assertAlmostEqual(support.distance_to_sample_m[1], 0.5)
        self.assertGreater(support.effective_density[0], support.effective_density[2])

    def test_collinear_hull_does_not_claim_area_support(self) -> None:
        observations = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
        support = support_metrics(
            observations, [[1.0, 0.0], [1.0, 0.1]], length_scale_m=1.0
        )
        np.testing.assert_array_equal(
            support.inside_convex_hull, [True, False]
        )

    def test_resolution_diagnostics_warn_for_oversampled_grid(self) -> None:
        diagnostics = display_resolution_diagnostics(
            [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
            grid_resolution_m=0.05,
            length_scale_m=0.5,
        )
        self.assertAlmostEqual(diagnostics.median_measurement_spacing_m, 1.0)
        self.assertEqual(len(diagnostics.warnings), 2)


if __name__ == "__main__":
    unittest.main()
