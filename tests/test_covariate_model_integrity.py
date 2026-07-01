from __future__ import annotations

import csv
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "code" / "check_covariate_model_integrity.py"


class CovariateModelIntegrityTests(unittest.TestCase):
    @staticmethod
    def write_command(path: Path, body: str) -> None:
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def test_audits_design_demeaning_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fsl_dir = root / "derivatives" / "fsl"
            dr_dir = fsl_dir / "dual-regression_smith09_denoised.dr"
            model_dir = (
                dr_dir
                / "contrasts"
                / "component-0004_stat-beta"
                / "covariate-models"
                / "model-cov-fdmean-blink"
            )
            contrast_dir = model_dir / "rtpj-minus-vlpfc"
            contrast_dir.mkdir(parents=True)
            (dr_dir / "mask.nii.gz").write_text("mask")

            group_input = contrast_dir / "group_task-rest_component-0004_stat-beta_contrast-rtpj-minus-vlpfc_model-cov-fdmean-blink.nii.gz"
            design_mat = contrast_dir / "design.mat"
            design_con = contrast_dir / "design.con"
            design_grp = contrast_dir / "design.grp"
            image_list = contrast_dir / "image_list.txt"
            subject_order = contrast_dir / "subject_order.tsv"
            audit = contrast_dir / "covariate_audit.tsv"
            group_input.write_text("group")
            design_grp.write_text("unused\n")
            design_mat.write_text(
                "/NumWaves\t3\n"
                "/NumPoints\t2\n\n"
                "/Matrix\n"
                "1\t-0.1\t-2.0\n"
                "1\t0.1\t2.0\n"
            )
            design_con.write_text(
                "/ContrastName1\tmean_pos\n"
                "/ContrastName2\tmean_neg\n"
                "/ContrastName3\tcov_pos\n"
                "/ContrastName4\tcov_neg\n"
                "/NumWaves\t3\n"
                "/NumContrasts\t4\n\n"
                "/Matrix\n"
                "1\t0\t0\n"
                "-1\t0\t0\n"
                "0\t0\t1\n"
                "0\t0\t-1\n"
            )
            audit.write_text(
                "randomise_index\tparticipant\tdelta_fd_mean\tdelta_fd_mean_demeaned\tdelta_blink_rate_per_min\tdelta_blink_rate_per_min_demeaned\n"
                "0\tsub-001\t0.2\t-0.1\t4\t-2.0\n"
                "1\tsub-002\t0.4\t0.1\t8\t2.0\n"
            )
            subject_order.write_text("randomise_index\tparticipant\n0\tsub-001\n1\tsub-002\n")
            image_list.write_text(
                "/tmp/sub-001_task-rest_contrast-rtpj-minus-vlpfc.nii.gz\n"
                "/tmp/sub-002_task-rest_contrast-rtpj-minus-vlpfc.nii.gz\n"
            )
            (model_dir / "randomise_jobs.tsv").write_text(
                "contrast\tnetwork\tgroup_input\tdesign_mat\tdesign_con\tdesign_grp\toutput_prefix\n"
                f"rtpj-minus-vlpfc\tdmn\t{group_input}\t{design_mat}\t{design_con}\t{design_grp}\t{model_dir / 'randomise' / 'job'}\n"
            )

            fakebin = root / "bin"
            fakebin.mkdir()
            self.write_command(fakebin / "fslnvols", "echo 2\n")
            self.write_command(fakebin / "fslstats", "echo '12345 98760'\n")

            output_dir = fsl_dir / "covariate_randomise_summary"
            result = subprocess.run(
                [
                    "python3",
                    str(CHECKER),
                    "--fsl-dir",
                    str(fsl_dir),
                    "--output-dir",
                    str(output_dir),
                    "--fail-on-error",
                ],
                env=os.environ | {"PATH": f"{fakebin}:{os.environ['PATH']}"},
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Complete integrity rows: 1/1", result.stdout)
            summary = output_dir / "task-rest_covariate-randomise_integrity.tsv"
            with summary.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(rows[0]["complete"], "true")
            self.assertEqual(rows[0]["covariate_columns_demeaned"], "true")
            self.assertEqual(rows[0]["design_matches_covariate_audit"], "true")
            self.assertEqual(rows[0]["subject_order_matches_audit"], "true")
            self.assertEqual(rows[0]["image_list_matches_audit"], "true")
            self.assertEqual(rows[0]["mask_voxels"], "12345")


if __name__ == "__main__":
    unittest.main()
