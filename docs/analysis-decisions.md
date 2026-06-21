# Analysis Decisions

The repository covers fMRIPrep, MRIQC, confound extraction, group-MELODIC
launching, completion checks, and confound-aware dual regression. Network
matching, QA exclusions, run-difference images, and randomise remain.

## Current Study Context

The resting-state fMRI project includes four within-participant stimulation
conditions:

- `SHAM`: no active stimulation
- `RTPJ`: stimulation at the RTPJ site
- `VLPFC`: stimulation at the VLPFC site
- `BOTH`: simultaneous stimulation at both sites

The project is not currently being treated as a simple 2 x 2 factorial design.

## Deferred Methodological Decisions

- Volumetric data may later receive minimal 4-mm FWHM SUSAN smoothing.
- Surface data would require a separate Connectome Workbench smoothing step.
- Nuisance regressors are included in stage 2 of the modified FSL
  `dual_regression` procedure.
- fMRIPrep outputs should not be nuisance-regressed during this preprocessing
  assignment.
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
- Automated QA should flag observations rather than silently exclude them.
- Bonferroni correction may eventually be used across the primary inferential
  family.

## Provisional Comparisons for Later Discussion

- `BOTH` versus `SHAM`
- `BOTH` versus the average of `RTPJ` and `VLPFC`
- `RTPJ` versus `VLPFC`

The meaning of "bidirectional" remains unresolved. It may mean two-sided
inference, or it may mean explicit positive and negative directional contrasts.
