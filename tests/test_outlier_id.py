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
                ("001", "01", 10, 0.10),
                ("002", "01", 100, 0.11),
                ("003", "01", 110, 0.12),
                ("004", "01", 120, 0.13),
                ("005", "01", 1000, 0.90),
            ]
            for subject, run, tsnr, fd_mean in values:
                path = (
                    mriqc
                    / f"sub-{subject}"
                    / "func"
                    / f"sub-{subject}_task-rest_run-{run}_bold.json"
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {"tsnr": tsnr, "fd_mean": fd_mean}
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

    def test_reads_condition_from_matching_events_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mriqc_file = (
                root
                / "mriqc"
                / "sub-001"
                / "func"
                / "sub-001_task-rest_run-01_bold.json"
            )
            events_file = (
                root
                / "bids"
                / "sub-001"
                / "func"
                / "sub-001_task-rest_run-01_events.tsv"
            )
            mriqc_file.parent.mkdir(parents=True)
            events_file.parent.mkdir(parents=True)
            mriqc_file.write_text(json.dumps({"tsnr": 50, "fd_mean": 0.1}))
            events_file.write_text("onset\tduration\ttrial_type\n0\t1\tboth\n")

            runs = outliers.read_iqms(root / "mriqc", "rest", root / "bids")

        self.assertEqual(runs[0].condition, "both")

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
                source=f"sub-002-run-{run}",
            )
            for run in range(1, 3)
        )

        subjects = outliers.summarize_subjects(runs)
        by_subject = {subject.participant: subject for subject in subjects}
        self.assertEqual(by_subject["sub-001"].n_runs, 4)
        self.assertEqual(by_subject["sub-001"].mean_tsnr, 42.5)

        with tempfile.TemporaryDirectory() as tmp:
            rows = outliers.write_subject_report(
                Path(tmp) / "subjects.tsv",
                subjects,
                tsnr_lower=0,
                fd_upper=10,
                expected_runs=4,
                fd_threshold=0.5,
                tsnr_threshold=30,
            )
        reports = {row["participant"]: row for row in rows}
        self.assertEqual(reports["sub-001"]["incomplete_runs"], "false")
        self.assertEqual(reports["sub-002"]["incomplete_runs"], "true")

    def test_condition_contrasts_flag_unusual_paired_differences(self):
        runs = []
        for subject in range(1, 6):
            for condition in ("sham", "rtpj", "vlpfc", "both"):
                tsnr = 50.0
                fd_mean = 0.1
                if subject == 5 and condition == "both":
                    tsnr = 20.0
                    fd_mean = 0.8
                runs.append(
                    outliers.RunIQM(
                        participant=f"sub-{subject:03d}",
                        session="",
                        task="rest",
                        acquisition="",
                        run="01",
                        echo="",
                        tsnr=tsnr,
                        fd_mean=fd_mean,
                        source=f"sub-{subject:03d}-{condition}",
                        condition=condition,
                    )
                )

        contrasts = outliers.calculate_condition_contrasts(runs)
        self.assertEqual(len(contrasts), 35)
        bounds = outliers.condition_contrast_bounds(contrasts)
        with tempfile.TemporaryDirectory() as tmp:
            rows = outliers.write_condition_contrast_report(
                Path(tmp) / "contrasts.tsv", contrasts, bounds
            )

        by_key = {(row["participant"], row["contrast"]): row for row in rows}
        flagged = by_key[("sub-005", "both_minus_sham")]
        self.assertEqual(flagged["delta_tsnr"], "-30")
        self.assertEqual(flagged["delta_fd_mean"], "0.7")
        self.assertEqual(flagged["delta_tsnr_outlier"], "true")
        self.assertEqual(flagged["delta_fd_mean_outlier"], "true")
        self.assertEqual(flagged["review"], "true")
        self.assertIn(("both_minus_rtpj", "fd_mean"), bounds)
        self.assertIn(("both_minus_vlpfc", "fd_mean"), bounds)
        self.assertIn(("rtpj_minus_sham", "fd_mean"), bounds)
        self.assertIn(("vlpfc_minus_sham", "fd_mean"), bounds)

    def test_condition_contrasts_mark_missing_conditions_for_review(self):
        runs = [
            outliers.RunIQM(
                participant="sub-001",
                session="",
                task="rest",
                acquisition="",
                run="01",
                echo="",
                tsnr=50,
                fd_mean=0.1,
                source="sub-001-sham",
                condition="sham",
            )
        ]
        contrasts = outliers.calculate_condition_contrasts(runs)
        self.assertEqual(len(contrasts), 7)
        self.assertTrue(all(not contrast.complete for contrast in contrasts))


if __name__ == "__main__":
    unittest.main()
