from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "code" / "OutlierID.py"
SPEC = importlib.util.spec_from_file_location("outlier_id", MODULE_PATH)
outliers = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = outliers
SPEC.loader.exec_module(outliers)


class OutlierIDTests(unittest.TestCase):
    def test_percentile_uses_linear_interpolation(self):
        self.assertEqual(outliers.percentile([1, 2, 3, 4, 5], 0.25), 2)
        self.assertEqual(outliers.percentile([1, 2, 3, 4], 0.25), 1.75)

    def test_flags_only_low_tsnr_and_high_fd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mriqc = root / "mriqc"
            values = [
                ("001", "01", 10, 0.10, 1, 1),
                ("002", "01", 100, 0.11, 2, 2),
                ("003", "01", 110, 0.12, 3, 3),
                ("004", "01", 120, 0.13, 4, 4),
                ("005", "01", 1000, 0.90, 90, 75),
            ]
            for subject, run, tsnr, fd_mean, fd_num, fd_perc in values:
                path = (
                    mriqc
                    / f"sub-{subject}"
                    / "func"
                    / f"sub-{subject}_task-rest_run-{run}_bold.json"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "tsnr": tsnr,
                            "fd_mean": fd_mean,
                            "fd_num": fd_num,
                            "fd_perc": fd_perc,
                        }
                    )
                )

            runs = outliers.read_iqms(mriqc, "rest")
            tsnr_bounds = outliers.tukey_bounds([run.tsnr for run in runs])
            fd_bounds = outliers.tukey_bounds([run.fd_mean for run in runs])
            report = root / "outliers.tsv"
            rows = outliers.write_run_report(
                report, runs, tsnr_bounds[3], fd_bounds[4], 0.5, 30
            )

            by_subject = {row["participant"]: row for row in rows}
            self.assertEqual(by_subject["sub-001"]["low_tsnr"], "true")
            self.assertEqual(by_subject["sub-001"]["high_fd_mean"], "false")
            self.assertEqual(by_subject["sub-005"]["low_tsnr"], "false")
            self.assertEqual(by_subject["sub-005"]["high_fd_mean"], "true")
            self.assertEqual(by_subject["sub-005"]["fd_mean_gt_0.5"], "true")
            self.assertEqual(by_subject["sub-005"]["fd_perc_gt_50"], "true")

    def test_subject_diagnostics_average_runs_and_flag_incomplete_subjects(self):
        runs = [
            outliers.RunIQM(
                participant="sub-001",
                session="",
                task="rest",
                acquisition="",
                run=f"0{run}",
                echo="",
                tsnr=40 + run,
                fd_mean=0.1 * run,
                fd_num=run,
                fd_perc=10 * run,
                source=f"sub-001-run-{run}",
            )
            for run in range(1, 5)
        ]
        runs.extend(
            outliers.RunIQM(
                participant="sub-002",
                session="",
                task="rest",
                acquisition="",
                run=f"0{run}",
                echo="",
                tsnr=50,
                fd_mean=0.1,
                fd_num=1,
                fd_perc=5,
                source=f"sub-002-run-{run}",
            )
            for run in range(1, 3)
        )

        subjects = outliers.summarize_subjects(runs)
        by_subject = {subject.participant: subject for subject in subjects}
        self.assertEqual(by_subject["sub-001"].n_runs, 4)
        self.assertEqual(by_subject["sub-001"].mean_tsnr, 42.5)
        self.assertEqual(by_subject["sub-001"].mean_fd_perc, 25)

        with tempfile.TemporaryDirectory() as tmp:
            rows = outliers.write_subject_report(
                Path(tmp) / "subjects.tsv",
                subjects,
                tsnr_lower=0,
                fd_upper=10,
                fd_perc_upper=100,
                expected_runs=4,
                fd_threshold=0.5,
                fd_perc_threshold=20,
                tsnr_threshold=30,
            )
        reports = {row["participant"]: row for row in rows}
        self.assertEqual(reports["sub-001"]["incomplete_runs"], "false")
        self.assertEqual(
            reports["sub-001"]["mean_fd_perc_gt_review_threshold"], "true"
        )
        self.assertEqual(reports["sub-002"]["incomplete_runs"], "true")


if __name__ == "__main__":
    unittest.main()
