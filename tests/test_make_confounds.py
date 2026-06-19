from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "code" / "MakeConfounds.py"
SPEC = importlib.util.spec_from_file_location("make_confounds", MODULE_PATH)
confounds = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = confounds
SPEC.loader.exec_module(confounds)


class MakeConfoundsTests(unittest.TestCase):
    def test_extracts_lab_columns_and_builds_parallel_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fmriprep = root / "derivatives" / "fmriprep-25.2.5"
            func = fmriprep / "sub-001" / "func"
            func.mkdir(parents=True)
            source = func / "sub-001_task-rest_run-01_desc-confounds_timeseries.tsv"
            bold = func / "sub-001_task-rest_run-01_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
            bold.write_text("image\n")

            columns = (
                ["cosine00", "non_steady_state_outlier00"]
                + confounds.MOTION
                + confounds.ACOMPCOR
                + ["framewise_displacement", "dvars"]
            )
            with source.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t")
                writer.writeheader()
                writer.writerow({column: "1" for column in columns} | {"framewise_displacement": "n/a"})
                writer.writerow({column: "2" for column in columns})

            output_dir = root / "derivatives" / "fsl" / "confounds"
            runs = confounds.find_runs(
                fmriprep, output_dir, "rest", "MNI152NLin6Asym", {"sub-001"}
            )
            self.assertEqual(len(runs), 1)
            selected = confounds.extract_confounds(
                runs[0].source_confounds, runs[0].fsl_confounds
            )
            self.assertEqual(
                selected,
                ["cosine00", "non_steady_state_outlier00"]
                + confounds.MOTION
                + confounds.ACOMPCOR
                + ["framewise_displacement"],
            )

            with runs[0].fsl_confounds.open() as stream:
                rows = list(csv.reader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(rows[0]), len(selected))
            self.assertEqual(rows[0][-1], "0")

            melodic_list = output_dir.parent / "melodic_filelist.txt"
            confound_list = output_dir.parent / "confound_filelist.txt"
            confounds.write_filelist(melodic_list, [runs[0].bold])
            confounds.write_filelist(confound_list, [runs[0].fsl_confounds])
            self.assertEqual(melodic_list.read_text().strip(), str(bold.resolve()))
            self.assertEqual(
                confound_list.read_text().strip(), str(runs[0].fsl_confounds.resolve())
            )


if __name__ == "__main__":
    unittest.main()
