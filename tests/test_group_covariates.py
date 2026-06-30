from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

import MakeGroupCovariates as group_covariates  # noqa: E402
import MakeCovariateDeltaTables as delta_tables  # noqa: E402
import MakeRandomiseDesignSpreadsheets as design_sheets  # noqa: E402


class GroupCovariateTests(unittest.TestCase):
    @staticmethod
    def write_events(path: Path, condition: str, pupil: float, blinks: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "onset\tduration\ttrial_type\ttarget\teyeClosed\tnrBlinks\tmeanPupilArea\n"
            f"0\t4\t{condition}\t{condition}\t0.25\t{blinks}\t{pupil}\n"
            f"4\t4\t{condition}\t{condition}\t0.50\t{blinks}\t{pupil + 100}\n"
        )

    def test_group_covariates_fill_conditions_and_compute_contrast_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bids = root / "bids"
            mriqc = root / "mriqc.tsv"
            mriqc.write_text(
                "participant\trun\ttsnr\tfd_mean\tsource\tcondition\n"
                "sub-001\t01\t50\t0.10\tmriqc1.json\t\n"
                "sub-001\t02\t52\t0.20\tmriqc2.json\t\n"
                "sub-001\t03\t54\t0.30\tmriqc3.json\t\n"
                "sub-001\t04\t56\t0.40\tmriqc4.json\t\n"
            )
            for run, condition, pupil, blinks in (
                ("01", "SHAM", 1000.0, 1),
                ("02", "RTPJ", 1100.0, 2),
                ("03", "VLPFC", 1200.0, 3),
                ("04", "BOTH", 1300.0, 4),
            ):
                self.write_events(
                    bids / "sub-001" / "func" / f"sub-001_task-rest_run-{run}_events.tsv",
                    condition,
                    pupil,
                    blinks,
                )

            run_rows = group_covariates.build_run_rows(mriqc, bids, "rest")
            self.assertEqual(
                [row["condition"] for row in run_rows],
                ["sham", "rtpj", "vlpfc", "both"],
            )
            self.assertEqual(run_rows[0]["condition_source"], "events")
            contrast_rows = group_covariates.build_contrast_rows(run_rows)
            both_minus_sham = next(
                row for row in contrast_rows if row["contrast"] == "both-minus-sham"
            )
            self.assertEqual(both_minus_sham["complete"], "true")
            self.assertAlmostEqual(float(both_minus_sham["delta_fd_mean"]), 0.30)
            self.assertAlmostEqual(
                float(both_minus_sham["delta_mean_pupil_area"]), 300.0
            )
            self.assertAlmostEqual(
                float(both_minus_sham["delta_blink_rate_per_min"]), 45.0
            )

    def test_design_spreadsheets_demean_fdmean_ev(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            covariates = root / "covariates.tsv"
            covariates.write_text(
                "participant\tcontrast\tcomplete\tdelta_fd_mean\n"
                "sub-001\tboth-minus-sham\ttrue\t0.10\n"
                "sub-002\tboth-minus-sham\ttrue\t0.30\n"
            )
            covariate_rows = design_sheets.load_covariate_rows(covariates)
            matrix_rows, audit_rows = design_sheets.build_design_rows(
                covariate_rows,
                "both-minus-sham",
                ["sub-001", "sub-002"],
                ["delta_fd_mean"],
            )
            self.assertEqual(matrix_rows[0]["EV1_intercept"], "1")
            self.assertAlmostEqual(
                float(matrix_rows[0]["EV2_delta_fd_mean_demeaned"]), -0.1
            )
            self.assertAlmostEqual(
                float(matrix_rows[1]["EV2_delta_fd_mean_demeaned"]), 0.1
            )
            self.assertEqual(audit_rows[0]["delta_fd_mean_mean"], "0.2")

            output = root / "spreadsheet.tsv"
            design_sheets.write_table(output, matrix_rows, list(matrix_rows[0]))
            with output.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(rows[1]["participant"], "sub-002")

    def test_covariate_delta_tables_flip_vlpfc_minus_rtpj(self):
        rows = [
            {
                "participant": "sub-001",
                "contrast": "rtpj-minus-vlpfc",
                "complete": "true",
                "missing_conditions": "",
                "delta_fd_mean": "0.25",
                "delta_mean_pupil_area": "-20",
                "delta_blink_rate_per_min": "4",
            }
        ]
        deltas = delta_tables.build_delta_rows(rows, ["vlpfc-minus-rtpj"])
        self.assertEqual(deltas[0]["contrast_label"], "VLPFC > RTPJ")
        self.assertEqual(deltas[0]["complete_delta_covariates"], "true")
        self.assertAlmostEqual(float(deltas[0]["delta_fdmean"]), -0.25)
        self.assertAlmostEqual(float(deltas[0]["delta_pupil"]), 20.0)
        self.assertAlmostEqual(float(deltas[0]["delta_blink"]), -4.0)

    def test_covariate_delta_tables_flag_missing_delta_metrics(self):
        rows = [
            {
                "participant": "sub-001",
                "contrast": "both-minus-sham",
                "complete": "true",
                "missing_conditions": "",
                "delta_fd_mean": "0.1",
                "delta_mean_pupil_area": "n/a",
                "delta_blink_rate_per_min": "3",
            }
        ]
        deltas = delta_tables.build_delta_rows(rows, ["both-minus-sham"])
        self.assertEqual(deltas[0]["complete_conditions"], "true")
        self.assertEqual(deltas[0]["complete_delta_covariates"], "false")
        self.assertEqual(deltas[0]["missing_delta_covariates"], "pupil")


if __name__ == "__main__":
    unittest.main()
