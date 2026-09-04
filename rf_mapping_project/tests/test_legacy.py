import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import rf_mapper


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_RAW = PROJECT_ROOT / "survey_output" / "raw_samples_20260831_184759.csv"


class LegacyDataTests(unittest.TestCase):
    def test_checked_in_grouping_and_statistics_are_unchanged(self) -> None:
        grouped = rf_mapper.load_grouped_samples(LEGACY_RAW)
        self.assertEqual(len(grouped), 9)
        self.assertTrue(all(len(values) == 50 for values in grouped.values()))
        median, mean, standard_deviation = rf_mapper.point_statistics(
            [{"rssi_dbm": value} for value in grouped[(0, 0)]]
        )
        self.assertEqual(median, -25.0)
        self.assertAlmostEqual(mean, -25.22)
        self.assertAlmostEqual(standard_deviation, 1.1881077392223316)

    def test_plot_with_arbitrary_filename_never_overwrites_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.csv"
            shutil.copy2(LEGACY_RAW, source)
            before = hashlib.sha256(source.read_bytes()).digest()
            summary, heatmap = rf_mapper.write_summary_and_heatmap(
                source, "Measured RSSI", None, None, False
            )
            self.assertEqual(summary.name, "input_point_summary.csv")
            self.assertEqual(heatmap.name, "input_rssi_heatmap.png")
            self.assertTrue(summary.is_file())
            self.assertTrue(heatmap.is_file())
            self.assertEqual(before, hashlib.sha256(source.read_bytes()).digest())

    def test_legacy_parser_defaults_and_commands_remain_available(self) -> None:
        parser = rf_mapper.build_argument_parser()
        plot = parser.parse_args(["plot", str(LEGACY_RAW)])
        self.assertEqual(plot.command, "plot")
        self.assertEqual(plot.title, "Measured RSSI")
        survey = parser.parse_args(
            [
                "survey",
                "--width-cm",
                "100",
                "--height-cm",
                "100",
                "--spacing-cm",
                "50",
            ]
        )
        self.assertEqual(survey.passes, 1)


class SerialProtocolTests(unittest.TestCase):
    class FakeSerial:
        def __init__(self, lines: list[str]) -> None:
            self.lines = [f"{line}\n".encode() for line in lines]
            self.written = b""

        def reset_input_buffer(self) -> None:
            pass

        def write(self, value: bytes) -> None:
            self.written += value

        def readline(self) -> bytes:
            return self.lines.pop(0) if self.lines else b""

    def test_malformed_and_out_of_range_data_rows_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            rf_mapper.parse_data_line("DATA,0,0,0,1")
        with self.assertRaises(ValueError):
            rf_mapper.parse_data_line("DATA,0,0,0,1,-200")
        with self.assertRaises(ValueError):
            rf_mapper.parse_data_line("DATA,100001,0,0,1,-50")
        with self.assertRaises(ValueError):
            rf_mapper.parse_data_line("DATA,0,0,0,4294967296,-50")

    def test_device_timestamp_wrap_is_supported(self) -> None:
        self.assertTrue(rf_mapper.device_time_advances(0xFFFFFFF0, 20))
        self.assertFalse(rf_mapper.device_time_advances(100, 100))

    def test_data_before_start_is_rejected(self) -> None:
        connection = self.FakeSerial(["DATA,0,0,0,100,-40"])
        with self.assertRaisesRegex(RuntimeError, "before.*started"):
            rf_mapper.measure_point(connection, 0, 0)

    def test_out_of_order_sample_index_is_rejected(self) -> None:
        connection = self.FakeSerial(
            ["START,0,0,2", "DATA,0,0,1,100,-40"]
        )
        with self.assertRaisesRegex(RuntimeError, "out-of-order"):
            rf_mapper.measure_point(connection, 0, 0)


if __name__ == "__main__":
    unittest.main()
