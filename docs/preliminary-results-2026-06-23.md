# Preliminary Resting-State Results - 2026-06-23

## Status

This document freezes the first complete analysis as a preliminary full-sample
result. The corresponding repository state is tagged
`preliminary-results-2026-06-23`. Subsequent QC-exclusion analyses are
sensitivity analyses and must not overwrite these outputs.

## Sample and Workflow

- Analysis sample: 27 participants with four complete, condition-labeled runs
  (108 runs total).
- `sub-212` has only two resting-state runs.
- `sub-233` has four runs but no usable `trial_type` condition labels in the
  tracked BIDS events files.
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

## Prespecified QC Sensitivity

The sensitivity rule excludes participants whose four-run mean FD is greater
than 0.50 mm or whose mean percentage of volumes above 0.20-mm FD is greater
than 50%. This rule was selected from participant-level QC, not from the neural
effect estimates.

| Participant | Mean FD | Mean % FD > 0.20 | Exclusion criterion |
|---|---:|---:|---|
| `sub-218` | 0.506783 | 46.4583 | Mean FD > 0.50 |
| `sub-222` | 0.732145 | 65.6150 | Both criteria |
| `sub-230` | 0.309157 | 55.4527 | Mean percentage > 50 |

The resulting sensitivity sample contains 24 participants. Differential
condition-level boxplot flags support review but are not themselves exclusion
criteria. Known stimulation-delivery failures, if confirmed, must be handled
as a separate technical exclusion.
