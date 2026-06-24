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

The subject summary is the primary absolute-QC screening table. It averages
tSNR, mean FD, and MRIQC's percentage of volumes above 0.2-mm FD across the
acquired runs, while also reporting each subject's worst run. Subjects are
marked for review when they have fewer than four runs, mean tSNR below 30,
mean FD above 0.5 mm, mean high-motion volumes above 50%, or any run above 50%
high-motion volumes. Directional Tukey 1.5-IQR flags are included as additional
diagnostics. The 20% and 50% motion columns make stricter alternatives visible,
but no participant or run is excluded automatically.

The condition-contrast table provides a separate differential-QC screen. It
reads each run's condition from the BIDS `trial_type` column and calculates the
seven planned paired differences:

- `BOTH - SHAM`
- `BOTH - RTPJ`
- `BOTH - VLPFC`
- `RTPJ - VLPFC`
- `RTPJ - SHAM`
- `VLPFC - SHAM`
- `BOTH - mean(RTPJ, VLPFC)`

Each difference is calculated for tSNR, mean FD, and FD percentage. A positive
motion difference means condition A had more motion; a negative tSNR difference
means condition A had lower tSNR. `OutlierID.py` reports signed two-sided Tukey
1.5-IQR flags but does not exclude anyone.

The sensitivity-analysis exclusions are generated separately from absolute
condition differences:

```bash
python3 code/select_qc_sensitivity_exclusions.py
```

For each comparison, the script applies an upper Tukey 1.5-IQR fence to the
absolute mean-FD difference and absolute difference in percentage of volumes
above 0.20-mm FD. A comparison receives a paired motion flag only when both
metrics exceed their fences. A participant is excluded from the sensitivity
analysis after paired flags in at least two of the seven comparisons. This
conservative rule makes differential head motion the primary QC exclusion
criterion while retaining tSNR flags and participant-average thresholds as
diagnostics. The correlated comparisons are not treated as independent tests.

Review the five output tables in `derivatives/qc`:

```text
task-rest_mriqc_outliers.tsv
task-rest_mriqc_bounds.tsv
task-rest_mriqc_subject_summary.tsv
task-rest_mriqc_condition_contrasts.tsv
task-rest_mriqc_condition_contrast_bounds.tsv
task-rest_qc_sensitivity_abs_bounds.tsv
task-rest_qc_sensitivity_exclusions.tsv
```

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

Build all seven contrasts for one selected component at a time. Component
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
`BOTH-mean(RTPJ,VLPFC)`. For each comparison it merges the participant maps in
the recorded order, then writes `subject_order.tsv`, one-sample `design.mat`,
`design.con`, `design.grp`, and a `run_randomise.sh` launcher. The design
contains positive and negative rows for two-sided interpretation.

The stable batch launcher in `code` reads the committed Smith09 matching table,
prepares missing component contrasts, and runs 5,000 permutations with
cluster-extent inference at a cluster-forming t threshold of 3.1 (`-c 3.1`).
TFCE is available only as an explicit option and is not interpreted. Start with
the two DMN components:

```bash
code/run_randomise.sh dmn --dry-run
code/run_randomise.sh dmn
```

This launches 14 jobs: two ICA solutions by seven condition contrasts. Expand
to all primary networks after that batch completes:

```bash
code/run_randomise.sh primary
code/run_randomise.sh smith09
```

The primary plan contains seven unique ICA components and 49 jobs, with at
most 24 active processes. Automatic dimensionality contributes separate DMN,
ECN, right-FPN, and left-FPN components. Dim-20 contributes DMN, ECN, and one
bilateral FPN component because both lateralized Smith09 maps select component
`8`. Completion markers prevent the primary batch from repeating finished DMN
tests. Logs are written under `derivatives/logs/randomise`.

The full-sample preliminary analysis did not exclude any of its 27 participants
for motion. To cover every remaining non-cerebellar Smith09 network in secondary
analyses, run the ICA-derived matches and direct atlas maps:

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
the participant count in each merged input, and expects 77 jobs, 154 t-stat
images, and 154 cluster-extent corrected-p images (two directions).
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

The preliminary full-sample result is tagged
`preliminary-results-2026-06-23` and documented in
[`docs/preliminary-results-2026-06-23.md`](docs/preliminary-results-2026-06-23.md).
Regenerate the differential-motion exclusion list, then repeat the desired jobs
without overwriting the full-sample outputs. `all` includes primary and
secondary ICA-derived and direct-Smith09 analyses (175 jobs):

```bash
python3 code/select_qc_sensitivity_exclusions.py
code/run_randomise_qc_sensitivity.sh all
python3 code/check_randomise_results.py \
  --network-set all \
  --analysis-set all \
  --sensitivity-label qc-outliers \
  --exclude-list code/exclude_qc_outliers.txt \
  --fail-on-missing
```

`code/randomise.sh` runs one network/contrast job when a targeted rerun is
needed. See [`code/README.md`](code/README.md) for concise input/output notes on
every script. FSL documents `-c` as the cluster-extent inference option in its
[randomise guide](https://fsl.fmrib.ox.ac.uk/fsl/docs/statistics/randomise.html).

For an explicitly secondary Z-map analysis, add `--map-type z`. Processing one
selected component at a time avoids materializing every contrast for all 144
automatic-dimensionality components.

## Remaining Work

1. Run and audit the documented 24-participant differential-motion sensitivity.
2. Reconcile the 27-participant sample with the earlier 28- and 22-participant
   analyses and resolve any stimulation-delivery exclusion.
3. Run and audit the non-cerebellar secondary-network family.
4. Compare full-sample and sensitivity results in the portable notebook.
5. Decide the final primary inferential family and across-job multiplicity
   strategy before treating any preliminary finding as confirmatory.

## License

Original project code is licensed under the MIT License. `code/dual_regression`
is derived from FSL and remains subject to the FSL License reproduced in that
file. See `LICENSE` for details.
