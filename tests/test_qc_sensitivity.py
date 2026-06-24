from __future__ import annotations

import csv
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class QCSensitivityTests(unittest.TestCase):
    def test_differential_motion_rule_selects_three_participants(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "decisions.tsv"
            bounds = root / "bounds.tsv"
            exclude_list = root / "exclude.txt"
            result = subprocess.run(
                [
                    "python3",
                    str(REPO_ROOT / "code" / "select_qc_sensitivity_exclusions.py"),
                    "--condition-contrasts",
                    str(
                        REPO_ROOT
                        / "derivatives"
                        / "qc"
                        / "task-rest_mriqc_condition_contrasts.tsv"
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
            self.assertIn("Participants excluded from sensitivity: 3", result.stdout)
            self.assertEqual(
                [
                    line
                    for line in exclude_list.read_text().splitlines()
                    if line and not line.startswith("#")
                ],
                ["sub-222", "sub-226", "sub-230"],
            )
            with report.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 27)
            excluded = {
                row["participant"]: int(row["paired_motion_outlier_count"])
                for row in rows
                if row["decision"] == "exclude_sensitivity"
            }
            self.assertEqual(excluded, {"sub-222": 4, "sub-226": 3, "sub-230": 2})
            with bounds.open(newline="") as stream:
                bound_rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(bound_rows), 21)
            self.assertEqual({row["n_complete"] for row in bound_rows}, {"27"})


if __name__ == "__main__":
    unittest.main()
