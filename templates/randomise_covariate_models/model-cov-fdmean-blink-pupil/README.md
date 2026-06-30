# Randomise Covariate Design Templates

Model: `cov-fdmean-blink-pupil`

Task: `rest`

Each spreadsheet is ready to paste into the FSL GLM GUI or compare with the generated `design.mat` files. Columns are ordered as `participant`, `intercept`, then demeaned covariates. The intercept column is intentionally not demeaned. File names include the contrast-specific N.

An `_excluded-participants.tsv` file is written only when participants were dropped from that contrast because a required covariate was unavailable.
