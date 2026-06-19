# r21-rest

Preprocessing, quality-control, and resting-state analysis code for the R21
stimulation project.

## Linux Paths

The scripts are ready for the current server layout:

```text
project          /ZPOOL/data/projects/r21-rest
BIDS             /ZPOOL/data/projects/r21-cardgame/bids
derivatives      /ZPOOL/data/projects/r21-rest/derivatives
scratch          /ZPOOL/data/scratch/$USER
fMRIPrep image   /ZPOOL/data/tools/fmriprep-25.2.5.sif
MRIQC image      /ZPOOL/data/tools/mriqc-24.0.2.sif
```

Set the corresponding environment variable only when a default path differs.

## Subject List

Create `code/sublist.txt` from participants with task-rest BOLD data:

```bash
code/list_subjects.sh
```

The batch launchers read this file. Blank lines and `#` comments are allowed.
Use `code/list_subjects.sh --force` to replace an older list. The current BIDS
dataset has 31 participant directories but 29 task-rest participants:
`sub-216` and `sub-232` have no task-rest BOLD data.

## fMRIPrep

fMRIPrep produces CIFTI 91k and native-resolution MNI152NLin6Asym outputs.

```bash
code/run_fmriprep.sh --pilot-one --dry-run
code/run_fmriprep.sh --pilot-one
code/run_fmriprep.sh
```

`code/fmriprep.sh SUBJECT` runs one participant. Batch logs are written under
`derivatives/logs/fmriprep`.

## MRIQC

MRIQC processes T1w and BOLD data without multi-echo options.

```bash
code/run_mriqc.sh --pilot-one --dry-run
code/run_mriqc.sh --pilot-one
code/run_mriqc.sh
code/mriqc_group.sh
```

`code/mriqc.sh SUBJECT` runs one participant. Batch logs are written under
`derivatives/logs/mriqc`.

## Verify Outputs

Check expected outputs for every BIDS run and T1w image:

```bash
code/check_preprocessing_status.py --fail-on-missing
```

The checker verifies fMRIPrep reports, MNI BOLD, CIFTI BOLD, confounds,
preprocessed T1w, FreeSurfer completion, MRIQC reports and IQM JSON files, plus
the MRIQC group CSV and HTML outputs. It derives expected counts from BIDS, so
participants with fewer than four acquired runs are handled correctly.

Write a CSV summary when useful:

```bash
code/check_preprocessing_status.py \
  --output-csv derivatives/preprocessing_status.csv
```

## Extract Confounds

After fMRIPrep is complete:

```bash
python3 code/MakeConfounds.py
```

The script follows the lab's existing `MakeConfounds.py` convention. It keeps:

- cosine high-pass terms;
- non-steady-state regressors;
- six translation/rotation parameters;
- `a_comp_cor_00` through `a_comp_cor_05`;
- framewise displacement.

Missing values are replaced with zero. FSL-ready matrices are written without
headers to `derivatives/fsl/confounds`. The script also creates two parallel,
ordered lists:

```text
derivatives/fsl/melodic_filelist.txt
derivatives/fsl/confound_filelist.txt
```

To use an inclusion list after QA:

```bash
python3 code/MakeConfounds.py --subjects code/included_sublist.txt
```

## Group MELODIC

Review the inclusion list and smoothing decision before the final group ICA.
The generated MELODIC list currently points to the native-resolution
MNI152NLin6Asym fMRIPrep volumes. If 4-mm smoothing is adopted, point
`MELODIC_FILELIST` to the corresponding smoothed-volume list instead.

Render or run automatic dimensionality estimation:

```bash
code/melodic.sh 0 --dry-run
code/melodic.sh 0
```

Run fixed dimensionality 20:

```bash
code/melodic.sh 20
```

Outputs are written to:

```text
derivatives/fsl/melodic-concat_dim-00_task-rest.ica
derivatives/fsl/melodic-concat_dim-20_task-rest.ica
```

## Dual Regression

The modified FSL script takes ordered image and confound lists. For a
stage-1/stage-2 group-mean run without `randomise`:

```bash
code/dual_regression \
  derivatives/fsl/melodic-concat_dim-20_task-rest.ica/melodic_IC \
  1 -1 0 \
  derivatives/fsl/melodic-concat_dim-20_task-rest.dr \
  derivatives/fsl/melodic_filelist.txt \
  derivatives/fsl/confound_filelist.txt
```

Confounds enter stage 2 only. The normal stage-2 outputs retain only the
original network maps.

## Remaining Work

1. Review MRIQC and motion summaries and finalize participant/run exclusions.
2. Decide whether the volumetric MELODIC inputs receive 4-mm smoothing.
3. Match MELODIC components to Smith09, prioritizing DMN, ECN, and left/right
   FPN; cerebellar and sensorimotor networks are secondary.
4. Build run-difference images from BIDS `trial_type` labels.
5. Create the final `randomise` designs and contrasts.

## License

Original project code is licensed under the MIT License. `code/dual_regression`
is derived from FSL and remains subject to the FSL License reproduced in that
file. See `LICENSE` for details.
