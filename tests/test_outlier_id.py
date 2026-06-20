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
                path.write_text(json.dumps({"tsnr": tsnr, "fd_mean": fd_mean}))

            runs = outliers.read_iqms(mriqc, "rest")
            tsnr_bounds = outliers.tukey_bounds([run.tsnr for run in runs])
            fd_bounds = outliers.tukey_bounds([run.fd_mean for run in runs])
            report = root / "outliers.tsv"
            rows = outliers.write_run_report(
                report, runs, tsnr_bounds[3], fd_bounds[4], 0.5
            )

            by_subject = {row["participant"]: row for row in rows}
            self.assertEqual(by_subject["sub-001"]["low_tsnr"], "true")
            self.assertEqual(by_subject["sub-001"]["high_fd_mean"], "false")
            self.assertEqual(by_subject["sub-005"]["low_tsnr"], "false")
            self.assertEqual(by_subject["sub-005"]["high_fd_mean"], "true")
            self.assertEqual(by_subject["sub-005"]["fd_mean_gt_0.5"], "true")


if __name__ == "__main__":
    unittest.main()
