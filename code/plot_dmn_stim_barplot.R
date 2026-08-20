# ============================================================================
# Slide 11 / Smith09 DMN component 4
# Reproduce the four-condition Stage-2 beta bar plot in R
#
# Result represented:
#   Smith09 DMN component 4
#   Significant whole-brain contrast: VLPFC > RTPJ
#
# Source data:
#   derivatives/fsl/randomise_summary/
#   task-rest_space-MNI152NLin6Asym_desc-smith09DmnComp0004RtpjMinusVlpfcNegativeClusterExtentCorrp_stat-stage2Beta_timeseries.tsv
#
# The original Python notebook plots condition means +/- SEM for:
#   Sham, RTPJ, VLPFC, BOTH
#
# Run this script from the r21-rest repository or any subdirectory of it.
# Requires: ggplot2, svglite
# ============================================================================

library(ggplot2)

if (!requireNamespace("svglite", quietly = TRUE)) {
  stop(
    "Package 'svglite' is required for editable SVG export. ",
    "Install it with: install.packages('svglite')"
  )
}

# ---- EDIT FIGURE SETTINGS HERE ------------------------------------------------

project_root_override <- NA_character_

condition_order  <- c("sham", "rtpj", "vlpfc", "both")

condition_labels <- c(
  sham  = "Sham",
  rtpj  = "rTPJ",
  vlpfc = "vlPFC",
  both  = "Both"
)

condition_colors <- c(
  sham  = "#8A8F98",
  rtpj  = "#2878B5",
  vlpfc = "#D95F59",
  both  = "#3A9D6F"
)

plot_title <- "VLPFC > RTPJ in the default mode network (DMN)"
y_axis_title <- "Dual-regression stage-2 beta\n(mean ± SEM)"
x_axis_title <- "Stimulation condition"

figure_width  <- 6.6
figure_height <- 4.0

output_subdir <- "figures"

# ---- Locate repository --------------------------------------------------------

find_project_root <- function(start = getwd()) {
  current <- normalizePath(start, winslash = "/", mustWork = TRUE)

  repeat {
    marker <- file.path(current, "derivatives", "fsl", "randomise_summary")

    if (dir.exists(marker)) {
      return(current)
    }

    parent <- dirname(current)

    if (identical(parent, current)) {
      stop(
        "Could not locate the r21-rest repository.\n",
        "Either run this script from inside the repository or set ",
        "'project_root_override' near the top of the script."
      )
    }

    current <- parent
  }
}

if (is.na(project_root_override)) {
  project_root <- find_project_root()
} else {
  project_root <- normalizePath(
    project_root_override,
    winslash = "/",
    mustWork = TRUE
  )
}

message("Project root: ", project_root)

# ---- Load the exact ROI values used for the slide-11 bar plot -----------------

data_file <- file.path(
  project_root,
  "derivatives",
  "fsl",
  "randomise_summary",
  paste0(
    "task-rest_space-MNI152NLin6Asym_",
    "desc-smith09DmnComp0004RtpjMinusVlpfcNegativeClusterExtentCorrp_",
    "stat-stage2Beta_timeseries.tsv"
  )
)

if (!file.exists(data_file)) {
  stop("Could not find source TSV:\n", data_file)
}

dat <- read.delim(
  data_file,
  header = TRUE,
  sep = "\t",
  stringsAsFactors = FALSE,
  check.names = FALSE
)

required_columns <- c("participant", "condition", "stage2_beta")
missing_columns <- setdiff(required_columns, names(dat))

if (length(missing_columns) > 0) {
  stop(
    "Missing required columns: ",
    paste(missing_columns, collapse = ", ")
  )
}

dat$stage2_beta <- as.numeric(dat$stage2_beta)

if (anyNA(dat$stage2_beta)) {
  stop("stage2_beta contains missing or non-numeric values.")
}

dat$condition <- factor(
  dat$condition,
  levels = condition_order
)

if (anyNA(dat$condition)) {
  stop("Found a condition not listed in 'condition_order'.")
}

# ---- Sanity checks ------------------------------------------------------------

condition_n <- table(dat$condition)

message(
  "Observations per condition: ",
  paste(names(condition_n), condition_n, sep = "=", collapse = ", ")
)

if (!all(condition_n == 27)) {
  warning(
    "Expected 27 observations in each condition. ",
    "Check the source data before using the figure."
  )
}

# ---- Compute mean and SEM exactly as in the Python notebook -------------------

sem <- function(x) {
  sd(x) / sqrt(length(x))
}

summary_list <- lapply(
  condition_order,
  function(cond) {
    x <- dat$stage2_beta[dat$condition == cond]

    data.frame(
      condition = cond,
      mean = mean(x),
      sem = sem(x),
      n = length(x),
      stringsAsFactors = FALSE
    )
  }
)

summary_df <- do.call(rbind, summary_list)

summary_df$condition <- factor(
  summary_df$condition,
  levels = condition_order
)

print(summary_df)

# ---- Make the bar plot ---------------------------------------------------------

p <- ggplot(
  summary_df,
  aes(
    x = condition,
    y = mean,
    fill = condition
  )
) +
  geom_hline(
    yintercept = 0,
    color = "#555555",
    linewidth = 0.5
  ) +
  geom_col(
    width = 0.72,
    color = "#222222",
    linewidth = 0.6
  ) +
  geom_errorbar(
    aes(
      ymin = mean - sem,
      ymax = mean + sem
    ),
    width = 0.18,
    linewidth = 0.6,
    color = "#222222"
  ) +
  scale_fill_manual(
    values = condition_colors,
    guide = "none"
  ) +
  scale_x_discrete(
    labels = condition_labels,
    drop = FALSE
  ) +
  scale_y_continuous(
    breaks = scales::breaks_width(0.2)
  ) +
  labs(
    title = plot_title,
    x = x_axis_title,
    y = y_axis_title
  ) +
  theme_classic(base_size = 11) +
  theme(
    plot.title = element_text(
      size = 15,
      face = "plain",
      hjust = 0.5
    ),
    axis.title.x = element_text(
      size = 13,
      margin = margin(t = 8)
    ),
    axis.title.y = element_text(size = 13),
    axis.text = element_text(
      size = 13,
      color = "black"
    ),
    axis.line = element_line(
      color = "#222222",
      linewidth = 0.5
    ),
    axis.ticks = element_line(
      color = "#222222",
      linewidth = 0.5
    ),
    plot.margin = margin(8, 10, 8, 8)
  )

print(p)

# ---- Export -------------------------------------------------------------------

output_dir <- file.path(project_root, output_subdir)

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}



# SVG preserves the plot as editable vector elements for Adobe Illustrator.
svg_file <- file.path(
  output_dir,
  "figure_dmn_stim_barplot.svg"
)

ggsave(
  filename = svg_file,
  plot = p,
  device = svglite::svglite,
  width = figure_width,
  height = figure_height,
  units = "in"
)



message("Saved editable SVG: ", svg_file)