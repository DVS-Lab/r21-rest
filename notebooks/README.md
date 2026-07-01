# Randomise Results Notebook

`plot_randomise_results.ipynb` displays every significant N=27 primary and
secondary cluster-extent result in its own interactive NiiVue MNI viewer. Each
result includes a plain-language description of the analysis, network, signed
contrast, corrected peak p-value, and cluster size, followed by sham, RTPJ,
VLPFC, and BOTH dual-regression stage-2 beta means with SEM.

The notebook also correlates each extracted brain contrast with the matching
signed pupil and blink-rate deltas from the primary N=27 subject set.

The notebook also audits every planned contrast, so nonsignificant comparisons
do not disappear. Its QC section uses only tSNR and mean FD. It shows centered
condition boxplots, three orthogonal signed-contrast boxplots, and participant
boxplots of mean absolute magnitude across those three contrasts. The Tukey
rule identifies `sub-218` on both metrics as a sensitivity-analysis candidate.

Run the result checker before opening the notebook. Then close any existing
JupyterLab server and use the project launcher:

```bash
python3 code/check_randomise_results.py --analysis-set all --fail-on-missing
python3 code/check_randomise_results.py \
  --network-set secondary \
  --analysis-set all \
  --fail-on-missing
bash notebooks/run_randomise_notebook.sh
```

The result checker uses the Linux-side dual-regression images to write compact
participant-by-condition `*_timeseries.tsv` files beside each significant map.
Commit those TSVs with the updated summary, NIfTI maps, and JSON sidecars. The
notebook reads only these tracked files and therefore does not require the
large dual-regression directories, FSL, or Neurodesk on another computer.

The launcher installs `notebooks/requirements.txt` before starting JupyterLab.
This ordering is required because IPyNiiVue uses AnyWidget in both the Python
kernel and the JupyterLab browser frontend. Installing from a cell in an
already-running Lab session can leave the frontend unregistered. If Lab was
already open during installation, stop it with `Ctrl-C`, rerun the launcher,
and refresh the browser tab.

## Sharing Rendered Output

Running every cell, saving the notebook, and committing the resulting `.ipynb`
allows collaborators to view saved text, tables, bar plots, boxplots, and the
static brain-map fallback on GitHub without executing Python. NiiVue is a live
widget and GitHub's static notebook renderer does not execute it; collaborators
must run the notebook to use NiiVue interactively. A saved notebook can also be
exported as a convenient standalone static HTML file:

```bash
python3 -m jupyter nbconvert \
  --to html \
  --HTMLExporter.embed_images=True \
  --output plot_randomise_results_rendered.html \
  notebooks/plot_randomise_results.ipynb
```

Collaborators can download and open that HTML file directly without Python.
Keep the executed notebook or rendered HTML only when intentionally publishing
a result snapshot; the source notebook otherwise remains output-free for clean
review.

Only cluster-extent results are displayed. The notebook reads both tracked
randomise summary tables and intentionally ignores TFCE. The region is selected
from the same group contrast summarized in the bar plot, so the condition means
and SEM are descriptive and must not be treated as
independent ROI inference. Each network/contrast is reported as an individual
hypothesis. Following Rubin's inference-based framework, an across-job alpha
adjustment is relevant to a disjunctive claim that at least one result exists,
not automatically to separate inferences about each reported hypothesis.

## Covariate Randomise Scatterplots

`plot_covariate_randomise_scatterplots.ipynb` is separate from the main
brain-map notebook. It reads
`derivatives/fsl/covariate_randomise_summary/task-rest_covariate-randomise_peak_summary.tsv`
and reviews both pieces of the covariate models: C3/C4, the blink or pupil
covariate-effect contrasts, and C1/C2, the adjusted main-effect contrasts.
The C1/C2 section compares the original 12 significant cluster-extent results
against the FD+blink and FD+pupil adjusted versions.

Launch it with:

```bash
bash notebooks/run_covariate_randomise_notebook.sh
```

The current covariate summary has complete C3/C4 rows, but no C3/C4 map crossed
the `1-p > 0.95` corrected threshold, so no C3/C4 ROI-value TSVs were copied by
the compiler. The notebook therefore shows the sorted C3/C4 peak audit and will
automatically render scatterplots once C3/C4 ROI-value TSVs are available. In
those scatterplots, the y axis is subject-level brain contrast beta from the
corrected ROI and the x axis is the raw blink or pupil contrast delta; mean FD
is included in the randomise model but is not plotted on the x axis.

The C1/C2 scatterplots are descriptive checks for adjusted main-effect ROIs,
not the formal covariate-effect tests. The notebook also reads the optional
`task-rest_covariate-randomise_integrity.tsv` file written by
`code/check_covariate_model_integrity.py` when it is available.
