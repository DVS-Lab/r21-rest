from __future__ import annotations

import csv
import importlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "code" / "MakeNetworkCorrelationTables.py"


class NetworkCorrelationTests(unittest.TestCase):
    def test_extracts_full_and_partial_condition_correlation_contrasts(self):
        try:
            np = importlib.import_module("numpy")
        except ModuleNotFoundError:
            self.skipTest("numpy is not installed in this Python environment")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dr_dir = root / "dual-regression_smith09_denoised.dr"
            dr_dir.mkdir()
            rows = [
                "dual_regression_index\tdual_regression_label\tparticipant\trun\tcondition\tcondition_order\tfile"
            ]
            rng = np.random.default_rng(1234)
            rhos = {"sham": 0.1, "rtpj": 0.2, "vlpfc": 0.3, "both": 0.6}
            for index, condition in enumerate(("sham", "rtpj", "vlpfc", "both")):
                label = f"subject{index:05d}"
                rows.append(
                    f"{index}\t{label}\tsub-001\t{index + 1:02d}\t{condition}\t{index + 1}\tinput.nii.gz"
                )
                base = rng.normal(size=80)
                noise = rng.normal(size=80)
                matrix = rng.normal(size=(80, 10))
                matrix[:, 3] = base
                matrix[:, 7] = rhos[condition] * base + (1.0 - rhos[condition]) * noise
                np.savetxt(dr_dir / f"dr_stage1_{label}.txt", matrix, fmt="%.8f")
            (dr_dir / "input_order.tsv").write_text("\n".join(rows) + "\n")

            output_dir = root / "summary"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--dr-dir",
                    str(dr_dir),
                    "--analysis",
                    "smith09_denoised",
                    "--network-set",
                    "dmn-ecn",
                    "--output-dir",
                    str(output_dir),
                    "--n-perm",
                    "99",
                    "--fail-on-missing",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Network pairs: 1", result.stdout)
            self.assertIn("Run correlation rows: 8", result.stdout)

            run_values = output_dir / (
                "task-rest_analysis-smith09_denoised_network-correlation_run-values.tsv"
            )
            with run_values.open(newline="") as stream:
                run_rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(run_rows), 8)
            self.assertEqual({row["correlation_type"] for row in run_rows}, {"full", "partial"})
            self.assertEqual({row["network_pair"] for row in run_rows}, {"dmn__ecn"})
            self.assertEqual({row["condition"] for row in run_rows}, {"sham", "rtpj", "vlpfc", "both"})

            contrasts = output_dir / (
                "task-rest_analysis-smith09_denoised_network-correlation_condition-contrasts.tsv"
            )
            with contrasts.open(newline="") as stream:
                contrast_rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(contrast_rows), 14)
            both_minus_sham = [
                row
                for row in contrast_rows
                if row["correlation_type"] == "full"
                and row["condition_contrast"] == "both-minus-sham"
            ][0]
            self.assertEqual(both_minus_sham["complete"], "true")
            self.assertGreater(float(both_minus_sham["delta_fisher_z"]), 0.0)

            summary = output_dir / (
                "task-rest_analysis-smith09_denoised_network-correlation_summary.tsv"
            )
            with summary.open(newline="") as stream:
                summary_rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(summary_rows), 14)
            self.assertEqual({row["n"] for row in summary_rows}, {"1"})
            self.assertTrue((output_dir / "README.md").is_file())


if __name__ == "__main__":
    unittest.main()
