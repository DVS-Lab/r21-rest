from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "code"))

import MakeCovariateRandomiseModels as cov_models  # noqa: E402


class CovariateRandomiseModelTests(unittest.TestCase):
    def test_select_participants_excludes_missing_pupil_only_when_requested(self):
        participants = ["sub-001", "sub-002", "sub-003"]
        rows = {
            ("sub-001", "both-minus-sham"): {
                "complete": "true",
                "missing_conditions": "",
                "delta_fd_mean": "0.1",
                "delta_blink_rate_per_min": "1",
                "delta_mean_pupil_area": "10",
            },
            ("sub-002", "both-minus-sham"): {
                "complete": "true",
                "missing_conditions": "",
                "delta_fd_mean": "0.2",
                "delta_blink_rate_per_min": "2",
                "delta_mean_pupil_area": "n/a",
            },
            ("sub-003", "both-minus-sham"): {
                "complete": "true",
                "missing_conditions": "",
                "delta_fd_mean": "0.3",
                "delta_blink_rate_per_min": "3",
                "delta_mean_pupil_area": "30",
            },
        }
        selected, excluded = cov_models.select_participants(
            participants,
            rows,
            "both-minus-sham",
            ["delta_fd_mean", "delta_blink_rate_per_min"],
        )
        self.assertEqual([entry["participant"] for entry in selected], participants)
        self.assertEqual(excluded, [])

        selected, excluded = cov_models.select_participants(
            participants,
            rows,
            "both-minus-sham",
            ["delta_fd_mean", "delta_blink_rate_per_min", "delta_mean_pupil_area"],
        )
        self.assertEqual([entry["participant"] for entry in selected], ["sub-001", "sub-003"])
        self.assertEqual(excluded[0]["participant"], "sub-002")
        self.assertEqual(excluded[0]["reason"], "missing_covariate:delta_mean_pupil_area")

    def test_parse_covariates_rejects_blink_and_pupil_together(self):
        with self.assertRaisesRegex(ValueError, "Do not model"):
            cov_models.parse_covariates("fdmean,blink,pupil")

    def test_demean_covariates_writes_zero_mean_columns(self):
        selected = [
            {"participant": "sub-001", "raw_values": {"delta_fd_mean": 0.1}},
            {"participant": "sub-002", "raw_values": {"delta_fd_mean": 0.3}},
            {"participant": "sub-003", "raw_values": {"delta_fd_mean": 0.5}},
        ]
        rows, means = cov_models.demean_covariates(selected, ["delta_fd_mean"])
        self.assertAlmostEqual(means["delta_fd_mean"], 0.3)
        self.assertAlmostEqual(
            sum(float(row["delta_fd_mean_demeaned"]) for row in rows),
            0.0,
        )

    def test_write_design_files_uses_intercept_plus_covariates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {
                    "randomise_index": "0",
                    "participant": "sub-001",
                    "delta_fd_mean": "0.1",
                    "delta_fd_mean_demeaned": "-0.1",
                },
                {
                    "randomise_index": "1",
                    "participant": "sub-002",
                    "delta_fd_mean": "0.3",
                    "delta_fd_mean_demeaned": "0.1",
                },
            ]
            design_mat, design_con, design_grp = cov_models.write_design_files(
                root, rows, ["delta_fd_mean"]
            )
            self.assertIn("/NumWaves\t2", design_mat.read_text())
            self.assertIn("1.000000e+00\t-1.000000e-01", design_mat.read_text())
            self.assertIn("/PPheights\t\t1.000000e+00\t2.000000e-01", design_mat.read_text())
            self.assertIn("1\t0", design_con.read_text())
            self.assertIn("/NumPoints\t2", design_grp.read_text())

    def test_write_design_template_uses_participant_intercept_and_demeaned_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {
                    "randomise_index": "0",
                    "participant": "sub-001",
                    "delta_fd_mean": "0.1",
                    "delta_fd_mean_demeaned": "-0.1",
                    "delta_blink_rate_per_min": "1.5",
                    "delta_blink_rate_per_min_demeaned": "-0.5",
                },
                {
                    "randomise_index": "1",
                    "participant": "sub-002",
                    "delta_fd_mean": "0.3",
                    "delta_fd_mean_demeaned": "0.1",
                    "delta_blink_rate_per_min": "2.5",
                    "delta_blink_rate_per_min_demeaned": "0.5",
                },
            ]
            manifest_row = cov_models.write_design_template(
                root,
                "rest",
                "cov-fdmean-blink",
                "both-minus-sham",
                rows,
                [],
                ["delta_fd_mean", "delta_blink_rate_per_min"],
            )
            tsv = root / manifest_row["template_tsv"]
            lines = tsv.read_text().splitlines()
            self.assertEqual(
                lines[0],
                "participant\tintercept\tdelta_fd_mean_demeaned\tdelta_blink_rate_per_min_demeaned",
            )
            self.assertEqual(lines[1], "sub-001\t1\t-0.1\t-0.5")
            self.assertIn("_N-02_", tsv.name)
            design_mat = root / manifest_row["template_mat"]
            self.assertIn("/NumWaves\t3", design_mat.read_text())
            self.assertIn("/PPheights\t\t1.000000e+00\t2.000000e-01\t1.000000e+00", design_mat.read_text())
            self.assertEqual(manifest_row["excluded_participants_tsv"], "")
            self.assertFalse(list(root.glob("*_excluded-participants.tsv")))

            manifest_row = cov_models.write_design_template(
                root,
                "rest",
                "cov-fdmean-blink",
                "both-minus-sham",
                rows,
                [{"participant": "sub-003", "reason": "missing_covariate:delta_mean_pupil_area"}],
                ["delta_fd_mean", "delta_blink_rate_per_min"],
            )
            self.assertTrue((root / manifest_row["excluded_participants_tsv"]).is_file())

    def test_run_randomise_launcher_uses_shell_array(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script = cov_models.build_run_randomise_script(
                root,
                [
                    {
                        "group_input": str(root / "group.nii.gz"),
                        "design_mat": str(root / "design.mat"),
                        "design_con": str(root / "design.con"),
                        "design_grp": str(root / "design.grp"),
                        "output_prefix": str(root / "randomise" / "task-rest_model-test"),
                    }
                ],
                root / "mask.nii.gz",
                n_perm=5000,
                cluster_threshold=3.1,
                tfce=False,
            )
            text = script.read_text()
            self.assertIn("cmd=(", text)
            self.assertIn('"${cmd[@]}"', text)
            self.assertIn("-n \"$nperm\"", text)
            self.assertNotIn("        -e ", text)


if __name__ == "__main__":
    unittest.main()
