# Preliminary Resting-State Results - 2026-06-23

## Status

This document freezes the first complete analysis as a preliminary full-sample
result. The corresponding repository state is tagged
`preliminary-results-2026-06-23`. Subsequent QC-exclusion analyses are
sensitivity analyses and must not overwrite these outputs.

## Sample and Workflow

- Starting sample: 31 participants.
- `sub-216` and `sub-232` have no task-rest BOLD data, leaving 29 participants
  with any resting-state data.
- `sub-212` has only two resting-state runs, leaving 28 participants with four
  runs.
- `sub-233` has four runs but no usable `trial_type` labels in the tracked BIDS
  events files, leaving 27 participants with four condition-labeled runs (108
  runs total).
- No participant in this 27-participant preliminary analysis was excluded for
  head motion, tSNR, or a condition-level QC outlier.
- Inputs: fMRIPrep MNI152NLin6Asym outputs, masked and smoothed to 5-mm FWHM.
- Nuisance model: 24 extended motion parameters, continuous FD, six aCompCor
  components, non-steady-state regressors, cosine regressors, and a constant.
- Network definitions: denoised temporal-concatenation ICA at automatic and
  fixed-20 dimensionality, plus the direct Smith09 ten-network maps.
- Group inference: two-sided one-sample `randomise`, 5,000 permutations,
  cluster-forming t = 3.1, cluster-extent FWE correction. TFCE is not being
  interpreted.
- Inferential family audited: 49 data-derived ICA jobs and 28 direct-Smith09
  jobs, each with positive and negative directions (154 corrected-p maps).

## Inclusion and Exclusion Criteria

The frozen full-sample analysis required one usable task-rest run for each of
SHAM, RTPJ, VLPFC, and BOTH; a unique condition label for every run; complete
fMRIPrep/denoising/dual-regression inputs; and successful construction of all
seven within-participant contrasts. The data-availability exclusions were
`sub-216` and `sub-232` (no task-rest BOLD), `sub-212` (only two runs), and
`sub-233` (no usable condition labels). No additional motion or tSNR exclusion
was applied, producing N=27.

The differential-motion criterion below applies only to the separately labeled
QC sensitivity analysis. A confirmed stimulation-delivery failure would be a
technical exclusion, not a motion exclusion, and is not applied until the
participant/run and failure are documented.

## Preliminary Findings

Three cluster-extent maps had peak corrected `1-p > 0.95`:

| Network definition | Signed effect | Peak 1-p | Peak FWE p |
|---|---|---:|---:|
| Automatic-dimensionality ICA DMN component 23 | VLPFC > RTPJ | 0.9934 | 0.0066 |
| Direct Smith09 DMN map 4 | VLPFC > RTPJ | 0.9844 | 0.0156 |
| Direct Smith09 ECN map 8 | RTPJ > BOTH | 0.9800 | 0.0200 |

The repeated DMN direction across data-derived and direct Smith09 network
definitions is encouraging, but all findings remain exploratory. Corrected
p-values control voxel/cluster inference within each randomise job. Each
network/contrast is reported as an individual hypothesis. Following Rubin's
inference-based framework, no blanket across-job alpha adjustment is applied;
an adjustment would be relevant to an "at least one" disjunctive claim. Bar
plots extracted from the same significant clusters are descriptive and are not
independent ROI tests.

## Data-Quality Review

No data-quality exclusion was applied to this N=27 first pass. The earlier
absolute-pairwise screen was superseded because its seven comparisons are
redundant and discard direction.

The current review centers condition values within participant and summarizes
all between-condition variation with three orthogonal signed contrasts.
Within-subject label-permutation tests show no consistent group condition
pattern for tSNR (`p=.58`) or mean FD (`p=.75`). These omnibus tests assess
whether condition labels organize the group profile; they do not select
participants. For participant screening, mean absolute magnitude is calculated
across all three contrasts separately for tSNR and mean FD. Applying the upper
Tukey fence to both distributions identifies `sub-218` as the sole participant
flagged on both metrics. The frozen results remain N=27; this criterion defines
a future N=26 sensitivity analysis. Known stimulation-delivery failures, if
confirmed, remain a separate technical issue.

All 25 jobs (50 tested directions) for `BOTH - mean(RTPJ, VLPFC)` were
nonsignificant. The closest result was the fixed-20 auditory component
(corrected `p=.0506`).

## Secondary Networks

The frozen preliminary results cover only DMN, ECN, and left/right FPN. The
primary visual, occipital-pole, lateral-visual, sensorimotor, and auditory
families have not yet been run. Launchers now cover their ICA-derived matches
and direct Smith09 maps. Cerebellum is omitted because of poor coverage.
