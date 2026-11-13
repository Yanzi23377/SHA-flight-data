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

## Importing flight pages

### Browser collector (recommended for historical datasets)

The browser collector uses Microsoft Edge for both login and collection on the
authenticated Flights pages, not the airport board's short history window.
Microsoft Edge must already be installed; there is no fallback to Chrome.
Browser sandboxing is enabled for both login and collection, including cookie
mode. This restores browser security protection; it does not bypass site access
restrictions or guarantee that security verification will succeed.
Install the optional dependency group:

```powershell
uv sync --group collect
uv run --group collect python scripts\collect_flights.py --login
```

Sign in manually in the Edge window that opens, return to the terminal, and press
Enter. This saves a dedicated local profile at `~\.sha-flight-edge-browser`, outside
the repository. Never share or commit that profile. The script does not read
credentials from your ordinary browser or VS Code's shared browser, so signing
in there does not automatically sign in this collector. If you previously used
the Chromium collector, run `--login` again to sign in to the new Edge profile;
the old profile is left untouched.

Alternatively, use `--cookies` to load a local **Netscape-format cookie export**
from your signed-in Edge session, without running `--login`:

```powershell
uv run --group collect python scripts\collect_flights.py --cookies "C:\private\flightradar24-cookies.txt" --start 2026-09-01 --end 2026-10-31 --flight MU5101 --flight CA1502 --flight 9C8946 --output sha_sep_oct_cookie_pilot.csv --run-dir .flight-collection\cookie-pilot
```

Replace the example path with your exported file. This is not Edge's native
`Cookies` database or a JSON export. Any local path is accepted, including
`--cookies .\fr24-cookies.txt` in the repository root. That filename is ignored
by Git; ensure exports with other names are also ignored if stored in the
repository. Never upload an export, paste its values into chat, or commit it. The script imports
only unexpired Flightradar24-domain cookies, preserving their paths, expiry,
Secure and HttpOnly flags. Cookies for other sites are ignored.

Cookie mode launches a temporary Edge session: it does not open or modify your
usual Edge profile, copy cookies into the saved collector profile, or include
cookie values in checkpoints/reports. Edge can remain open normally.
`--cookies` cannot be combined with `--login` or `--profile`.
The collector still requires the Gold/Business indicator on the page before
collecting, waiting up to 20 seconds for the asynchronously rendered indicator.
An imported-cookie count confirms only that the file was read, not that the
website accepted the session. If the cookies expire or are insufficient to authenticate, refresh
the export manually or use `--login`; access challenges are not bypassed.
Supply `--cookies` again when using `--resume`.

First run a pilot across three airlines, without modifying the main dataset:

```powershell
uv run --group collect python scripts\collect_flights.py --start 2026-09-01 --end 2026-10-31 --flight MU5101 --flight CA1502 --flight 9C8946 --output sha_sep_oct_pilot.csv --run-dir .flight-collection\pilot
```

Then expand discovery and collection:

```powershell
uv run --group collect python scripts\collect_flights.py --start 2026-09-01 --end 2026-10-31 --discover --output sha_sep_oct_2026.csv --run-dir .flight-collection\sep-oct
```

For cookie authentication, add `--cookies "C:\private\flightradar24-cookies.txt"`
to this command instead of doing the manual-profile login step.

The default seed is `sha_master.csv`. All its flight numbers/codeshares become
candidates, and its SHA routes are searched in both directions, without an
airline filter. `--seed` also accepts a CSV with a `flight_number` column.
To expand beyond known routes, supply `--routes` with a CSV containing
`origin_iata,destination_iata`; both directions are added automatically.
Use historical route/airline references where available: current route searches
can miss discontinued services, and autocomplete suggestions may be capped.
Discovery records the returned suggestion count and treats results as potentially
truncated rather than claiming completeness.

`--flight` selects specific numbers, while `--limit N` selects the first N sorted
candidates for a pilot. Neither limits the route discovery phase when
`--discover` is present. `--headless` hides the Edge window and works with either
cookie authentication or a previously signed-in collector profile. Cookies
replace interactive login; the browser is still needed for JavaScript, route
search and loading earlier history rows. The window closes when collection
finishes or stops on an error.
The default pause is three seconds between page loads/history requests.
Access errors, challenges, and browser request failures stop collection rather
than trigger automatic bypasses or repeated retries.

For each candidate, the collector reads source Unix timestamps from the table
and loads earlier rows until it crosses the start-date boundary or encounters an
explicit limit. Filtering uses the scheduled event date at SHA (UTC+08:00):
scheduled departure for outbound events, scheduled arrival for inbound events.
It preserves cancelled records and does not treat estimated arrival times as
actual arrivals. Source timing semantics and operating-carrier identity remain
unverified; calendar/holiday labels are not inferred.

Progress is checkpointed after each flight number. Repeat the same command with
`--resume` to reuse completed histories and retry incomplete/failed work.
Keep the same dates, output, template and run directory; remove pilot selectors
when expanding a pilot within the same run. Resume rebuilds the dataset from
cached observations instead of blindly appending duplicates. Output and
checkpoint files are replaced atomically. The collector refuses to overwrite
the seed, template, or master dataset.

Alongside the new CSV, it writes:

- `<output-stem>.candidates.json`: flight numbers and discovery provenance.
- `<output-stem>.coverage.json`: per-number extraction status, route-discovery
  outcomes, counts by day/direction/route/airline display, missing dates,
  identity-review counts, and any collection error.

Stable source flight IDs join codeshare observations where available. Without
one, identities use flight number, route and scheduled timestamp and require
review; they are not automatically merged across different flight numbers.
Conflicting observations are flagged, not silently overwritten.
Airline display labels are not verified operating airlines.

Exit code 2 signals errors, a pagination cap, or history exhaustion before the
requested boundary could be verified; inspect the coverage report before
analysis. **Even exit code 0 does not certify all SHA flights:** it only establishes
successful processing of discovered candidates. The report always marks airport
census completeness as false until independently reconciled against a historical
movement reference. Counts and zero-record days alone cannot prove completeness.

Run the collector and importer tests, including browser tests using local fixtures.
Tests use isolated Chromium instances rather than your signed-in Edge profile:

```powershell
uv run --group collect playwright install chromium
uv run --group collect python -m unittest discover -s tests -v
```

### Using an already-shared VS Code browser tab

If a fresh Edge session encounters a security challenge, an already-authenticated
tab shared with Copilot can supply flight tables instead. Python does **not**
attach to your ordinary Edge window or take its cookies. Copilot operates the
shared tab through VS Code's browser tools, navigating normally and using
"Load earlier flights", then saves only the extracted flight data locally.
Access restrictions stop extraction; this is not a challenge bypass.

`scripts.collect_flights.shared_browser_code(numbers, start, max_pages=30, delay=5)`
generates the browser-tool snippet using the same table extractor as the
standalone collector. It returns a JSON batch with `exports` and a `stopped`
reason. Each export contains `schema_version: 1`, `flight_number`,
`airline_display`, `source_url`, `retrieved_at_utc`, `history_status`, and `rows`.
Save batches under the ignored `.flight-collection\shared-exports` directory.
The history status must be `reached_start`, `history_exhausted_unverified`, or
`page_limit`; a start-boundary claim is checked against the exported dates.

Import those batches into a separate dataset without launching a browser,
reading credentials, or making network requests:

```powershell
uv run python scripts\collect_flights.py --browser-export-dir .flight-collection\shared-exports --start 2026-09-01 --end 2026-10-31 --output sha_sep_oct_shared.csv --run-dir .flight-collection\shared
```

Add `--resume` after saving further batches to the same export directory.
Keep completed batches: a partial snapshot cannot replace completed history.
Among equivalent-coverage snapshots of a flight number, the newest retrieval
is used; re-importing the same batches does not multiply observations.
All batches are validated before caches or the output CSV are replaced.
This import mode does not require Playwright and cannot be combined with
login, cookies, profile, headless, discovery, or flight-selection options.
The coverage report identifies the mode and lists `pending_numbers` from the
seed that have not been processed. Import success describes only exported
flight numbers, not completion of the seed list or an airport census.

### Combining saved history with the existing master

The combined workflow preserves existing master rows and creates a **new**
dataset. For the current master, the existing interval is September 22 through
October 22, 2026; the main gaps are September 1-21 and October 23-31. Trusting
that middle interval is an explicit assumption, not independent verification.

```powershell
uv run python scripts\collect_flights.py --combine-master sha_master.csv --browser-export-dir .flight-collection\shared-exports --review-export-dir .flight-collection\shared-review --trusted-start 2026-09-22 --trusted-end 2026-10-22 --start 2026-09-01 --end 2026-10-31 --delay 5 --output sha_sep_oct_2026_combined.csv --run-dir .flight-collection\sep-oct-combined
```

Omit `--review-export-dir` if you have no additional raw batches. Add `--resume`
for subsequent imports using the same dataset configuration. The pacing
`--delay` may change on resume without resetting collected data. Keep original batches
immutable; add new files rather than replacing or removing imported files.
The existing master is never overwritten. This mode does not launch a browser,
read cookies, or require Playwright.

The output uses the master schema. Matching prefers source flight ID and
direction, checks route consistency, and normalizes timestamp formatting.
Different producers' `event_id` values are not assumed compatible. Distinct
source IDs are not collapsed because they share a scheduled time; ambiguous
fallback matches go to review. Matched master values and IDs are retained.

Alongside the CSV:

- `.coverage.json` distinguishes trusted baseline dates, completed history
  extraction, pending intervals, and unresolved usable coverage.
- `.review.json` preserves conflicting observations, source provenance,
  ambiguous identities, and quarantined raw rows with their failure reasons.
- `.candidates.json` records known flight numbers and their provenance.
- The run directory contains input hashes, a checkpoint, and `jobs.json` with
  uncovered intervals for each remaining number.

Valid rows from a structurally valid raw batch can be imported even when
individual rows lack required timestamps. Those rows are quarantined explicitly;
actual/landed times are never substituted for scheduled times. Malformed batches
still fail before outputs are replaced. Quarantine keeps usable coverage
unresolved, even when history extraction has crossed the requested start date.

Copilot can read `jobs.json` and pass a bounded selection to
`shared_browser_code(..., intervals={number: [[start, end], ...]})`. The worker
uses the earliest requested boundary, preserves loaded rows on a later failure,
and stops on an access error or an incomplete history. Save its returned batch
before importing. Reusing the same shared flight tab retains already-loaded
rows when possible. A lost tab may require pagination again.

Shared-browser pacing defaults to five seconds between collector-initiated page
loads and history actions, with one job at a time. An explicit `delay=2` worker
setting and `--delay 2` combined import allow two-second intervals; shorter
intervals are rejected. Saved complete histories do
not generate new jobs. Newly discovered numbers need their full uncovered
interval. Pages may still return overlapping rows while navigating to older
history; these are not additional unique events. The shared tab is operated
through browser tools, not an unattended Python attachment or background service.
Flight-page navigation allows up to 60 seconds independently of the pacing
interval, so a tool's shorter inherited navigation deadline does not abort a
normally loading page. HTTP errors and security challenges still stop the worker.

Supply `--candidate-file` with a historical discovery CSV containing
`flight_number` and optionally `origin_iata,destination_iata` to add numbers
beyond the master. Current schedules and route autocomplete cannot establish
historical completeness. The observed signed-in SHA arrivals board limits its
calendar to about 48 hours; that board cannot currently enumerate September-
October history. Do not override disabled dates or bypass access restrictions.

An optional `--discovery-report` JSON documents blocked/unverified discovery.
It requires `airport: "SHA"`, matching ISO `start`/`end`, a `status` of
`"blocked"` or `"unverified"`, and a nonempty `reason`. This documents limitations;
it cannot certify an airport census. HTTP 403/429, security challenges, lost
authentication, or inaccessible requested history stop browser collection.
Resume only after access has been resolved.

Exit code 2 reports pending work, quarantine, identity-review observations,
recorded access errors, or blocked discovery. Even exit code 0 does **not**
establish a complete airport census: the coverage flag remains false without
independent historical movement enumeration and event-level reconciliation.
Counts by date, completed seed numbers, and ratios against master row counts
are not airport-coverage percentages.

### Basic HTTP importer

Fetch a specific Flightradar24 flight-history page using a browser-like HTTP GET
and convert its visible history-table rows into the `sha_master.csv` layout:

```bash
uv run python scripts/fetch_flights.py --url https://www.flightradar24.com/data/flights/mu5101 --output imported_flights.csv
```

Repeat `--url` for additional flights. `--timeout` sets the request timeout in
seconds (default: 30). Optional `--cookies` accepts a Netscape-format cookie file,
not a browser's native Cookies database. Treat it as a credential: preferably keep it
outside the repository, otherwise ensure it is ignored by Git, and never share it. Prefer the dedicated browser profile
above for authenticated collection. The `/data/flights` search page is not a flight-history
page and is rejected. Each usable history row becomes a CSV record, with the
flight number taken from the URL, airport codes extracted from the table, and
`retrieved_at_utc` set to the fetch time. Displayed times are preserved as text;
UTC timestamps and local calendar fields are not inferred.

The legacy `--merge` option only appends rows; it does not deduplicate or resolve
flight identities. Do not use it to merge a historical collection into the master.
Use a new output file and the browser collector for resumable historical work.

This uses Python's standard library, does not execute JavaScript, and does not
bypass access restrictions. HTTP failures and pages without usable history rows
are reported as errors before writing the output. Only request pages you are
permitted to access. Remote record IDs identify rows within an import, not stable
flight-event identities across repeated downloads.

### Saved pages (offline)

`scripts/fetch_flights.py` can read HTML pages that you have already saved
and convert recognized table fields into the `sha_master.csv` column layout. It
does not log in, contact Flightradar24, or make any network requests. Create a
manifest CSV with `file,source_url` columns, placing each saved HTML filename
beside its original page URL, then run:

```bash
uv run python scripts/fetch_flights.py --html-dir saved_pages --manifest saved_pages.csv --output imported_flights.csv
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

## Research presentation

`sha_research_presentation.pptx` is a widescreen visual deck with 12 main slides
(approximately 8–10 minutes) and two backup slides. Charts use editable PowerPoint
shapes; detailed explanations, denominators, caveats and references are in the
speaker notes. Replace the title-slide placeholders before presenting.

```bash
uv sync --group report
uv run --group report python scripts/generate_presentation.py
```
