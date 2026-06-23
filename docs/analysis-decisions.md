# Analysis Decisions

The repository covers preprocessing through cluster-extent randomise inference
and portable result visualization. The 27-participant full-sample analysis is
frozen as a preliminary result; a 24-participant QC sensitivity is planned.

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
- The prespecified QC sensitivity excludes `sub-218`, `sub-222`, and `sub-230`
  when four-run mean FD is greater than 0.50 mm or mean percentage of volumes
  above 0.20-mm FD is greater than 50%. This does not resolve or replace a
  separate technical exclusion for failed stimulation delivery.
- Group MELODIC components will be compared with Smith09 PNAS maps. Primary
  networks are DMN, ECN, and left/right FPN; secondary networks include
  cerebellum and sensorimotor components.
- ICA matches are ranked by absolute spatial correlation because component
  polarity is arbitrary; the signed correlation remains in the output table.
- Dual regression with resampled Smith09 maps will provide an atlas-based
  sensitivity analysis independent of the data-derived ICA solutions.
- Dual regression uses design normalization of stage-1 timecourses. Primary
  condition differences use the resulting raw stage-2 coefficient maps, not
  the `_Z` maps. Nickerson et al. (2017, doi:10.3389/fnins.2017.00115) identify
  design-normalized stage-2 coefficients as the valid group-inference measure;
  Z maps additionally mix the effect estimate with run-specific uncertainty
  and are reserved for sensitivity checks.
- Bijsterbosch et al. (2018, doi:10.7554/eLife.32992) support treating
  dual-regression stage-2 spatial maps as meaningful subject-varying measures,
  but do not establish Z maps as preferable to coefficient maps.
- Component-wise condition differences are constructed from complete sets of
  one `SHAM`, `RTPJ`, `VLPFC`, and `BOTH` run per participant. Missing or
  duplicate conditions stop the analysis rather than silently changing the
  sample.
- Primary one-sample permutation tests use 5,000 permutations and
  cluster-extent inference with a cluster-forming t threshold of 3.1 (`-c
  3.1`). Both positive and negative condition-difference contrasts are tested.
  TFCE is not interpreted.
- The first randomise pass includes DMN from both denoised ICA solutions. The
  expanded primary pass adds ECN and FPN, while running dim-20 component 8 only
  once because it is the best match for both left and right FPN.
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
