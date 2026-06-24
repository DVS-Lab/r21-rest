from __future__ import annotations

import csv
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class QCExclusionTests(unittest.TestCase):
    def test_mean_three_contrast_rule_selects_joint_tsnr_fd_outlier(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "decisions.tsv"
            bounds = root / "bounds.tsv"
            exclude_list = root / "exclude.txt"
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "code" / "select_qc_exclusions.py"),
                    "--mriqc-runs",
                    str(
                        REPO_ROOT
                        / "derivatives"
                        / "qc"
                        / "task-rest_mriqc_outliers.tsv"
                    ),
                    "--output",
                    str(report),
                    "--bounds-output",
                    str(bounds),
                    "--exclude-list",
                    str(exclude_list),
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Participants evaluated: 27", result.stdout)
            self.assertIn("Participants excluded: 1", result.stdout)
            self.assertEqual(
                [
                    line
                    for line in exclude_list.read_text().splitlines()
                    if line and not line.startswith("#")
                ],
                ["sub-218"],
            )
            with report.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 27)
            excluded = [row for row in rows if row["decision"] == "exclude"]
            self.assertEqual([row["participant"] for row in excluded], ["sub-218"])
            self.assertEqual(excluded[0]["n_metric_outliers"], "2")
            self.assertEqual(excluded[0]["tsnr_outlier"], "true")
            self.assertEqual(excluded[0]["fd_mean_outlier"], "true")
            with bounds.open(newline="") as stream:
                bound_rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(bound_rows), 2)
            self.assertEqual({row["n_participants"] for row in bound_rows}, {"27"})
            self.assertEqual(
                {row["metric"] for row in bound_rows}, {"tsnr", "fd_mean"}
            )


if __name__ == "__main__":
    unittest.main()
