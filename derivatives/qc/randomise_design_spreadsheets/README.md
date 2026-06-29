# Randomise Design Spreadsheets

These tables are for building FSL `design.mat`, `design.con`, and `design.grp` files in the FSL GLM GUI.

- Order source: `sorted participants complete for all requested contrasts`
- Participants: 27
- EV columns to paste into the design matrix: `EV1_intercept, EV2_delta_fd_mean_demeaned`
- Use the `_demeaned` covariate columns in the design matrix. Raw columns in the audit files are for checking only.
- Use `task-rest_design-contrast-reference.tsv` for the two contrasts: C1 tests the positive mean effect and C2 tests the negative mean effect.
- Use `task-rest_design-group-reference.tsv` for the exchangeability groups; all rows are group 1 for this one-sample model.
