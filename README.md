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
