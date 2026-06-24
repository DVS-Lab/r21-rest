from __future__ import annotations

import csv
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class QCExclusionTests(unittest.TestCase):
    def test_three_metric_boxplot_rule_excludes_nobody(self):
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
            self.assertIn("Participants excluded: 0", result.stdout)
            self.assertEqual(
                [
                    line
                    for line in exclude_list.read_text().splitlines()
                    if line and not line.startswith("#")
                ],
                [],
            )
            with report.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 27)
            self.assertFalse(any(row["decision"] == "exclude" for row in rows))
            counts = {
                row["participant"]: int(row["n_metric_outliers"])
                for row in rows
                if int(row["n_metric_outliers"]) > 0
            }
            self.assertEqual(
                counts,
                {
                    "sub-218": 2,
                    "sub-222": 1,
                    "sub-226": 1,
                    "sub-230": 2,
                    "sub-236": 1,
                    "sub-238": 1,
                },
            )
            with bounds.open(newline="") as stream:
                bound_rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(bound_rows), 3)
            self.assertEqual({row["n_participants"] for row in bound_rows}, {"27"})
            self.assertEqual(
                {row["metric"] for row in bound_rows}, {"tsnr", "fd_mean", "fd_perc"}
            )


if __name__ == "__main__":
    unittest.main()
