# Randomise Covariate Templates

These small spreadsheets mirror the covariate design matrices used for whole-brain randomise follow-up models. They are tracked in GitHub so the FSL model setup can be reviewed without copying large derivative images.

Each model folder contains one FSL `design.mat` template plus one labeled TSV per contrast. File names include the analysis task, model label, contrast, and contrast-specific N. Columns are ordered as `participant`, `intercept`, then demeaned covariates. The `intercept` column is always `1` and is not demeaned.

The `.mat` files can be passed directly to FSL. The paired TSV files keep the same rows labeled for review.
