# Code Guide

Run commands from the project root. Unless an override is documented in the
main `README.md`, inputs come from the BIDS dataset or an earlier step under
`derivatives`, and generated outputs remain under `derivatives`.

## Workflow Order

1. Create the participant list and run fMRIPrep and MRIQC.
2. Check preprocessing completion and review MRIQC diagnostics.
3. Extract confounds, smooth and mask the BOLD data, then regress confounds.
4. Check the denoised inputs and run both group-MELODIC solutions.
5. Match ICA components to Smith09 and run dual regression.
6. Construct within-participant condition differences.
7. Run one-sample permutation tests and plot the corrected results.

## Preprocessing

| File | Input | Purpose and output |
|---|---|---|
| `list_subjects.sh` | BIDS `sub-*` directories | Writes `code/sublist.txt` for participants with task-rest BOLD data. |
| `sublist.example.txt` | None | Example participant-list format; blank lines and comments are allowed. |
| `fmriprep.sh` | One participant label | Runs fMRIPrep for one participant and writes project derivatives. |
| `run_fmriprep.sh` | `code/sublist.txt` | Runs `fmriprep.sh` across the participant list with bounded concurrency. |
| `mriqc.sh` | One participant label | Runs participant-level MRIQC. |
| `run_mriqc.sh` | `code/sublist.txt` | Runs participant-level MRIQC across the list. |
| `mriqc_group.sh` | Completed MRIQC outputs | Creates the MRIQC group tables and reports. |
| `check_preprocessing_status.py` | BIDS, fMRIPrep, and MRIQC outputs | Reports expected versus present outputs for every participant. |

## Quality Control and Denoising

| File | Input | Purpose and output |
|---|---|---|
| `OutlierID.py` | MRIQC BOLD IQMs and BIDS events | Writes run-, participant-, and condition-difference QC tables under `derivatives/qc`. |
| `MakeConfounds.py` | fMRIPrep confounds and BIDS events | Writes FSL/AFNI confound matrices, the ordered run manifest, and input lists. |
| `smooth-3dBlurToFWHM.sh` | One fMRIPrep BOLD run and mask | Masks and smooths one run to 5-mm FWHM while adding its condition label. |
| `run_smooth-3dBlurToFWHM.sh` | Ordered run manifest | Runs the single-run smoothing script across all included runs. |
| `regress_confounds.sh` | One smoothed run and confound matrix | Uses `3dTproject` to write one denoised BOLD run. |
| `run_regress_confounds.sh` | Ordered run manifest | Denoises every run and writes `melodic_filelist_5mm_denoised.txt`. |
| `check_melodic_inputs.sh` | Denoised MELODIC file list | Checks grids, masks, volumes, intensity, and variance; writes a QC TSV. |

## ICA and Network Matching

| File | Input | Purpose and output |
|---|---|---|
| `melodic.sh` | Denoised MELODIC file list and dimension `0` or `20` | Runs temporal-concatenation group MELODIC. |
| `match_smith09.sh` | One group-MELODIC solution and Smith09 maps | Resamples Smith09 maps and calculates all spatial correlations with `fslcc`. |
| `gen_fslcc_table.py` | Raw `fslcc` output | Writes labeled correlation matrices and best-match tables. |
| `run_match_smith09.sh` | Four completed MELODIC solutions | Runs every Smith09 comparison and then the summary script. |
| `summarize_smith09_analyses.py` | Four Smith09 best-match tables | Writes `derivatives/fsl/diagnostics/smith09_ica_comparison.tsv`. |

## Dual Regression and Inference

| File | Input | Purpose and output |
|---|---|---|
| `dual_regression` | Group maps plus ordered 4D BOLD inputs | Unmodified FSL v0.6 dual-regression script retained under its FSL license. |
| `run_dual_regression.sh` | Denoised MELODIC dimension `0` or `20` | Runs stages 1 and 2 with design normalization and writes `input_order.tsv`. |
| `run_dual_regression_smith09.sh` | Smoothed or denoised file list and Smith09 maps | Runs the same two stages using the published ten-network maps. |
| `make_dual_regression_contrasts.sh` | One completed dual-regression component | Builds all seven paired condition differences, merged group inputs, and one-sample designs. |
| `randomise.sh` | One merged component/condition difference | Runs one one-sample cluster-extent test (`-c 3.1`); TFCE is available only with `--tfce`. |
| `run_randomise.sh` | Completed dual regression and, for ICA, the Smith09 matching table | Prepares DMN, all primary ICA components, or the four direct Smith09 maps and launches up to 24 jobs concurrently. |
| `run_randomise_qc_sensitivity.sh` | Completed dual regression and `exclude_qc_outliers.txt` | Repeats primary and/or Smith09 randomise after the predefined three-participant QC exclusion, without overwriting full-sample outputs. |
| `exclude_qc_outliers.txt` | Participant-level QC summary | Prespecified 24-participant sensitivity exclusions and rule. |
| `check_randomise_results.py` | Primary randomise outputs | Verifies both design directions and cluster-extent corrp maps, then copies significant maps and compact participant-by-condition ROI-value TSVs to `derivatives/fsl/randomise_summary`. |
| `../notebooks/plot_randomise_results.ipynb` | Tracked randomise summary, significant maps, and ROI-value TSVs | Interactively plots significant clusters on MNI anatomy and four-condition means with SEM on any computer. |

Use the batch launcher first for DMN and then for the full primary set:

```bash
code/run_randomise.sh dmn --dry-run
code/run_randomise.sh dmn
code/run_randomise.sh primary
code/run_randomise.sh smith09 --dry-run
code/run_randomise.sh smith09
python3 code/check_randomise_results.py --analysis-set all --network-set primary --fail-on-missing
bash notebooks/run_randomise_notebook.sh
```

Run the predefined QC sensitivity separately:

```bash
code/run_randomise_qc_sensitivity.sh all --dry-run
code/run_randomise_qc_sensitivity.sh all
python3 code/check_randomise_results.py \
  --analysis-set all \
  --sensitivity-label qc-outliers \
  --exclude-list code/exclude_qc_outliers.txt \
  --fail-on-missing
```

Completed jobs have a `.complete` marker beside their output prefix, so the
primary run skips DMN tests already finished by the first batch.
