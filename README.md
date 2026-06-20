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

## MRIQC Outliers

Summarize the completed task-rest MRIQC outputs:

```bash
python3 code/OutlierID.py
```

The script follows the lab's existing `OutlierID.py` approach while making the
rules directional: only unusually low tSNR and unusually high mean framewise
displacement are flagged. Tukey 1.5-IQR fences are calculated across all
task-rest runs; mean FD above 0.5 mm is also flagged. No participant or run is
excluded automatically.

Review the three output tables in `derivatives/qc`:

```text
task-rest_mriqc_outliers.tsv
task-rest_mriqc_bounds.tsv
task-rest_mriqc_subject_summary.tsv
```

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

This also restricts the two ordered FSL input lists to the reviewed sample.

## Smooth To 5 mm

After extracting confounds, smooth every run in the ordered MELODIC list to a
final 5-mm FWHM with AFNI `3dBlurToFWHM`:

```bash
code/run_smooth-3dBlurToFWHM.sh --dry-run
code/run_smooth-3dBlurToFWHM.sh
```

`code/smooth-3dBlurToFWHM.sh SUBJECT RUN` handles one run. It uses the matching
fMRIPrep brain mask and an isolated work directory under
`/ZPOOL/data/scratch/$USER/r21-rest/smoothing`, avoiding conflicts from AFNI's
temporary `3dFWHMx.1D` files. Smoothed images are written beside their original
fMRIPrep images with a `_5mm.nii.gz` suffix. The batch script writes the ordered
list `derivatives/fsl/melodic_filelist_5mm.txt` only after all requested outputs
exist.

## Group MELODIC

`code/melodic.sh` uses `derivatives/fsl/melodic_filelist_5mm.txt` by default.
Run temporal-concatenation MELODIC both with automatic dimensionality and with
20 fixed components:

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

Set `MELODIC_FILELIST` only when intentionally testing a different ordered
image list.

## Match Smith09 Networks

The original Smith09 10-network image is stored in `masks`. For each completed
MELODIC analysis, resample those maps to the exact MELODIC grid and calculate
signed spatial correlations with `fslcc`:

```bash
code/match_smith09.sh 0 --dry-run
code/match_smith09.sh 0
code/match_smith09.sh 20
```

Results are written to `derivatives/fsl/smith09_dim-00_task-rest` and
`derivatives/fsl/smith09_dim-20_task-rest`. Each directory contains the raw
`fslcc` output, the resampled 10-network image, a complete labeled correlation
matrix, and `smith09_best_matches.tsv`. The best-match table marks DMN, ECN,
and left/right FPN as primary networks and cerebellar and sensorimotor maps as
secondary networks. Component selection still requires visual review.

## Dual Regression

The modified FSL script takes ordered image and confound lists. For a
stage-1/stage-2 group-mean run without `randomise`:

```bash
code/dual_regression \
  derivatives/fsl/melodic-concat_dim-20_task-rest.ica/melodic_IC \
  1 -1 0 \
  derivatives/fsl/melodic-concat_dim-20_task-rest.dr \
  derivatives/fsl/melodic_filelist_5mm.txt \
  derivatives/fsl/confound_filelist.txt
```

Confounds enter stage 2 only. The normal stage-2 outputs retain only the
original network maps.

## Remaining Work

1. Review MRIQC flags, the fMRIPrep reports, and the stimulation-delivery note;
   then create `code/included_sublist.txt`.
2. Extract confounds, smooth to 5 mm, and run both group MELODIC analyses.
3. Review the Smith09 correlations and component spatial maps.
4. Build run-difference images from BIDS `trial_type` labels.
5. Create the final `randomise` designs and contrasts.

## License

Original project code is licensed under the MIT License. `code/dual_regression`
is derived from FSL and remains subject to the FSL License reproduced in that
file. See `LICENSE` for details.
