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

## Final Shareable Reports

The current N=27 results are summarized in two self-contained HTML reports:

- [`notebooks/plot_randomise_results_rendered.html`](notebooks/plot_randomise_results_rendered.html): direct Smith09 DMN and ECN connectivity results.
- [`notebooks/plot_network_correlation_ppi_results_rendered.html`](notebooks/plot_network_correlation_ppi_results_rendered.html): DMN coupling with ECN and left/right FPN, plus the secondary DMN x ECN interaction analysis.

Both reports use the original 10 Smith09 maps and focus on three nonredundant
contrasts: mean stimulation minus sham, BOTH minus the mean of the two
single-site conditions, and RTPJ minus VLPFC. They report cluster-extent
inference only and combine the inspected positive and negative directions into
a conservative two-sided p-value. See
[`notebooks/README.md`](notebooks/README.md) for scope and reproduction notes.

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
`derivatives/logs/fmriprep`. The batch launcher checks the expected report,
MNI, CIFTI, confound, T1w, and FreeSurfer outputs and skips complete
participants. Use `--rerun-complete` only for an intentional full rerun.

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

The subject summary is a diagnostic QC table. It averages tSNR and mean FD
across the acquired runs while also reporting each subject's worst run.
Subjects are marked for review when they have fewer than four runs, mean tSNR
below 30, or mean FD above 0.5 mm. Directional Tukey 1.5-IQR flags are included
as additional diagnostics, but no participant or run is excluded automatically.

The condition-contrast table records the seven planned differences for
diagnostic review. It
reads each run's condition from the BIDS `trial_type` column and calculates the
seven planned paired differences:

- `BOTH - SHAM`
- `BOTH - RTPJ`
- `BOTH - VLPFC`
- `RTPJ - VLPFC`
- `RTPJ - SHAM`
- `VLPFC - SHAM`
- `BOTH - mean(RTPJ, VLPFC)`

Each difference is calculated for tSNR and mean FD. A positive motion
difference means condition A had more motion; a negative tSNR difference means
condition A had lower tSNR. `OutlierID.py` reports signed two-sided Tukey
1.5-IQR flags as diagnostics.

The result notebook provides the current nonredundant QC summary. It subtracts
each participant's four-condition mean to retain direction, uses three
orthogonal contrasts that span all possible condition differences. Within-
subject label permutation tests whether condition directions align across
participants. These permutation tests describe group condition structure and
are not exclusion tests. In the N=27 data, there is no consistent condition
pattern for tSNR (`p=.58`) or mean FD (`p=.75`).

`select_qc_exclusions.py` averages each participant's absolute magnitude across
the three orthogonal contrasts separately for tSNR and mean FD, then applies
the upper Tukey fence to each distribution. This is retained as a diagnostic
sensitivity rule; the final N=27 analysis does not exclude participants for
data quality.

Review the tracked output tables in `derivatives/qc`:

```text
task-rest_mriqc_outliers.tsv
task-rest_mriqc_bounds.tsv
task-rest_mriqc_subject_summary.tsv
task-rest_mriqc_condition_contrasts.tsv
task-rest_mriqc_condition_contrast_bounds.tsv
task-rest_qc_contrast_average_bounds.tsv
task-rest_qc_exclusions.tsv
task-rest_run_covariates.tsv
task-rest_group_covariates.tsv
```

`MakeGroupCovariates.py` combines the MRIQC run metrics with task-rest BIDS
events. It keeps mean FD and tSNR, then extracts run-level pupil area, blink
rate, total blinks, and eye-closure fraction from the event TSVs:

```bash
python3 code/MakeGroupCovariates.py
```

Create reviewable design spreadsheets for covariate-adjusted group models with
mean FD as the nuisance EV:

```bash
python3 code/MakeRandomiseDesignSpreadsheets.py --covariates fdmean
```

The spreadsheet outputs live under
`derivatives/qc/randomise_design_spreadsheets`. They are meant for the FSL GLM
GUI: paste the labeled `EV*` columns from each contrast-specific
`*_design-matrix.tsv`, use `task-rest_design-contrast-reference.tsv` for the
positive and negative intercept contrasts, and use
`task-rest_design-group-reference.tsv` for `design.grp`. When building a design
for a specific randomise stack on Linux, pass that stack's `subject_order.tsv`
so the spreadsheet order exactly matches the merged 4D image.

The currently tracked FD-mean spreadsheets use sorted complete participants and
have N=27. In the local BIDS copy, `sub-233` run 01 is now condition-labeled
from events, but runs 02-04 are still zero-row task-rest event files, so
`sub-233` remains incomplete until those files are fixed and the covariate
tables are regenerated. Pupil and blink-rate columns are extracted into the
covariate tables, but FD mean is the only generated design EV for now because
the current local events have missing pupil/blink-derived values for a few
otherwise usable runs.

For the covariate-adjusted whole-brain `randomise` follow-up models, the small
GitHub-tracked design templates live under
`templates/randomise_covariate_models`. Generate or refresh them with:

```bash
python3 code/MakeCovariateRandomiseModels.py --templates-only --covariates fdmean,blink
python3 code/MakeCovariateRandomiseModels.py --templates-only --covariates fdmean,pupil
```

Those template filenames include the contrast-specific N. Each contrast has an
FSL-ready `.mat` file plus a labeled TSV ordered as `participant`, `intercept`,
then demeaned covariates; the intercept column is all `1`s and is not demeaned.
An excluded-participants TSV is written only for contrasts where at least one
participant was dropped from that template.

The covariate-adjusted `randomise` launchers use the generated `design.mat`
and `design.con` files without passing `-e design.grp`, since these are
subject-level one-sample contrast images rather than exchangeability-block
models. Each generated `design.con` has four contrasts: C1 `mean_pos`, C2
`mean_neg`, C3 `cov_pos`, and C4 `cov_neg`. In the `fdmean,blink` and
`fdmean,pupil` models, FD mean is the adjustment covariate and the final
covariate column, blink or pupil, is tested by C3/C4.

On the Linux box, rebuild the covariate model folders, inspect every path, then
launch the currently significant follow-up jobs with bounded concurrency:

```bash
python3 code/MakeCovariateRandomiseModels.py --covariates fdmean,blink --overwrite
python3 code/MakeCovariateRandomiseModels.py --covariates fdmean,pupil --overwrite
code/run_covariate_randomise.sh --dry-run --max-jobs 35
code/run_covariate_randomise.sh --max-jobs 35
python3 code/check_covariate_randomise_results.py --fail-on-missing
python3 code/check_covariate_model_integrity.py --fail-on-error
```

The compiler writes GitHub-trackable covariate summaries to
`derivatives/fsl/covariate_randomise_summary`. The peak summary includes C1/C2
mean-effect rows and C3/C4 covariate-effect rows. Significant corrected maps
are copied there with JSON sidecars plus small ROI-value TSVs that join each
participant's subject-level contrast beta to the covariate audit table; those
TSVs are the portable inputs for C3/C4 scatterplots. For significant C1/C2
maps, the compiler also writes condition-level stage-2 beta TSVs used for
four-condition bar plots.
The integrity checker writes
`derivatives/fsl/covariate_randomise_summary/task-rest_covariate-randomise_integrity.tsv`
and verifies the model assumptions that are easy to get wrong: design/audit
row order, demeaned covariate columns, subject and image-list order, group input
volume counts, C3/C4 contrast targets, and mask voxel counts. It allows small
rounding differences from FSL's six-decimal `.mat` formatting and reports the
maximum design-vs-audit difference for each job.

## Network Correlations and PPI

Use the original 10-map Smith09 dual-regression timecourses to test whether DMN
coupling with ECN and left/right FPN changes by stimulation condition:

```bash
python3 code/MakeNetworkCorrelationTables.py \
  --analysis smith09_denoised \
  --network-set dmn-targets \
  --fail-on-missing
```

Outputs are small TSVs under `derivatives/fsl/network_correlation_summary`.
They include run-level Pearson and partial correlations from explicitly
z-scored timecourses, Fisher-z condition-difference tables, and deterministic
sign-flip summaries.

For the secondary physio-physio interaction analysis, reuse the 10-map stage-1
timecourses and add the standardized DMN x ECN product as component 11. The FSL
`dual_regression` file remains unmodified.

```bash
code/run_smith09_dmn_ecn_ppi.sh --dry-run
code/run_smith09_dmn_ecn_ppi.sh
code/run_smith09_dmn_ecn_ppi_randomise.sh --dry-run
code/run_smith09_dmn_ecn_ppi_randomise.sh
python3 code/check_ppi_randomise_results.py --fail-on-missing
```

Components 1-10 are the explicitly z-scored Smith09 timecourses and component
11 is the centered interaction. Stage 2 uses `fsl_glm --demean --des_norm`.
The checker writes compact summaries, copied significant maps, JSON sidecars,
and condition-level ROI TSVs to `derivatives/fsl/ppi_randomise_summary`.

## Verify Outputs

Check expected outputs for every BIDS run and T1w image:

```bash
code/check_preprocessing_status.py --fail-on-missing
```

The checker verifies fMRIPrep reports, MNI BOLD, CIFTI BOLD, confounds,
preprocessed T1w, FreeSurfer completion, MRIQC reports and IQM JSON files, plus
the MRIQC group TSV tables and HTML outputs. It derives expected counts from
BIDS, so participants with fewer than four acquired runs are handled correctly.

Write a CSV summary when useful:

```bash
code/check_preprocessing_status.py \
  --output-csv derivatives/preprocessing_status.csv
```

## Extract Confounds

After fMRIPrep is complete:

```bash
python3 code/MakeConfounds.py --subjects code/included_sublist.txt
```

The script follows the lab's existing `MakeConfounds.py` convention. It writes
one omnibus nuisance matrix per run containing:

- cosine high-pass terms;
- non-steady-state regressors;
- 24 extended motion terms: the six rigid-body parameters, their temporal
  derivatives, their squares, and the squared derivatives;
- `a_comp_cor_00` through `a_comp_cor_05`;
- continuous framewise displacement.

Missing values are replaced with zero. Headerless numeric `.1D` matrices are
written to `derivatives/fsl/confounds`. The `.1D` extension is required because
AFNI interprets the first row of every `.tsv` file as a header. Each run's
condition is read from the unique `trial_type` in its BIDS events file. Runs are
ordered within subject as sham, RTPJ, VLPFC, and both, while retaining the
acquired run number. The image and confound lists are written in exactly the
same order:

```text
derivatives/fsl/melodic_filelist.txt
derivatives/fsl/confound_filelist.txt
```

`derivatives/fsl/task-rest_run_manifest.tsv` records participant, acquired run,
condition, canonical condition order, events, BOLD, and confound paths. This is
the provenance table for later condition contrasts.

`MakeConfounds.py` requires every included subject to have exactly one run from
each condition. Participants with missing labels or incomplete condition sets
are skipped as a unit; the script never guesses counterbalancing. At present,
`sub-212` has only sham and VLPFC runs, while the four `sub-233` task-rest events
files contain placeholder headers and no `trial_type` rows. Their exclusion
reasons are recorded in:

```text
derivatives/fsl/task-rest_skipped_subjects.tsv
```

The reviewed inclusion list restricts both ordered FSL input lists to complete
subjects approved for analysis.

## Smooth To 5 mm

After extracting confounds, smooth every run in the ordered run manifest to a
final 5-mm FWHM with AFNI `3dBlurToFWHM`:

```bash
code/run_smooth-3dBlurToFWHM.sh --dry-run
code/run_smooth-3dBlurToFWHM.sh
```

`code/smooth-3dBlurToFWHM.sh SUBJECT RUN` handles one run. It passes the matching
fMRIPrep brain mask to `3dBlurToFWHM`, then explicitly applies that mask to the
smoothed image with `fslmaths -mas`. Work is isolated under
`/ZPOOL/data/scratch/$USER/r21-rest/smoothing`, avoiding conflicts from AFNI's
temporary `3dFWHMx.1D` files.

Smoothed files retain the acquired run and add the condition and canonical
order, for example
`run-02_..._condition-sham_order-01_desc-preproc_bold_5mm.nii.gz`. The batch
script writes `derivatives/fsl/melodic_filelist_5mm.txt` in canonical condition
order only after every requested output exists.

## Regress Confounds

After smoothing, regress all nuisance terms together from each run:

```bash
code/run_regress_confounds.sh --dry-run
code/run_regress_confounds.sh
```

`code/regress_confounds.sh SUBJECT RUN` handles one run. It uses AFNI
`3dTproject` with the matching fMRIPrep brain mask and a single joint design
containing all extracted confounds plus a constant. No censoring or additional
temporal filtering is applied. The cosine columns already implement the
fMRIPrep high-pass model. The batch launcher rejects old `.tsv` matrices and
matrices with fewer than the 31 required base regressors before launching jobs.

The cleaned files are written under `derivatives/fsl/denoised`. The batch
script writes the canonical ordered input list only after every output exists:

```text
derivatives/fsl/melodic_filelist_5mm_denoised.txt
```

This is intentionally an omnibus regression. `fsl_glm --out_res` could produce
the same kind of residuals with an equivalent full-rank design, while
`fsl_regfilt` is primarily convenient when selected design columns, such as
classified ICA components, are to be removed. Running separate nuisance steps
is avoided because sequential projections can reintroduce previously removed
variance; see [Lindquist et al. (2019)](https://doi.org/10.1002/hbm.24528).

## Check MELODIC Inputs

Audit every cleaned input before starting group ICA:

```bash
code/check_melodic_inputs.sh
```

The check verifies that all paths are present and unique, every subject has one
run for each of the four conditions, run lengths and image grids agree, and
each image matches its original fMRIPrep mask. It also checks signal outside
the mask, spatial coverage, finite intensity summaries, and nonzero temporal
variance. Run-level values are written to:

```text
derivatives/qc/task-rest_melodic_input_qc.tsv
```

The table also records the nuisance-regressor count and the ratio of temporal
standard deviation retained after regression. Ratios near one indicate that
regression had almost no effect; ratios below 0.10 indicate unusually severe
variance removal. Failed status counts and the first 20 affected inputs are
printed directly to the terminal.

Small text diagnostics in `derivatives/qc` and
`derivatives/fsl/diagnostics` may be committed. All other FSL outputs, images,
MELODIC directories, confound matrices, and logs remain ignored.

## Group MELODIC

`code/melodic.sh` uses the checked
`derivatives/fsl/melodic_filelist_5mm_denoised.txt` by default. Run
temporal-concatenation MELODIC both with automatic dimensionality and with 20
fixed components:

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
derivatives/fsl/melodic-concat_denoised_dim-00_task-rest.ica
derivatives/fsl/melodic-concat_denoised_dim-20_task-rest.ica
```

Set `MELODIC_FILELIST` only when intentionally testing a different ordered
image list.

## Match Smith09 Networks

The original Smith09 10-network image is stored in `masks`. Match all four
completed MELODIC analyses in one pass:

```bash
code/run_match_smith09.sh --dry-run
code/run_match_smith09.sh
```

This runs `code/match_smith09.sh DATA_SET DIMENSION` for smoothed and denoised
data at automatic and fixed-20 dimensionality. Smith09 maps are resampled to
each exact MELODIC grid before calculating signed spatial correlations with
`fslcc`. Because ICA component polarity is arbitrary, matches are ranked by
absolute correlation while retaining the sign.

Each `derivatives/fsl/smith09*_task-rest` directory contains raw `fslcc`
output, the resampled 10-network image, a complete labeled correlation matrix,
and `smith09_best_matches.tsv`. The four analyses are combined in:

```text
derivatives/fsl/diagnostics/smith09_ica_comparison.tsv
```

The table reports the best and next-best component, signed and absolute
correlations, and their absolute-correlation margin. DMN, ECN, and left/right
FPN are marked primary; cerebellar and sensorimotor maps are secondary. Final
component selection still requires visual review.

## Dual Regression

`code/dual_regression` is restored to the unmodified FSL v0.6 script. It takes
the cleaned images as ordinary positional inputs; confounds are not entered a
second time. Launch stages 1 and 2 for both denoised group-ICA solutions:

```bash
code/run_dual_regression.sh 0 --dry-run
code/run_dual_regression.sh 0
code/run_dual_regression.sh 20
```

Both launchers call the original script with `1 -1 0`: stage-1 timecourses are
design-normalized, no group design is supplied, and no `randomise` permutations
are run. Outputs are written to:

```text
derivatives/fsl/dual-regression_denoised_dim-00_task-rest.dr
derivatives/fsl/dual-regression_denoised_dim-20_task-rest.dr
```

The input list follows the same within-subject condition order recorded in
`task-rest_run_manifest.tsv`. Using the same cleaned data for MELODIC and both
dual-regression stages prevents nuisance variance removed before ICA from being
reintroduced later. Each output contains an `input_order.tsv` that maps FSL's
`subjectNNNNN` labels back to participant, run, and stimulation condition.

### Smith09 Sensitivity Analysis

Run stages 1 and 2 using the original Smith09 maps instead of data-derived
MELODIC maps:

```bash
code/run_dual_regression_smith09.sh denoised --dry-run
code/run_dual_regression_smith09.sh denoised
```

The launcher resamples all 10 Smith09 maps to the exact input grid, preserves
their published order, and calls the unmodified FSL script with `1 -1 0`, so
no `randomise` permutations are launched. Outputs are written to
`derivatives/fsl/dual-regression_smith09_denoised.dr`. Its `input_order.tsv`
maps FSL's `subject00000` labels back to participant, acquired run, condition,
and canonical condition order.

FSL is called with `des_norm=1`, so stage-1 timecourses are variance-normalized
when used as stage-2 regressors. The correlation compiler also z-scores each
stage-1 column explicitly within run. Pearson and correlation-matrix partial
correlations are invariant to this scaling, but the explicit step makes the
procedure auditable. PPI products are constructed from these z-scored columns.

Run the same sensitivity analysis on the smoothed but not nuisance-regressed
data with:

```bash
code/run_dual_regression_smith09.sh smoothed
```

## Condition Contrasts and Randomise Inputs

Use the design-normalized raw stage-2 coefficient images
(`dr_stage2_subjectNNNNN.nii.gz`) for the primary within-participant
subtractions. This is the quantity forwarded by FSL's standard dual-regression
workflow, and it is the design-normalized stage-2 spatial-map estimate
recommended for group inference by Nickerson et al. (2017). The corresponding
`_Z` files additionally incorporate run-specific residual uncertainty; they
are available as a sensitivity analysis but are not the primary effect
estimates for paired subtraction.

Build all eight contrasts for one selected component at a time. Component
numbers are 1-based, matching the MELODIC and Smith09 matching tables:

```bash
# Smith09 default mode network (published map 4)
code/make_dual_regression_contrasts.sh smith09 4 --dry-run
code/make_dual_regression_contrasts.sh smith09 4

# Denoised dim-20 DMN match (MELODIC component 10)
code/make_dual_regression_contrasts.sh 20 10

# Denoised automatic-dimensionality DMN match (component 23)
code/make_dual_regression_contrasts.sh 0 23
```

The script extracts that component from the four stage-2 images for each
participant and creates `BOTH-SHAM`, `BOTH-RTPJ`, `BOTH-VLPFC`,
`RTPJ-VLPFC`, `RTPJ-SHAM`, `VLPFC-SHAM`, and
`BOTH-mean(RTPJ,VLPFC)`, and `mean(RTPJ,VLPFC,BOTH)-SHAM`. For each comparison it merges the participant maps in
the recorded order, then writes `subject_order.tsv`, one-sample `design.mat`,
`design.con`, `design.grp`, and a `run_randomise.sh` launcher. The design
contains positive and negative rows for two-sided interpretation.

Add only the newly specified stimulation-average contrast to the existing
N=27 analyses without rebuilding the other seven contrasts:

```bash
code/run_randomise.sh primary --contrasts mean-stimulation-minus-sham --max-jobs 35
code/run_randomise.sh smith09 --contrasts mean-stimulation-minus-sham --max-jobs 35
code/run_randomise.sh secondary --contrasts mean-stimulation-minus-sham --max-jobs 35
code/run_randomise.sh smith09-secondary --contrasts mean-stimulation-minus-sham --max-jobs 35
```

The stable batch launcher in `code` reads the committed Smith09 matching table,
prepares missing component contrasts, and runs 5,000 permutations with
cluster-extent inference at a cluster-forming t threshold of 3.1 (`-c 3.1`).
TFCE is available only as an explicit option and is not interpreted. Start with
the two DMN components:

```bash
code/run_randomise.sh dmn --dry-run
code/run_randomise.sh dmn
```

This launches 16 jobs: two ICA solutions by eight condition contrasts. Expand
to all primary networks after that batch completes:

```bash
code/run_randomise.sh primary
code/run_randomise.sh smith09
```

The primary plan contains seven unique ICA components and 56 jobs, with at
most 24 active processes. Automatic dimensionality contributes separate DMN,
ECN, right-FPN, and left-FPN components. Dim-20 contributes DMN, ECN, and one
bilateral FPN component because both lateralized Smith09 maps select component
`8`. Completion markers prevent the primary batch from repeating finished DMN
tests. Logs are written under `derivatives/logs/randomise`.

The final N=27 analysis did not exclude participants for motion. The scripts
also retain the ability to audit non-cerebellar Smith09 networks without
including them in the final report:

```bash
code/run_randomise.sh secondary
code/run_randomise.sh smith09-secondary
python3 code/check_randomise_results.py \
  --network-set secondary \
  --analysis-set all \
  --fail-on-missing
```

This adds primary visual, occipital-pole, lateral-visual, sensorimotor, and
auditory networks. Cerebellum is intentionally omitted because of poor coverage.

Audit the finished data-derived and direct-Smith09 batches with:

```bash
python3 code/check_randomise_results.py --analysis-set all --fail-on-missing
```

The checker verifies that every component uses C1=`1` and C2=`-1`, confirms
the participant count in each merged input, and expects 88 jobs, 176 t-stat
images, and 176 cluster-extent corrected-p images (two directions).
Because FSL corrp images contain `1-p`, a peak above 0.95 indicates corrected
`p < 0.05`. Results are written to the GitHub-tracked directory:

```text
derivatives/fsl/randomise_summary/task-rest_randomise_peak_summary.tsv
```

Complete significant corrp images are copied into the same directory using
`task-rest_space-MNI152NLin6Asym_desc-..._stat-corrp_statmap.nii.gz` names,
with JSON sidecars documenting the analysis, network, component, contrast,
direction, inference method, permutation count, threshold, peak, and source.
Compact participant-by-condition stage-2 beta TSVs make the result notebook
portable across machines.

Regenerate the QC diagnostic table with:

```bash
python3 code/select_qc_exclusions.py
```

The boxplot rule is retained for sensitivity review but is not used to exclude
participants from the final N=27 analysis.

`code/randomise.sh` runs one network/contrast job when a targeted rerun is
needed. See [`code/README.md`](code/README.md) for concise input/output notes on
every script. FSL documents `-c` as the cluster-extent inference option in its
[randomise guide](https://fsl.fmrib.ox.ac.uk/fsl/docs/statistics/randomise.html).

For an explicitly secondary Z-map analysis, add `--map-type z`. Processing one
selected component at a time avoids materializing every contrast for all 144
automatic-dimensionality components.

## Remaining Work

The original 10-map DMN x ECN PPI batch did not include the mean-stimulation-
minus-sham contrast. The coupling report marks it as not run. Completing that
single test is optional and should not be represented as a null result in the
meantime.

For interpretation, state whether each inferential claim is individual,
conjunctive, or disjunctive. Following Rubin (2021), do not apply a blanket
across-job alpha adjustment to separate individual hypotheses; adjustment is
relevant to an "at least one" disjunctive claim.

## License

Original project code is licensed under the MIT License. `code/dual_regression`
is derived from FSL and remains subject to the FSL License reproduced in that
file. See `LICENSE` for details.
