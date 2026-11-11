# Adjusted-workday analysis and report update plan

## Purpose

Investigate whether Shanghai Hongqiao flight-event volume, cancellations, and departure delays differed on China's National Day make-up workdays, then update the final notebook and Word report with descriptive results and appropriately qualified conclusions.

## What the current evidence supports

- The calendar image marks Sunday, September 20, and Saturday, October 10, 2026, as National Day make-up workdays.
- `sha_master.csv` covers September 22–October 22, so it excludes September 20. October 10 is the only adjusted-workday date represented.
- On October 10, the dataset has 682 flight-event records (342 arrivals and 340 departures), 680 known statuses, and 30 cancellations: a 4.41% cancellation rate.
- The closest available ordinary-Saturday comparison is October 17: 775 records (387 arrivals and 388 departures), 775 known statuses, and 8 cancellations (1.03%). October 10 has 12.0% fewer recorded events and a 3.38 percentage-point higher cancellation rate in this one-date comparison.
- For the departure-delay measure, October 10 has 0 of 323 eligible departures delayed by at least 60 minutes; October 17 has 14 of 384 (3.65%). The analysis assumes the scheduled and actual departure timestamps are accurate, although the source verification flag is false.
- These are counts of recorded flight events, not passenger counts or a complete measure of scheduled service. A single adjusted workday versus a single ordinary Saturday cannot establish an effect or its cause.

## Analysis steps

1. **Verify calendar scope and labels.** Confirm the two dates and their classifications against the calendar source already recorded in the dataset. Clearly note that September 20 is outside the data-collection window; do not treat it as a zero-flight day.
2. **Define the comparison groups.** Report October 10 separately. Use October 17 as the closest ordinary-Saturday reference, show October 11 and October 18 as additional ordinary-weekend context, and include all weekend dates while clearly separating public-holiday weekends from ordinary weekends.
3. **Calculate comparable outcomes.** For each date, report total recorded events and arrivals/departures; known and unknown status counts; cancellations and cancellation rate (cancellations ÷ known-status records, expressed as a percentage); scheduled-hour profile; and, for eligible non-cancelled departures only, the count and proportion delayed by at least 60 minutes.
4. **Check sensitivity and completeness.** Show denominators beside every rate, compare status completeness, and avoid interpreting lower event counts as lower actual service unless record coverage and the scheduled-flight denominator can be established. Treat the single-date comparisons as descriptive, not statistical evidence of a general calendar effect.
5. **State what stronger evidence would require.** To assess a recurring adjusted-workday effect, extend collection to September 20 and obtain multiple years or holiday periods, complete scheduled-flight coverage, and relevant controls such as route, airline, hour, weather, and operational conditions. Passenger-demand claims require passenger data. Consider matched-day or regression analysis only after enough comparable dates and coverage are available.

## Notebook and Word report update sequence

1. Extend the existing pandas analysis with an adjusted-workday date table, the explicitly matched October 10/October 17 comparison, and concise plots or tables for event volume, direction, cancellation rate, hour profile, and eligible recorded-gap rate.
2. Add a methods note, limitations, and a short interpretation that distinguishes association from causation and recorded events from actual passenger demand.
3. Update the shared analysis and notebook/report-generation logic in `scripts/build_word_final_project.py` so generated material stays consistent. Regenerate the notebook and Word report, then synchronize and execute the final executed notebook used for submission.
4. Review the Word report's tables, figures, conclusions, and required word-count range; check that all reported numerators, denominators, dates, and labels agree with the notebook outputs.
5. Validate by rerunning the analysis from `sha_master.csv`, comparing its results with the report, and checking the final notebook for execution errors.

## Completed

- Added pandas-based weekend and adjusted-workday analysis to the notebook.
- Compared October 10 with October 17 and included the other weekend dates with public-holiday classifications kept distinct.
- Added event direction, known/unknown status, cancellations, local-hour event counts, and eligible ≥60-minute recorded-gap outcomes.
- Updated the reproducible generator, final notebook, executed notebook, results JSON, figures, and Word report.
- Executed all six notebook code cells and checked the reported October 10 and October 17 values against the generated results and Word tables. The report remains within its 3,000–6,000-word main-text requirement.

The result remains descriptive: only October 10 of the two calendar make-up workdays is observed, and the flight-event records do not establish passenger demand, complete scheduled-flight coverage, or causal effects.
