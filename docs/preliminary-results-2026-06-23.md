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
definitions is encouraging, but all findings remain exploratory. The corrected
p-values control voxel/cluster inference within each randomise job, not the
full family of 77 network-by-condition jobs. Bar plots extracted from the same
significant clusters are descriptive and are not independent ROI tests.

## Differential-Motion QC Sensitivity

The sensitivity rule is based on the seven prespecified condition comparisons,
not participant-average motion thresholds or neural effect estimates. For each
comparison, absolute mean-FD differences and absolute differences in the
percentage of volumes above 0.20-mm FD are screened with separate Tukey upper
fences (`Q3 + 1.5 x IQR`). A comparison receives a paired motion flag only when
both motion metrics exceed their fences. Exclusion requires paired flags in at
least two comparisons. tSNR and participant-average motion remain diagnostics.
The contrasts were planned, but this exact exclusion rule was defined after
reviewing the QC distributions and is therefore a post hoc sensitivity rule.

| Participant | Paired motion flags | Flagged comparisons |
|---|---:|---|
| `sub-222` | 4 | BOTH-RTPJ; RTPJ-SHAM; VLPFC-SHAM; BOTH-mean(RTPJ,VLPFC) |
| `sub-226` | 3 | BOTH-SHAM; BOTH-RTPJ; VLPFC-SHAM |
| `sub-230` | 2 | BOTH-SHAM; RTPJ-SHAM |

The resulting sensitivity sample contains 24 participants. Known
stimulation-delivery failures, if confirmed, require a separate technical
exclusion and a separately labeled analysis.

## Secondary Networks

The frozen preliminary results cover only DMN, ECN, and left/right FPN. The
primary visual, occipital-pole, lateral-visual, sensorimotor, and auditory
families have not yet been run. Launchers now cover their ICA-derived matches
and direct Smith09 maps. Cerebellum is omitted because of poor coverage.
