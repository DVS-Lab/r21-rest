# Analysis Decisions

The repository covers fMRIPrep, MRIQC, confound extraction, joint nuisance
regression, MELODIC input checks, group-MELODIC launching, completion checks,
network matching, and standard dual regression. Final QA exclusions,
run-difference images, and randomise designs remain.

## Current Study Context

The resting-state fMRI project includes four within-participant stimulation
conditions:

- `SHAM`: no active stimulation
- `RTPJ`: stimulation at the RTPJ site
- `VLPFC`: stimulation at the VLPFC site
- `BOTH`: simultaneous stimulation at both sites

The project is not currently being treated as a simple 2 x 2 factorial design.

## Analysis Decisions

- Volumetric MNI152NLin6Asym data are smoothed and masked to a final 5-mm FWHM
  with AFNI `3dBlurToFWHM`.
- Surface data would require a separate Connectome Workbench smoothing step.
- The 24 extended motion parameters, continuous FD, six aCompCor components,
  non-steady-state regressors, cosine terms, and a constant are projected from
  each run in one joint `3dTproject` model before group ICA.
- Group MELODIC and both stages of the original FSL `dual_regression` use the
  same cleaned data. Nuisance regression and temporal filtering are not
  repeated later.
- Group MELODIC will be run with fixed dimensionality 20 and with automatic
  dimensionality estimation.
- QA will include motion and MRIQC outlier identification consistent with prior
  lab work, including boxplot/IQR-based flags.
- Differential QA will use two-sided Tukey 1.5-IQR boxplot fences on tSNR, mean
  FD, and FD percentage differences for `BOTH - SHAM`, `BOTH - RTPJ`,
  `BOTH - VLPFC`, `RTPJ - VLPFC`, `RTPJ - SHAM`, `VLPFC - SHAM`, and
  `BOTH - mean(RTPJ, VLPFC)`. These correlated flags supplement absolute
  subject-level QA, identify runs for visual review, and do not automatically
  exclude participants.
- Subject exclusions should not be finalized until the stimulation-delivery
  concern is resolved.
- Group MELODIC components will be compared with Smith09 PNAS maps. Primary
  networks are DMN, ECN, and left/right FPN; secondary networks include
  cerebellum and sensorimotor components.
- ICA matches are ranked by absolute spatial correlation because component
  polarity is arbitrary; the signed correlation remains in the output table.
- Dual regression with resampled Smith09 maps will provide an atlas-based
  sensitivity analysis independent of the data-derived ICA solutions.
- Automated QA should flag observations rather than silently exclude them.
- Bonferroni correction may eventually be used across the primary inferential
  family.

## Planned Comparisons

- `BOTH` versus `SHAM`
- `BOTH` versus `RTPJ`
- `BOTH` versus `VLPFC`
- `RTPJ` versus `VLPFC`
- `RTPJ` versus `SHAM`
- `VLPFC` versus `SHAM`
- `BOTH` versus the average of `RTPJ` and `VLPFC`

The meaning of "bidirectional" remains unresolved. It may mean two-sided
inference, or it may mean explicit positive and negative directional contrasts.
