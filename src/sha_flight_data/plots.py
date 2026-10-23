import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


Flight = Dict[str, str]
REQUIRED_COLUMNS = {
    "calendar_day_type",
    "direction",
    "local_date",
    "local_hour",
    "route",
    "status_display",
}
CALENDAR_ORDER = (
    "ordinary_weekday",
    "public_holiday",
    "weekend",
    "adjusted_workday",
)
CALENDAR_LABELS = {
    "ordinary_weekday": "Ordinary weekday",
    "public_holiday": "Public holiday",
    "weekend": "Weekend",
    "adjusted_workday": "Adjusted workday",
}


def read_flights(csv_path: Path) -> List[Flight]:
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        columns = set(reader.fieldnames or ())
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(
                "CSV is missing required columns: " + ", ".join(sorted(missing))
            )
        flights = list(reader)

    if not flights:
        raise ValueError("CSV contains no flight records.")
    return flights


def plot_daily_volume(flights: List[Flight], output_path: Path) -> None:
    counts = defaultdict(Counter)
    for flight in flights:
        counts[flight["local_date"]][flight["direction"]] += 1

    dates = sorted(counts)
    figure, axes = plt.subplots(figsize=(11, 5))
    for direction, label, color in (
        ("arrival", "Arrivals", "#2878B5"),
        ("departure", "Departures", "#E07A32"),
    ):
        axes.plot(
            dates,
            [counts[date][direction] for date in dates],
            marker="o",
            markersize=3,
            linewidth=1.8,
            label=label,
            color=color,
        )

    axes.set_title("Scheduled flights per day")
    axes.set_xlabel("Local date at Shanghai Hongqiao (SHA)")
    axes.set_ylabel("Scheduled flight records")
    axes.tick_params(axis="x", rotation=45)
    axes.grid(axis="y", alpha=0.25)
    axes.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def plot_hourly_schedule(flights: List[Flight], output_path: Path) -> None:
    counts = defaultdict(Counter)
    for flight in flights:
        hour = int(flight["local_hour"])
        if not 0 <= hour <= 23:
            raise ValueError(
                "Invalid local_hour {!r} for flight {!r}.".format(
                    flight["local_hour"], flight.get("event_id", "")
                )
            )
        counts[hour][flight["direction"]] += 1

    hours = list(range(24))
    figure, axes = plt.subplots(figsize=(10, 5))
    for direction, label, color in (
        ("arrival", "Arrivals", "#2878B5"),
        ("departure", "Departures", "#E07A32"),
    ):
        axes.plot(
            hours,
            [counts[hour][direction] for hour in hours],
            marker="o",
            markersize=3,
            linewidth=1.8,
            label=label,
            color=color,
        )

    axes.set_title("Scheduled flights by local hour")
    axes.set_xlabel("Scheduled local hour at SHA (24-hour clock)")
    axes.set_ylabel("Scheduled flight records")
    axes.set_xticks(hours)
    axes.grid(axis="y", alpha=0.25)
    axes.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def plot_top_routes(flights: List[Flight], output_path: Path) -> None:
    route_counts = Counter(flight["route"] for flight in flights)
    top_routes = route_counts.most_common(15)
    labels = [route for route, _ in reversed(top_routes)]
    values = [count for _, count in reversed(top_routes)]

    figure, axes = plt.subplots(figsize=(9, 7))
    bars = axes.barh(labels, values, color="#2878B5")
    axes.bar_label(bars, padding=3, fontsize=8)
    axes.set_title("15 most frequent directional routes")
    axes.set_xlabel("Scheduled flight records")
    axes.set_ylabel("Route (origin–destination)")
    axes.grid(axis="x", alpha=0.25)
    axes.set_axisbelow(True)
    figure.tight_layout()
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def plot_cancellation_rates(flights: List[Flight], output_path: Path) -> None:
    totals = Counter()
    cancellations = Counter()
    unknown_statuses = 0

    for flight in flights:
        category = flight["calendar_day_type"]
        status = flight["status_display"].strip().casefold()
        if not status or status == "unknown":
            unknown_statuses += 1
            continue
        totals[category] += 1
        if status == "canceled":
            cancellations[category] += 1

    categories = [
        category
        for category in CALENDAR_ORDER
        if totals[category]
    ]
    labels = [CALENDAR_LABELS.get(category, category) for category in categories]
    rates = [
        cancellations[category] / totals[category] * 100
        for category in categories
    ]

    figure, axes = plt.subplots(figsize=(9, 5))
    bars = axes.bar(labels, rates, color="#5A9E6F")
    for bar, category in zip(bars, categories):
        axes.annotate(
            "{:.1f}% ({}/{})".format(
                cancellations[category] / totals[category] * 100,
                cancellations[category],
                totals[category],
            ),
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    axes.set_title("Status-based cancellation rate by calendar day type")
    axes.set_xlabel("Calendar day type")
    axes.set_ylabel("Canceled / known-status records (%)")
    axes.grid(axis="y", alpha=0.25)
    axes.set_axisbelow(True)
    if rates:
        axes.set_ylim(0, max(rates) * 1.25)
    figure.text(
        0.01,
        0.01,
        "Unknown or blank status excluded: {} record(s).".format(unknown_statuses),
        ha="left",
        fontsize=8,
        color="#555555",
    )
    figure.tight_layout(rect=(0, 0.04, 1, 1))
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def create_plots(csv_path: Path, output_dir: Path) -> List[Path]:
    flights = read_flights(csv_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    plots = [
        ("sha_daily_flight_volume.png", plot_daily_volume),
        ("sha_hourly_schedule.png", plot_hourly_schedule),
        ("sha_top_routes.png", plot_top_routes),
        ("sha_cancellation_rates.png", plot_cancellation_rates),
    ]
    output_paths = []
    for filename, plot_function in plots:
        output_path = output_dir / filename
        plot_function(flights, output_path)
        output_paths.append(output_path)
    return output_paths


def main(argv: Optional[List[str]] = None) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Create research-oriented plots from the SHA flight dataset."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=repository_root / "sha_master.csv",
        help="Path to the flight CSV (default: sha_master.csv in the project root).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repository_root / "plots",
        help="Directory for generated PNG files (default: plots/).",
    )
    args = parser.parse_args(argv)

    for output_path in create_plots(args.input, args.output_dir):
        print("Saved {}".format(output_path))


if __name__ == "__main__":
    main()
