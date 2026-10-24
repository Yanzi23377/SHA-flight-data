# SHA flight data

Create research-oriented plots from `sha_master.csv` with Python:

```bash
uv sync
uv run python -m sha_flight_data.plots
```

The four 300-DPI PNG files are written to `plots/`:

- `sha_daily_flight_volume.png` — daily scheduled arrivals and departures.
- `sha_hourly_schedule.png` — schedule volume by local hour at SHA.
- `sha_top_routes.png` — the 15 most frequent directional routes.
- `sha_cancellation_rates.png` — cancellations by calendar day type, using
  records with a known status as the denominator.

To use a different CSV or output directory:

```bash
uv run python -m sha_flight_data.plots --input path/to/flights.csv --output-dir path/to/plots
```

For the research project, see the [documented Jupyter notebook](./sha_flight_plots.ipynb), editable [report source](./research_report.md), and [PDF report](./research_report.pdf), which includes three analysis figures. The report uses a proposed revised scope that omits carrier comparisons because the supplied operating-carrier values are blank and unverified; obtain instructor approval before submission.

```bash
uv run jupyter lab sha_flight_plots.ipynb
```

The report has 3,000-6,000 main-text words (excluding title page and references).
To rebuild it, install the report dependency group and run:

```bash
uv sync --group report
uv run --group report python scripts/generate_report.py
```

The dataset's `timing_semantics_verified` values are all false. The notebook and
report label departure timestamp comparisons as exploratory rather than
validated delay estimates.

## Additional exploratory research

[Research extensions](./research_extensions.ipynb) adds three questions to the
original notebook: paired departure/arrival timestamp gaps, morning/evening
extreme-tail risk matched within route and date, and cancellation concentration.
It reports date-cluster bootstrap intervals, identity-review sensitivity for the
paired analysis, and matched-cell/date sensitivity for the extreme-tail analysis.
These are exploratory associations, not causal or validated delay findings.

Run the notebook from the repository root, or reproduce the numerical results
without third-party dependencies:

```bash
uv run python scripts/explore_research.py
```

The script writes `research_extensions_results.json`. It uses 2,000 whole-date
bootstrap replicates with seed 20261024. The new notebook is separate from the
existing report and does not change its proposed research scope.

An editable Word report, `research_extensions_report.docx`, follows the original
PDF's academic structure and A4 styling, with three figures, five results tables,
references and a reproducibility appendix. Plots fit the text width on portrait pages.
Image paragraphs use automatic line spacing so Word does not clip embedded plots
to the fixed text-line height. Fill in the cover placeholders and
confirm the scope with the instructor before submission. To rebuild it after
running the analysis and refreshing the notebook figures:

```bash
uv sync --group report
uv run --group report python scripts/generate_extensions_document.py
```

## Research presentation

`sha_research_presentation.pptx` is a widescreen visual deck with 12 main slides
(approximately 8–10 minutes) and two backup slides. Charts use editable PowerPoint
shapes; detailed explanations, denominators, caveats and references are in the
speaker notes. Replace the title-slide placeholders before presenting.

```bash
uv sync --group report
uv run --group report python scripts/generate_presentation.py
```
