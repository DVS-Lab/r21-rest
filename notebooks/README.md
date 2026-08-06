# Results Notebooks

The two final shareable reports use the original 10 Smith09 maps, the N=27
sample, and three nonredundant condition contrasts:

1. mean(RTPJ, VLPFC, BOTH) - sham
2. BOTH - mean(RTPJ, VLPFC)
3. RTPJ - VLPFC

Only cluster-extent inference is reported (5,000 permutations,
cluster-forming `t=3.1`). TFCE is intentionally omitted. Because FSL writes
separate positive and negative one-tailed tests, the reports use the
conservative two-sided value `min(1, 2 * p_best_tail)`.

## Primary Connectivity

`plot_randomise_results.ipynb` reports direct Smith09 DMN and ECN
dual-regression results. It contains a complete audit of the planned
network-by-contrast tests and displays each significant result with a static
MNI brain image and four-condition mean plus SEM plot.

The executed notebook and standalone HTML are committed as:

```text
notebooks/plot_randomise_results.ipynb
notebooks/plot_randomise_results_rendered.html
```

## Network Coupling and PPI

`plot_network_correlation_ppi_results.ipynb` reports full and partial
DMN coupling with ECN, left FPN, and right FPN. It also reports the secondary
voxelwise DMN x ECN physio-physio interaction analysis from the original
10-map model. Significant PPI results include a static MNI brain image and a
four-condition mean plus SEM plot.

The original 10-map PPI results now include all three final contrasts. The
mean-stimulation-minus-sham test is complete and null; the other two contrasts
have corrected maps and four-condition plots in the report.

The executed notebook and standalone HTML are committed as:

```text
notebooks/plot_network_correlation_ppi_results.ipynb
notebooks/plot_network_correlation_ppi_results_rendered.html
```

## Running Locally

The reports read only compact, GitHub-tracked TSV, NIfTI, and JSON files. They
do not require the large Linux dual-regression directories or FSL.

```bash
bash notebooks/run_randomise_notebook.sh
bash notebooks/run_network_correlation_ppi_notebook.sh
```

To refresh the standalone HTML after executing and saving a notebook:

```bash
python3 -m jupyter nbconvert \
  --to html \
  --HTMLExporter.embed_images=True \
  --output plot_randomise_results_rendered.html \
  notebooks/plot_randomise_results.ipynb

python3 -m jupyter nbconvert \
  --to html \
  --HTMLExporter.embed_images=True \
  --output plot_network_correlation_ppi_results_rendered.html \
  notebooks/plot_network_correlation_ppi_results.ipynb
```

## Covariate Follow-Up

`plot_covariate_randomise_scatterplots.ipynb` remains a separate follow-up
report for FD+blink and FD+pupil models. C1/C2 are shown as adjusted brain maps
with four-condition bar plots; C3/C4 covariate effects use scatterplots when a
corrected ROI is available.

```bash
bash notebooks/run_covariate_randomise_notebook.sh
```

All ROI bar plots are descriptive summaries extracted from the same corrected
cluster used to identify the result and are not independent ROI tests.
