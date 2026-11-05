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

## China National Day holiday flight project

`national_day_research_project.pdf` is a transportation-engineering research
paper on
flight-event patterns at Shanghai Hongqiao Airport during October 1-7, 2026.
It states the transport-planning problem and research contribution, includes
five figures, and compares the holiday week with adjacent, weekday-aligned
seven-day periods. It also examines China's adjusted-workday calendar: October
10 is flagged as an adjusted workday, and the prior comparison week includes
the September 25-27 Mid-Autumn public holidays. The paper distinguishes flight
records from passenger demand and explains why this dataset cannot measure
traveler motives, emissions, or causal holiday effects. Replace the author,
course, and submission-date placeholders before submission.

Regenerate the PDF and its charts with:

```bash
uv run --group report python scripts/generate_national_day_report.py
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

## Importing flight pages

Fetch a specific Flightradar24 flight-history page using a browser-like HTTP GET
and convert its visible history-table rows into the `sha_master.csv` layout:

```bash
uv run python scripts/import_saved_pages.py --url https://www.flightradar24.com/data/flights/mu5101 --output imported_flights.csv
```

Repeat `--url` for additional flights. `--timeout` sets the request timeout in
seconds (default: 30). The `/data/flights` search page is not a flight-history
page and is rejected. Each usable history row becomes a CSV record, with the
flight number taken from the URL, airport codes extracted from the table, and
`retrieved_at_utc` set to the fetch time. Displayed times are preserved as text;
UTC timestamps and local calendar fields are not inferred.

This uses Python's standard library, does not execute JavaScript or log in, and
does not bypass access restrictions. HTTP failures and pages without usable
history rows are reported as errors before writing the output. Only request
pages you are permitted to access. Remote record IDs identify rows within an
import, not stable flight-event identities across repeated downloads.

### Saved pages (offline)

`scripts/import_saved_pages.py` can read HTML pages that you have already saved
and convert recognized table fields into the `sha_master.csv` column layout. It
does not log in, contact Flightradar24, or make any network requests. Create a
manifest CSV with `file,source_url` columns, placing each saved HTML filename
beside its original page URL, then run:

```bash
uv run python scripts/import_saved_pages.py --html-dir saved_pages --manifest saved_pages.csv --output imported_flights.csv
```

Only recognized table labels are mapped; missing fields remain blank, and
`timing_semantics_verified` is set to `false`. The parser cannot reliably infer
timestamps or fields absent from the saved tables. Review and validate the
output before using it for analysis. The input HTML and manifest must be
obtained through access permitted by the source service.

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

## Word report and documented notebook

The Word-format academic submission package is in
[final_project_word](./final_project_word):

- [sha_national_day_final_report.docx](./final_project_word/sha_national_day_final_report.docx)
  contains a title page, introduction and literature review, methods, results,
  conclusions, and references. Its main text is approximately 3,356 words.
- [sha_national_day_final.ipynb](./final_project_word/sha_national_day_final_executed.ipynb)
  is the documented and executed notebook used for the three approved questions.
- [sha_national_day_final_results.json](./final_project_word/sha_national_day_final_results.json)
  contains the machine-readable summary values.

Rebuild and execute the package with:

```bash
uv run --group report python scripts/build_word_final_project.py
uv run --group report jupyter nbconvert --execute --to notebook \
  final_project_word/sha_national_day_final.ipynb \
  --output sha_national_day_final_executed.ipynb
```

The report uses a conventional academic structure and clearly states that course-specific
formatting or referencing instructions should be checked against the instructor's page
before submission.

## Final three-question project

A consolidated, reproducible project for the revised three-question scope is
available in [final_project/final_project.pdf](./final_project/final_project.pdf)
and [final_project/final_project.md](./final_project/final_project.md). It
compares equal seven-day calendar phases, reports daily trends and missing
status data, distinguishes a 60-minute recorded timestamp-gap threshold from
verified operational delays, compares disruption by date and hour, and treats
October 10 as a single adjusted-workday case study against the three ordinary
weekend dates in the dataset.

Regenerate the project with:

```bash
uv run python scripts/build_final_project.py
```

The script writes figures and machine-readable results to `final_project/`.

## Research presentation

`sha_research_presentation.pptx` is a widescreen visual deck with 12 main slides
(approximately 8–10 minutes) and two backup slides. Charts use editable PowerPoint
shapes; detailed explanations, denominators, caveats and references are in the
speaker notes. Replace the title-slide placeholders before presenting.

```bash
uv sync --group report
uv run --group report python scripts/generate_presentation.py
```
