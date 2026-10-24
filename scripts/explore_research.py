"""Reproducible exploratory research extensions; no third-party dependencies."""

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[1]
TIMESTAMPS = (
    "scheduled_departure_utc",
    "actual_departure_utc",
    "scheduled_arrival_utc",
    "landed_status_utc",
)


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def known(row):
    return row["status_display"].strip().casefold() not in ("", "unknown")


def canceled(row):
    return row["status_display"].strip().casefold() == "canceled"


def interval(clusters, seed=20261024, repetitions=2000):
    """Resample dates containing (numerator, denominator) sufficient statistics."""
    if len(clusters) < 2:
        raise ValueError("At least two dates are required for a cluster interval.")
    rng = random.Random(seed)
    estimates = []
    for _ in range(repetitions):
        sample = rng.choices(clusters, k=len(clusters))
        estimates.append(sum(x[0] for x in sample) / sum(x[1] for x in sample))
    return [percentile(estimates, 0.025), percentile(estimates, 0.975)]


def distribution(values):
    return {
        "n": len(values),
        "mean": mean(values),
        "median": median(values),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "ge15_pct": 100 * mean(value >= 15 for value in values),
        "ge60_pct": 100 * mean(value >= 60 for value in values),
    }


def paired_summary(records):
    dep = [record["departure_gap"] for record in records]
    arr = [record["arrival_gap"] for record in records]
    gain = [record["gain"] for record in records]
    late = [record for record in records if record["departure_gap"] >= 15]
    dates = defaultdict(list)
    for record in late:
        dates[record["row"]["local_date"]].append(record)
    recovery_clusters = [
        (sum(record["arrival_gap"] < 15 for record in day), len(day))
        for day in dates.values()
    ]
    return {
        "n": len(records),
        "departure": distribution(dep),
        "arrival": distribution(arr),
        "scheduled_duration_minus_recorded_elapsed_minutes": distribution(gain),
        "positive_gain_pct": 100 * mean(value > 0 for value in gain),
        "departure_ge15_n": len(late),
        "arrival_lt15_among_departure_ge15_n": sum(
            record["arrival_gap"] < 15 for record in late
        ),
        "arrival_lt15_among_departure_ge15_pct": 100
        * mean(record["arrival_gap"] < 15 for record in late),
        "arrival_lt15_among_departure_ge15_date_bootstrap_ci_pct": [
            100 * value for value in interval(recovery_clusters)
        ],
    }


def analyze(csv_path):
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("The input dataset is empty.")
    if len({row["event_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate event_id values: resolve event identity first.")
    dates = sorted({row["local_date"] for row in rows})
    paired = defaultdict(list)
    departures = []
    exclusions = Counter()
    for row in rows:
        direction = row["direction"]
        if direction not in ("arrival", "departure"):
            raise ValueError("Unexpected direction: " + direction)
        if not known(row) or canceled(row):
            exclusions[direction + "_unknown_or_canceled"] += 1
            continue
        if direction == "departure":
            if all(row[name] for name in TIMESTAMPS[:2]):
                scheduled, actual = [
                    datetime.fromisoformat(row[name].replace("Z", "+00:00"))
                    for name in TIMESTAMPS[:2]
                ]
                gap = (actual - scheduled).total_seconds() / 60
                if abs(gap - float(row["timing_difference_minutes"])) > 1e-6:
                    raise ValueError("Inconsistent departure gap: " + row["event_id"])
                departures.append({"row": row, "gap": gap})
            else:
                exclusions["departure_missing_departure_timestamp"] += 1
        if not all(row[name] for name in TIMESTAMPS):
            exclusions[direction + "_missing_paired_timestamp"] += 1
            continue
        scheduled_dep, actual_dep, scheduled_arr, actual_arr = [
            datetime.fromisoformat(row[name].replace("Z", "+00:00"))
            for name in TIMESTAMPS
        ]
        dep_gap = (actual_dep - scheduled_dep).total_seconds() / 60
        arr_gap = (actual_arr - scheduled_arr).total_seconds() / 60
        scheduled_duration = (scheduled_arr - scheduled_dep).total_seconds() / 60
        elapsed = (actual_arr - actual_dep).total_seconds() / 60
        if scheduled_duration <= 0 or elapsed <= 0:
            raise ValueError("Nonpositive leg duration: " + row["event_id"])
        gain = dep_gap - arr_gap
        if abs(gain - (scheduled_duration - elapsed)) > 1e-6:
            raise ValueError("Paired timestamp identity failed: " + row["event_id"])
        paired[direction].append(
            {
                "row": row,
                "departure_gap": dep_gap,
                "arrival_gap": arr_gap,
                "gain": gain,
                "scheduled_duration": scheduled_duration,
                "recorded_elapsed": elapsed,
            }
        )

    paired_results = {}
    for direction, records in paired.items():
        summary = paired_summary(records)
        clean = [
            record for record in records
            if record["row"]["identity_review_required"].casefold() != "true"
            and record["row"]["identity_review"].casefold() != "true"
        ]
        summary["excluding_identity_review"] = paired_summary(clean)
        routes = defaultdict(list)
        for record in records:
            routes[record["row"]["route"]].append(record)
        summary["routes_n_ge100"] = [
            {
                "route": route,
                "n": len(group),
                "median_gain": median(record["gain"] for record in group),
            }
            for route, group in sorted(routes.items())
            if len(group) >= 100
        ]
        paired_results[direction] = summary

    windows = defaultdict(list)
    cells = defaultdict(lambda: defaultdict(list))
    for record in departures:
        hour = int(record["row"]["local_hour"])
        window = "morning" if 6 <= hour <= 11 else (
            "evening" if 17 <= hour <= 22 else None
        )
        if window is not None:
            windows[window].append(record["gap"])
            cells[(record["row"]["local_date"], record["row"]["route"])][window].append(
                record["gap"]
            )
    matched = []
    for (date, route), groups in cells.items():
        if not groups["morning"] or not groups["evening"]:
            continue
        morning, evening = groups["morning"], groups["evening"]
        matched.append(
            {
                "date": date,
                "route": route,
                "n": len(morning) + len(evening),
                "min_window_n": min(len(morning), len(evening)),
                "mean_difference": mean(evening) - mean(morning),
                "ge60_difference_pp": 100 * (
                    mean(value >= 60 for value in evening)
                    - mean(value >= 60 for value in morning)
                ),
            }
        )
    tail = {window: distribution(values) for window, values in windows.items()}
    tail["matched_route_date_cells"] = len(matched)
    tail["matched_records"] = sum(cell["n"] for cell in matched)
    tail["matched_dates"] = len({cell["date"] for cell in matched})
    for metric in ("mean_difference", "ge60_difference_pp"):
        by_date = defaultdict(list)
        for cell in matched:
            by_date[cell["date"]].append(cell[metric])
        tail["matched_" + metric] = mean(cell[metric] for cell in matched)
        tail["matched_" + metric + "_date_bootstrap_ci"] = interval(
            [(sum(values), len(values)) for values in by_date.values()]
        )
    tail["sensitivity_min2_per_window"] = {}
    for metric in ("mean_difference", "ge60_difference_pp"):
        selected = [cell for cell in matched if cell["min_window_n"] >= 2]
        by_date = defaultdict(list)
        for cell in selected:
            by_date[cell["date"]].append(cell[metric])
        tail["sensitivity_min2_per_window"][metric] = {
            "cells": len(selected),
            "dates": len(by_date),
            "estimate": mean(cell[metric] for cell in selected),
            "date_bootstrap_ci": interval(
                [(sum(values), len(values)) for values in by_date.values()]
            ),
        }
    leave_one_date_out = [
        mean(
            cell["ge60_difference_pp"]
            for cell in matched if cell["date"] != date
        )
        for date in dates
    ]
    tail["ge60_difference_pp_leave_one_date_out_range"] = [
        min(leave_one_date_out), max(leave_one_date_out)
    ]

    daily = []
    for date in dates:
        day = [row for row in rows if row["local_date"] == date]
        eligible = [row for row in day if known(row)]
        if len({row["calendar_day_type"] for row in day}) != 1:
            raise ValueError("Inconsistent calendar label: " + date)
        daily.append(
            {
                "date": date,
                "calendar_day_type": day[0]["calendar_day_type"],
                "records": len(day),
                "known": len(eligible),
                "canceled": sum(canceled(row) for row in eligible),
                "canceled_pct": 100 * mean(canceled(row) for row in eligible),
            }
        )
    calendar = []
    for category in sorted({day["calendar_day_type"] for day in daily}):
        group = [day for day in daily if day["calendar_day_type"] == category]
        total, count = sum(day["known"] for day in group), sum(
            day["canceled"] for day in group
        )
        result = {
            "category": category,
            "dates": len(group),
            "known": total,
            "canceled": count,
            "canceled_pct": 100 * count / total,
            "daily_rate_min_max_pct": [
                min(day["canceled_pct"] for day in group),
                max(day["canceled_pct"] for day in group),
            ],
        }
        if len(group) >= 2:
            result["date_bootstrap_ci_pct"] = [
                100 * value for value in interval(
                    [(day["canceled"], day["known"]) for day in group]
                )
            ]
        else:
            result["date_bootstrap_ci_pct"] = None
        calendar.append(result)
    worst = sorted(daily, key=lambda day: day["canceled"], reverse=True)[:5]
    cancellation_total = sum(day["canceled"] for day in daily)
    worst_known = sum(day["known"] for day in worst)
    remaining_known = sum(day["known"] for day in daily) - worst_known
    remaining_canceled = cancellation_total - sum(day["canceled"] for day in worst)
    recurring = defaultdict(list)
    for row in rows:
        if known(row):
            recurring[(row["direction"], row["flight_number"], row["route"])].append(row)
    recurrent = sorted(
        [
            {
                "direction": direction,
                "flight_number": number,
                "route": route,
                "known": len(group),
                "canceled": sum(canceled(row) for row in group),
            }
            for (direction, number, route), group in recurring.items()
            if len(group) >= 15
        ],
        key=lambda group: group["canceled"],
        reverse=True,
    )[:10]
    return {
        "audit": {
            "rows": len(rows),
            "dates": len(dates),
            "date_range": [dates[0], dates[-1]],
            "directions": dict(Counter(row["direction"] for row in rows)),
            "unknown_status": sum(not known(row) for row in rows),
            "canceled": cancellation_total,
            "timing_semantics_verified": dict(
                Counter(row["timing_semantics_verified"] for row in rows)
            ),
            "operating_carrier_nonempty": sum(bool(row["operating_carrier"]) for row in rows),
            "eligible_departures": len(departures),
            "exclusions": dict(exclusions),
        },
        "paired_timestamps": paired_results,
        "morning_evening_tail": tail,
        "cancellations": {
            "daily": daily,
            "calendar": calendar,
            "top5_dates": worst,
            "top5_dates_share_of_cancellations_pct": 100
            * sum(day["canceled"] for day in worst) / cancellation_total,
            "top5_dates_share_of_known_records_pct": 100
            * worst_known / sum(day["known"] for day in daily),
            "top5_dates_cancellation_pct": 100
            * sum(day["canceled"] for day in worst) / worst_known,
            "remaining_dates_cancellation_pct": 100 * remaining_canceled / remaining_known,
            "recurrent_flight_numbers_top10": recurrent,
        },
        "method": {
            "bootstrap_repetitions": 2000,
            "bootstrap_seed": 20261024,
            "bootstrap_unit": "local_date; percentile interval, exploratory not causal",
            "matched_estimand": "Equal-weight mean across observed route-date cells "
            "with at least one eligible departure in each window; resample whole dates.",
            "windows_local_hour": {"morning": [6, 11], "evening": [17, 22]},
            "threshold_minutes": 60,
            "warning": "Exploratory questions chosen after inspecting the dataset. "
            "No confirmatory p-values; timing event semantics are unverified. "
            "Arrival and departure cohorts are reported separately, not pooled.",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "sha_master.csv")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "research_extensions_results.json"
    )
    args = parser.parse_args()
    results = analyze(args.input)
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("Saved exploratory results to", args.output)
    compact = {
        key: value for key, value in results.items()
        if key not in ("paired_timestamps", "cancellations")
    }
    compact["paired_timestamps"] = {
        direction: {
            key: value for key, value in summary.items()
            if key not in ("routes_n_ge100", "excluding_identity_review")
        }
        for direction, summary in results["paired_timestamps"].items()
    }
    compact["cancellations"] = {
        key: value for key, value in results["cancellations"].items()
        if key != "daily"
    }
    print(json.dumps(compact, indent=2))


if __name__ == "__main__":
    main()
