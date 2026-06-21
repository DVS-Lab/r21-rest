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
            bids = root / "bids"
            fmriprep = root / "derivatives" / "fmriprep-25.2.5"
            func = fmriprep / "sub-001" / "func"
            func.mkdir(parents=True)
            source = func / "sub-001_task-rest_run-01_desc-confounds_timeseries.tsv"
            bold = func / "sub-001_task-rest_run-01_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
            bold.write_text("image\n")
            events = bids / "sub-001" / "func" / "sub-001_task-rest_run-01_events.tsv"
            events.parent.mkdir(parents=True)
            events.write_text("onset\tduration\ttrial_type\n0\t1\tRTPJ\n")

            columns = (
                ["cosine00", "non_steady_state_outlier00"]
                + confounds.MOTION_24
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
                bids,
                fmriprep,
                output_dir,
                "rest",
                "MNI152NLin6Asym",
                {"sub-001"},
            )
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].condition, "rtpj")
            self.assertEqual(runs[0].condition_order, 2)
            self.assertIn("condition-rtpj", runs[0].fsl_confounds.name)
            self.assertEqual(runs[0].fsl_confounds.suffix, ".1D")
            selected = confounds.extract_confounds(
                runs[0].source_confounds, runs[0].fsl_confounds
            )
            self.assertEqual(
                selected,
                ["cosine00", "non_steady_state_outlier00"]
                + confounds.MOTION_24
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
            manifest = output_dir.parent / "task-rest_run_manifest.tsv"
            confounds.write_manifest(manifest, runs)
            self.assertEqual(melodic_list.read_text().strip(), str(bold.resolve()))
            self.assertEqual(
                confound_list.read_text().strip(), str(runs[0].fsl_confounds.resolve())
            )
            with manifest.open() as stream:
                manifest_rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(manifest_rows[0]["acquired_run"], "01")
            self.assertEqual(manifest_rows[0]["condition"], "rtpj")

    def test_condition_parser_rejects_empty_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.tsv"
            events.write_text("onset\tduration\ttrial_type\n")
            with self.assertRaisesRegex(ValueError, "found none"):
                confounds.condition_from_events(events)

    def test_numeric_value_rejects_nonfinite_values(self):
        source = Path("confounds.tsv")
        with self.assertRaisesRegex(ValueError, "non-finite value"):
            confounds.numeric_value("inf", source, 2, "framewise_displacement")

    def test_run_lists_follow_condition_order_not_acquisition_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bids = root / "bids"
            fmriprep = root / "fmriprep"
            output = root / "fsl" / "confounds"
            for run, condition in (("01", "VLPFC"), ("02", "SHAM")):
                prefix = f"sub-001_task-rest_run-{run}"
                func = fmriprep / "sub-001" / "func"
                func.mkdir(parents=True, exist_ok=True)
                (func / f"{prefix}{confounds.CONFOUND_SUFFIX}").touch()
                (
                    func
                    / f"{prefix}_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
                ).touch()
                events = bids / "sub-001" / "func" / f"{prefix}_events.tsv"
                events.parent.mkdir(parents=True, exist_ok=True)
                events.write_text(
                    f"onset\tduration\ttrial_type\n0\t1\t{condition}\n"
                )

            runs = confounds.find_runs(
                bids, fmriprep, output, "rest", "MNI152NLin6Asym", None
            )
            self.assertEqual(
                [(run.condition, run.acquired_run) for run in runs],
                [("sham", "02"), ("vlpfc", "01")],
            )
            with self.assertRaisesRegex(ValueError, "Incomplete condition sets"):
                confounds.validate_condition_sets(runs)

    def test_skips_participants_without_complete_condition_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bids = root / "bids"
            fmriprep = root / "fmriprep"
            output = root / "fsl" / "confounds"

            for participant in ("sub-001", "sub-002"):
                for index, condition in enumerate(
                    ("SHAM", "RTPJ", "VLPFC", "BOTH"), start=1
                ):
                    run = f"{index:02d}"
                    prefix = f"{participant}_task-rest_run-{run}"
                    func = fmriprep / participant / "func"
                    func.mkdir(parents=True, exist_ok=True)
                    (func / f"{prefix}{confounds.CONFOUND_SUFFIX}").touch()
                    (
                        func
                        / f"{prefix}_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
                    ).touch()
                    events = bids / participant / "func" / f"{prefix}_events.tsv"
                    events.parent.mkdir(parents=True, exist_ok=True)
                    if participant == "sub-002":
                        events.write_text("onset\tduration\ttrial_type\n")
                    else:
                        events.write_text(
                            f"onset\tduration\ttrial_type\n0\t1\t{condition}\n"
                        )

            runs, skipped = confounds.find_eligible_runs(
                bids,
                fmriprep,
                output,
                "rest",
                "MNI152NLin6Asym",
                None,
            )

            self.assertEqual(len(runs), 4)
            self.assertEqual({run.participant for run in runs}, {"sub-001"})
            self.assertIn("sub-002", skipped)
            self.assertIn("found none", skipped["sub-002"])

            report = root / "skipped.tsv"
            confounds.write_skipped_subjects(report, skipped)
            with report.open() as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(rows[0]["participant"], "sub-002")


if __name__ == "__main__":
    unittest.main()
