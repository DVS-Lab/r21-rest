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
| `MakeGroupCovariates.py` | MRIQC run table and BIDS task-rest events | Writes run-level and contrast-level group covariates, including mean FD, tSNR, pupil area, blink rate, and eye closure. |
| `MakeCovariateDeltaTables.py` | `task-rest_group_covariates.tsv` | Writes compact complete-case subject-level contrast-delta tables for mean FD, pupil area, and blink rate under `derivatives/qc/covariate_delta_tables`, using the primary N=27 subject scope by default, plus a missingness audit. |
| `MakeRandomiseDesignSpreadsheets.py` | Group covariates and, optionally, a `subject_order.tsv` | Writes labeled TSV/CSV tables for building covariate-adjusted `design.mat`, `design.con`, and `design.grp` files in the FSL GUI. |
| `MakeCovariateRandomiseModels.py` | Existing dual-regression contrast images and group covariates | Builds covariate-adjusted whole-brain randomise model folders with per-contrast participant orders, design files, merged group inputs, launchers, and tracked review templates under `templates/randomise_covariate_models`. |
| `tsvResting.m` | r21-cardgame BIDS task-rest events | Bart's MATLAB pupil/blink analysis helper; auto-detects the Mac and Linux r21-cardgame locations, reads `R21_CARDGAME_ROOT`, and adds `klab`, `klab/kStats`, or explicit `KLAB_ROOT`/`KSTATS_ROOT` override paths when needed. |
| `MakeConfounds.py` | fMRIPrep confounds and BIDS events | Writes FSL/AFNI confound matrices, the ordered run manifest, and input lists. |
| `smooth-3dBlurToFWHM.sh` | One fMRIPrep BOLD run and mask | Masks and smooths one run to 5-mm FWHM while adding its condition label. |
| `run_smooth-3dBlurToFWHM.sh` | Ordered run manifest | Runs the single-run smoothing script across all included runs. |
| `regress_confounds.sh` | One smoothed run and confound matrix | Uses `3dTproject` to write one denoised BOLD run. |
| `run_regress_confounds.sh` | Ordered run manifest | Denoises every run and writes `melodic_filelist_5mm_denoised.txt`. |
| `check_melodic_inputs.sh` | Denoised MELODIC file list | Checks grids, masks, volumes, intensity, and variance; writes a QC TSV. |
| `select_qc_exclusions.py` | Condition-labeled run-level MRIQC TSV | Averages absolute magnitude across three orthogonal contrasts, applies Tukey upper fences to tSNR and mean FD, and selects participants flagged on both. |

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
| `run_randomise.sh` | Completed dual regression and, for ICA, the Smith09 matching table | Runs primary or non-cerebellar secondary ICA matches or direct Smith09 maps with up to 24 concurrent jobs. |
| `run_randomise_qc_sensitivity.sh` | Completed dual regression and `exclude_qc_outliers.txt` | Repeats selected randomise families with a supplied exclusion list without overwriting full-sample outputs. |
| `run_covariate_randomise.sh` | `randomise_jobs.tsv` files from `MakeCovariateRandomiseModels.py` | Preflights and launches covariate-adjusted randomise jobs across model folders with bounded concurrency. |
| `check_covariate_randomise_results.py` | Completed covariate-adjusted randomise model folders | Compiles C1-C4 covariate-model peaks, copies significant corrected maps, and writes scatterplot-ready ROI-value TSVs to `derivatives/fsl/covariate_randomise_summary`. |
| `check_covariate_model_integrity.py` | Completed covariate-adjusted randomise model folders | Audits model assumptions: mask voxels, demeaned covariates, design/audit row agreement, subject/image order, group input volume counts, and C3/C4 contrast vectors. |
| `exclude_qc_outliers.txt` | Output from `select_qc_exclusions.py` | Participants whose average three-contrast magnitude is a boxplot outlier for both tSNR and mean FD; currently `sub-218`. |
| `check_randomise_results.py` | Selected randomise outputs | Verifies both design directions and cluster-extent corrp maps, then copies significant maps and compact participant-by-condition ROI-value TSVs to `derivatives/fsl/randomise_summary`. |
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

Run the remaining non-cerebellar networks separately:

```bash
code/run_randomise.sh secondary
code/run_randomise.sh smith09-secondary
python3 code/check_randomise_results.py \
  --analysis-set all \
  --network-set secondary \
  --fail-on-missing
```

Regenerate the participant QC decisions with the adopted boxplot rule:

```bash
python3 code/select_qc_exclusions.py
```

The generated exclusion list currently contains `sub-218`. Treat an N=26 rerun
as a sensitivity analysis; the preliminary N=27 outputs remain frozen.

Build reviewable group-level covariate spreadsheets before creating FSL GUI
design files:

```bash
python3 code/MakeGroupCovariates.py
python3 code/MakeCovariateDeltaTables.py
python3 code/MakeRandomiseDesignSpreadsheets.py --covariates fdmean
```

Prepare covariate-adjusted whole-brain randomise follow-up models for the
currently significant cluster-extent jobs. Run this on the Linux box because it
uses the full dual-regression contrast images and `fslmerge`:

```bash
python3 code/MakeCovariateRandomiseModels.py --covariates fdmean,blink --overwrite
python3 code/MakeCovariateRandomiseModels.py --covariates fdmean,pupil --overwrite
code/run_covariate_randomise.sh --dry-run --max-jobs 35
code/run_covariate_randomise.sh --max-jobs 35
python3 code/check_covariate_randomise_results.py --fail-on-missing
python3 code/check_covariate_model_integrity.py --fail-on-error
```

Small FSL `design.mat` templates and labeled TSVs are also written to
`templates/randomise_covariate_models/model-*`. These are the GitHub-tracked
copies for review and direct reuse. Each file name includes its
contrast-specific N, and each TSV is ordered as `participant`, `intercept`,
then demeaned covariates. The intercept column is all `1`s and is not
demeaned. An excluded-participants TSV is written only when a contrast actually
drops one or more participants.

To regenerate only the tracked templates without touching the large
dual-regression outputs:

```bash
python3 code/MakeCovariateRandomiseModels.py --templates-only --covariates fdmean,blink
python3 code/MakeCovariateRandomiseModels.py --templates-only --covariates fdmean,pupil
```

The FD/blink model remains N=27 for each contrast. The FD/pupil model uses
contrast-specific complete cases because Bart confirmed that three pupil runs
are not recoverable. Blink rate and pupil size are intentionally not modeled
together. Each generated model folder contains its own `run_randomise.sh`
launcher, and `code/run_covariate_randomise.sh` can launch all model-folder
jobs together. The covariate launchers do not pass `-e design.grp`;
exchangeability blocks are unnecessary for these subject-level one-sample
contrast images. Each generated `design.con` has four contrasts: C1 `mean_pos`,
C2 `mean_neg`, C3 `cov_pos`, and C4 `cov_neg`. In the `fdmean,blink` and
`fdmean,pupil` models, FD mean is the adjustment covariate and the final
covariate column, blink or pupil, is tested by C3/C4.

`check_covariate_randomise_results.py` compiles the covariate-adjusted
`randomise` outputs into `derivatives/fsl/covariate_randomise_summary`. It
audits C1-C4 outputs, records peak corrected-p values, copies significant
corrected maps, and writes ROI-value TSVs joined to `covariate_audit.tsv` for
scatterplot follow-up.
`check_covariate_model_integrity.py` writes a paired integrity TSV in the same
summary folder. It verifies the mask exists and records its voxel count, checks
that all covariate columns are demeaned, confirms design matrix rows match
`covariate_audit.tsv`, and checks that `subject_order.tsv` and `image_list.txt`
follow the same participant order as the merged group input.

For the exact design matrix order used by a specific randomise stack, rerun the
spreadsheet step with that stack's `subject_order.tsv`:

```bash
python3 code/MakeRandomiseDesignSpreadsheets.py \
  --subject-order derivatives/fsl/dual-regression_smith09_denoised.dr/contrasts/component-0004_stat-beta/subject_order.tsv \
  --covariates fdmean
```

Use the `EV*` columns from each `*_design-matrix.tsv` in the FSL GUI, the two
rows in `task-rest_design-contrast-reference.tsv` for positive and negative
directions, and `task-rest_design-group-reference.tsv` for exchangeability
groups. The current tracked spreadsheet set is FD-mean only and has N=27
because the local BIDS copy still has zero-row task-rest events for
`sub-233` runs 02-04. Pupil and blink-rate columns are available in
`task-rest_group_covariates.tsv`; generate `fdmean,pupil,blink` designs after
reviewing and resolving the currently missing pupil/blink-derived values.

Completed jobs have a `.complete` marker beside their output prefix, so the
primary run skips DMN tests already finished by the first batch.
