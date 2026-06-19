# r21-rest

Code for preprocessing, quality assessment, and later dual-regression analyses
of the R21 resting-state stimulation data.

The launchers intentionally follow the simple lab pattern used in related
projects:

- `code/fmriprep.sh` runs fMRIPrep for one subject.
- `code/run_fmriprep.sh` runs fMRIPrep over `code/sublist.txt`.
- `code/mriqc.sh` runs MRIQC for one subject.
- `code/run_mriqc.sh` runs MRIQC over `code/sublist.txt`.
- `code/mriqc_group.sh` runs the MRIQC group report.

The scripts are meant to run on the Linux server. On a Mac or other review
machine, use `--dry-run` or `--render-only`.

## Defaults

The launchers are ready for the current Linux layout:

```bash
project root      /ZPOOL/data/projects/r21-rest
BIDS input        /ZPOOL/data/projects/r21-cardgame/bids
derivatives       /ZPOOL/data/projects/r21-rest/derivatives
work/scratch      /ZPOOL/data/scratch/$USER
fMRIPrep image    /ZPOOL/data/tools/fmriprep-25.2.5.sif
MRIQC image       /ZPOOL/data/tools/mriqc-24.0.2.sif
TemplateFlow      /ZPOOL/data/tools/templateflow
FreeSurfer key    /ZPOOL/data/tools/licenses/fs_license.txt
```

Outputs are written inside the project derivatives folder:

```bash
derivatives/fmriprep-25.2.5
derivatives/freesurfer
derivatives/mriqc
derivatives/logs
```

fMRIPrep defaults to CIFTI 91k and the requested output spaces:

```bash
--cifti-output 91k
--output-spaces fsLR MNI152NLin6Asym
```

MRIQC defaults to:

```bash
--modalities T1w bold
--no-datalad-get
--no-sub
```

This is not treated as multi-echo data, and no multi-echo options are passed.

## Subject List

Create the subject list on Linux:

```bash
code/list_subjects.sh --output code/sublist.txt
```

Subject labels may be written as `189` or `sub-189`. Blank lines and `#`
comments are allowed.

## fMRIPrep

Render one pilot command:

```bash
code/run_fmriprep.sh --pilot-one --dry-run
```

Run one pilot subject:

```bash
code/run_fmriprep.sh --pilot-one
```

Run the batch:

```bash
code/run_fmriprep.sh
```

Use `--max-jobs N` to change concurrency. The script refuses more than five
concurrent jobs.

## MRIQC

Render one pilot command:

```bash
code/run_mriqc.sh --pilot-one --dry-run
```

Run one pilot subject:

```bash
code/run_mriqc.sh --pilot-one
```

Run MRIQC for the full subject list:

```bash
code/run_mriqc.sh
```

After participant-level MRIQC finishes, run the group report:

```bash
code/mriqc_group.sh
```

Logs are written to `derivatives/logs/mriqc`.

## Useful Overrides

The default paths should work as-is on the Linux server. If a path differs, set
an environment variable when launching:

```bash
BIDS_DIR=/path/to/bids code/run_mriqc.sh --pilot-one
TEMPLATEFLOW_DIR=/ZPOOL/data/scratch/$USER/templateflow code/run_mriqc.sh
MRIQC_MAX_JOBS=2 code/run_mriqc.sh
```

`config/linux.env.example` is kept as a readable record for preflight/status
tools. It should not need editing for the standard Linux layout.

## Status Checks

Summarize expected fMRIPrep and MRIQC outputs:

```bash
code/check_preprocessing_status.py --subjects code/sublist.txt
```

The checker reports fMRIPrep HTML, preprocessed BOLD files, confounds files, and
MRIQC HTML files. Marker columns may remain `missing` with the simplified
launchers; use the output-file counts to track actual completion.

## Next Analysis Steps

After preprocessing/QC:

1. Extract the lab-standard fMRIPrep confounds.
2. Amend the FSL `dual_regression` workflow to accept those confounds.
3. Review MRIQC and motion summaries before excluding any of the 31 subjects.
4. Run group-level MELODIC on the included data.
5. Match components to Smith09 PNAS networks, prioritizing DMN, ECN, and left
   and right FPN.
6. Build run-difference images from the `trial_type` labels in the BIDS events
   files, then pass those images to `randomise`.

## License

Original project code is licensed under the MIT License. `code/dual_regression`
is derived from FSL and remains subject to the FSL License reproduced in that
file. See `LICENSE` for details.
