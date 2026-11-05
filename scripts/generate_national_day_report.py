"""Build a publication-style exploratory report on China's 2026 National Day flights."""

import argparse
import csv
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sha_master.csv"
DEFAULT_OUTPUT = ROOT / "national_day_research_project.pdf"
FIGURE_DIR = ROOT / "national_day_figures"
HOLIDAY_START = date(2026, 10, 1)
PERIODS = (
    ("Pre-holiday", HOLIDAY_START - timedelta(days=7), HOLIDAY_START - timedelta(days=1)),
    ("National Day", HOLIDAY_START, HOLIDAY_START + timedelta(days=6)),
    ("Post-holiday", HOLIDAY_START + timedelta(days=7), HOLIDAY_START + timedelta(days=13)),
)
REQUIRED_COLUMNS = {
    "event_id",
    "direction",
    "local_date",
    "local_hour",
    "route",
    "status_display",
    "weekday",
    "calendar_day_type",
    "adjusted_workday",
}
NAVY = "#17324d"
BLUE = "#2878B5"
TEAL = "#5A9E8F"
ORANGE = "#E07A32"
LIGHT_BLUE = "#D9E5EE"


def read_records(path):
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError("Dataset is missing required columns: " + ", ".join(sorted(missing)))
        rows = list(reader)
    if not rows:
        raise ValueError("The input dataset is empty.")
    ids = [row["event_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate event_id values found; resolve event identity before analysis.")
    for row in rows:
        try:
            row["_date"] = date.fromisoformat(row["local_date"])
            row["_hour"] = int(row["local_hour"])
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid local_date or local_hour in event " + row["event_id"]) from exc
        if row["direction"] not in ("arrival", "departure"):
            raise ValueError("Unexpected direction in event " + row["event_id"])
    return rows


def is_known_status(row):
    return row["status_display"].strip().casefold() not in ("", "unknown")


def is_canceled(row):
    return row["status_display"].strip().casefold() == "canceled"


def summarize_calendar_days(rows):
    records_by_date = defaultdict(list)
    for row in rows:
        records_by_date[row["_date"]].append(row)

    summaries = defaultdict(list)
    for day, day_rows in sorted(records_by_date.items()):
        categories = {row["calendar_day_type"] for row in day_rows}
        adjustment_flags = {row["adjusted_workday"].strip().casefold() for row in day_rows}
        if len(categories) != 1 or len(adjustment_flags) != 1:
            raise ValueError("Inconsistent calendar classification on " + day.isoformat())
        category = categories.pop()
        adjusted = adjustment_flags.pop()
        if adjusted not in ("true", "false"):
            raise ValueError("Invalid adjusted_workday flag on " + day.isoformat())
        if (adjusted == "true") != (category == "adjusted_workday"):
            raise ValueError("Calendar category and adjusted_workday flag disagree on " + day.isoformat())
        known = [row for row in day_rows if is_known_status(row)]
        summaries[category].append(
            {
                "date": day,
                "weekday": day_rows[0]["weekday"],
                "events": len(day_rows),
                "known": len(known),
                "canceled": sum(is_canceled(row) for row in known),
                "adjusted": adjusted == "true",
            }
        )
    return summaries


def summarize(rows):
    date_counts = defaultdict(Counter)
    period_rows = {}
    for row in rows:
        day = row["_date"]
        date_counts[day]["all"] += 1
        date_counts[day][row["direction"]] += 1
        if is_known_status(row):
            date_counts[day]["known"] += 1
            if is_canceled(row):
                date_counts[day]["canceled"] += 1

    for label, start, end in PERIODS:
        selected = [row for row in rows if start <= row["_date"] <= end]
        present_dates = {row["_date"] for row in selected}
        expected_dates = {start + timedelta(days=offset) for offset in range(7)}
        if present_dates != expected_dates:
            raise ValueError(
                "{} window must contain records for all seven dates; found {} of 7.".format(
                    label, len(present_dates)
                )
            )
        known = [row for row in selected if is_known_status(row)]
        canceled = [row for row in known if is_canceled(row)]
        period_rows[label] = {
            "rows": selected,
            "dates": sorted(present_dates),
            "events": len(selected),
            "per_day": len(selected) / 7,
            "arrivals": sum(row["direction"] == "arrival" for row in selected),
            "departures": sum(row["direction"] == "departure" for row in selected),
            "known": len(known),
            "unknown": len(selected) - len(known),
            "canceled": len(canceled),
            "cancel_rate": len(canceled) / len(known) if known else 0,
        }

    return date_counts, period_rows


def make_figures(date_counts, period_rows, calendar_summary):
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 12,
            "axes.labelsize": 9,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )
    paths = {}

    all_dates = sorted(date_counts)
    figure, axis = plt.subplots(figsize=(8.1, 4.3))
    axis.plot(
        all_dates,
        [date_counts[day]["departure"] for day in all_dates],
        color=BLUE,
        linewidth=1.7,
        label="Departures",
    )
    axis.plot(
        all_dates,
        [date_counts[day]["arrival"] for day in all_dates],
        color=TEAL,
        linewidth=1.7,
        label="Arrivals",
    )
    axis.axvspan(
        HOLIDAY_START,
        HOLIDAY_START + timedelta(days=7),
        color=ORANGE,
        alpha=0.13,
        label="Oct 1-7 holiday",
    )
    axis.set_title("Daily flight-event records at Shanghai Hongqiao")
    axis.set_ylabel("Records per local date")
    axis.set_xlabel("Scheduled local date")
    highest_direction_count = max(
        max(date_counts[day]["arrival"], date_counts[day]["departure"])
        for day in all_dates
    )
    axis.set_ylim(0, max(450, highest_direction_count * 1.15))
    axis.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    axis.grid(axis="y", alpha=0.24)
    axis.legend(frameon=False, ncol=3, loc="lower left")
    figure.autofmt_xdate(rotation=25)
    figure.tight_layout()
    paths["daily"] = FIGURE_DIR / "daily_flight_events.png"
    figure.savefig(paths["daily"], dpi=220, bbox_inches="tight")
    plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(8.1, 4.2))
    labels = [label for label, _, _ in PERIODS]
    period_colors = [LIGHT_BLUE, ORANGE, TEAL]
    bars = axes[0].bar(
        labels,
        [period_rows[label]["per_day"] for label in labels],
        color=period_colors,
        edgecolor="white",
    )
    axes[0].set_title("Mean event records per day")
    axes[0].set_ylabel("Flight-event records / 7 days")
    axes[0].grid(axis="y", alpha=0.24)
    axes[0].bar_label(bars, fmt="%.1f", padding=3, fontsize=8)
    bars = axes[1].bar(
        labels,
        [period_rows[label]["cancel_rate"] * 100 for label in labels],
        color=period_colors,
        edgecolor="white",
    )
    axes[1].set_title("Canceled records among known statuses")
    axes[1].set_ylabel("Canceled records (%)")
    axes[1].grid(axis="y", alpha=0.24)
    axes[1].bar_label(bars, fmt="%.2f%%", padding=3, fontsize=8)
    for axis in axes:
        axis.tick_params(axis="x", labelrotation=15)
    figure.tight_layout()
    paths["periods"] = FIGURE_DIR / "period_comparison.png"
    figure.savefig(paths["periods"], dpi=220, bbox_inches="tight")
    plt.close(figure)

    holiday_rows = period_rows["National Day"]["rows"]
    routes = Counter(row["route"] for row in holiday_rows)
    top_routes = routes.most_common(10)
    figure, axis = plt.subplots(figsize=(8.1, 4.6))
    route_labels = [route for route, _ in reversed(top_routes)]
    route_values = [count for _, count in reversed(top_routes)]
    route_colors = [
        BLUE if route.startswith("SHA-") else TEAL for route in route_labels
    ]
    bars = axis.barh(route_labels, route_values, color=route_colors)
    axis.bar_label(bars, padding=3, fontsize=8)
    axis.set_title("Most frequently recorded directional routes, Oct 1-7")
    axis.set_xlabel("Flight-event records across seven dates")
    axis.grid(axis="x", alpha=0.24)
    axis.legend(
        handles=[
            plt.Rectangle((0, 0), 1, 1, color=BLUE, label="Departing SHA"),
            plt.Rectangle((0, 0), 1, 1, color=TEAL, label="Arriving at SHA"),
        ],
        frameon=False,
        loc="lower right",
    )
    figure.tight_layout()
    paths["routes"] = FIGURE_DIR / "holiday_top_routes.png"
    figure.savefig(paths["routes"], dpi=220, bbox_inches="tight")
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8.1, 4.2))
    colors_by_period = dict(zip(labels, (BLUE, ORANGE, TEAL)))
    for label in labels:
        counts = Counter(row["_hour"] for row in period_rows[label]["rows"])
        total = period_rows[label]["events"]
        hours = list(range(24))
        shares = [100 * counts[hour] / total for hour in hours]
        axis.plot(
            hours,
            shares,
            marker="o",
            markersize=3,
            linewidth=1.6,
            color=colors_by_period[label],
            label=label,
        )
    axis.set_title("Scheduled event records by local hour")
    axis.set_xlabel("Scheduled local hour")
    axis.set_ylabel("Share of period records (%)")
    axis.set_xticks(range(0, 24, 2))
    axis.grid(axis="y", alpha=0.24)
    axis.legend(frameon=False)
    figure.tight_layout()
    paths["hours"] = FIGURE_DIR / "hourly_schedule_profile.png"
    figure.savefig(paths["hours"], dpi=220, bbox_inches="tight")
    plt.close(figure)

    category_order = (
        "ordinary_weekday",
        "weekend",
        "public_holiday",
        "adjusted_workday",
    )
    category_labels = {
        "ordinary_weekday": "Ordinary weekday",
        "weekend": "Weekend",
        "public_holiday": "Public holiday",
        "adjusted_workday": "Adjusted workday",
    }
    category_colors = {
        "ordinary_weekday": BLUE,
        "weekend": TEAL,
        "public_holiday": ORANGE,
        "adjusted_workday": "#9A4D67",
    }
    figure, axis = plt.subplots(figsize=(8.1, 4.4))
    for position, category in enumerate(category_order):
        days = calendar_summary.get(category, [])
        if not days:
            continue
        jitter = [
            (index - (len(days) - 1) / 2) * min(0.022, 0.34 / max(len(days) - 1, 1))
            for index in range(len(days))
        ]
        axis.scatter(
            [position + offset for offset in jitter],
            [item["events"] for item in days],
            color=category_colors[category],
            s=43 if category != "adjusted_workday" else 68,
            marker="D" if category == "adjusted_workday" else "o",
            edgecolors="white",
            linewidths=0.7,
            zorder=3,
        )
        if category == "adjusted_workday":
            item = days[0]
            axis.annotate(
                "{}: {}".format(item["date"].strftime("%b %-d"), item["events"]),
                (position, item["events"]),
                xytext=(8, 9),
                textcoords="offset points",
                fontsize=8,
                color=category_colors[category],
            )
    axis.set_title("Daily flight-event records by calendar day type")
    axis.set_ylabel("Flight-event records per date")
    axis.set_xticks(range(len(category_order)))
    axis.set_xticklabels(
        [
            "{}\n(n={})".format(
                category_labels[category],
                len(calendar_summary.get(category, [])),
            )
            for category in category_order
        ]
    )
    axis.set_ylim(bottom=0)
    axis.grid(axis="y", alpha=0.24)
    figure.tight_layout()
    paths["calendar"] = FIGURE_DIR / "calendar_day_type.png"
    figure.savefig(paths["calendar"], dpi=220, bbox_inches="tight")
    plt.close(figure)
    return paths, top_routes


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontName="Times-Bold",
            fontSize=24,
            leading=29,
            textColor=colors.HexColor(NAVY),
            alignment=TA_CENTER,
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            "Subtitle",
            parent=styles["Normal"],
            fontName="Times-Italic",
            fontSize=12,
            leading=17,
            textColor=colors.HexColor("#4C6478"),
            alignment=TA_CENTER,
            spaceAfter=9,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyAcademic",
            parent=styles["BodyText"],
            fontName="Times-Roman",
            fontSize=10.2,
            leading=14.3,
            alignment=TA_JUSTIFY,
            spaceAfter=7,
            allowWidows=0,
            allowOrphans=0,
        )
    )
    styles.add(
        ParagraphStyle(
            "Section",
            parent=styles["Heading1"],
            fontName="Times-Bold",
            fontSize=15,
            leading=19,
            textColor=colors.HexColor(NAVY),
            spaceBefore=11,
            spaceAfter=7,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "Subsection",
            parent=styles["Heading2"],
            fontName="Times-Bold",
            fontSize=11.5,
            leading=14,
            textColor=colors.HexColor("#285A7A"),
            spaceBefore=8,
            spaceAfter=5,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "Caption",
            parent=styles["BodyText"],
            fontName="Times-Italic",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#444444"),
            alignment=TA_LEFT,
            spaceBefore=3,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "Reference",
            parent=styles["BodyText"],
            fontName="Times-Roman",
            fontSize=9.4,
            leading=13,
            leftIndent=16,
            firstLineIndent=-16,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "Cover",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=11,
            leading=18,
            alignment=TA_CENTER,
            spaceAfter=7,
        )
    )
    return styles


def add_para(story, styles, text, style="BodyAcademic"):
    story.append(Paragraph(escape(text), styles[style]))


def add_section(story, styles, title):
    story.append(Paragraph(escape(title), styles["Section"]))


def add_figure(story, styles, path, caption):
    reader = ImageReader(str(path))
    width, height = reader.getSize()
    max_width = A4[0] - 48 * mm
    max_height = 91 * mm
    scale = min(max_width / width, max_height / height)
    story.append(
        Image(
            str(path),
            width=width * scale,
            height=height * scale,
            hAlign="CENTER",
        )
    )
    add_para(story, styles, caption, "Caption")


def add_results_table(story, styles, period_rows):
    body = [
        ["Seven-day window", "Flight-event\nrecords", "Records /\nday", "Arrivals", "Departures", "Canceled / known"],
    ]
    for label, _, _ in PERIODS:
        summary = period_rows[label]
        body.append(
            [
                label,
                "{:,}".format(summary["events"]),
                "{:.1f}".format(summary["per_day"]),
                "{:,}".format(summary["arrivals"]),
                "{:,}".format(summary["departures"]),
                "{:,} / {:,} ({:.2f}%)".format(
                    summary["canceled"],
                    summary["known"],
                    summary["cancel_rate"] * 100,
                ),
            ]
        )
    table = Table(body, colWidths=[29 * mm, 25 * mm, 21 * mm, 19 * mm, 22 * mm, 41 * mm], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(NAVY)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.4),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F8")]),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9D3DC")),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 3 * mm))
    add_para(
        story,
        styles,
        "Note. Status rates use known-status records as the denominator; blank and 'Unknown' statuses are excluded. Flight-event records include canceled records and are not passenger totals.",
        "Caption",
    )


def build_report(output_path, input_path):
    rows = read_records(input_path)
    date_counts, period_rows = summarize(rows)
    calendar_summary = summarize_calendar_days(rows)
    figures, top_routes = make_figures(date_counts, period_rows, calendar_summary)
    styles = make_styles()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    title = "Holiday Flight-Service Patterns at Shanghai Hongqiao Airport"
    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=24 * mm,
        leftMargin=24 * mm,
        topMargin=22 * mm,
        bottomMargin=21 * mm,
        title=title,
        author="",
        subject=(
            "Calendar-aware descriptive analysis of China's 2026 National Day "
            "flight-event patterns"
        ),
    )
    story = [
        Spacer(1, 35 * mm),
        Paragraph(escape(title), styles["ReportTitle"]),
        Paragraph(
            "A calendar-aware descriptive analysis of China's 2026 National Day period",
            styles["Subtitle"],
        ),
        Spacer(1, 6 * mm),
        Paragraph("Transportation Engineering Research Paper", styles["Cover"]),
        Spacer(1, 19 * mm),
    ]
    for line in (
        "Study period: September 22-October 22, 2026",
        "Focus period: October 1-7, 2026",
        "Author: [Add your name]",
        "Course: [Add course name and code]",
        "Submission date: [Add date]",
    ):
        add_para(story, styles, line, "Cover")
    story.extend(
        [
            Spacer(1, 12 * mm),
            Paragraph(
                escape(
                    "Scope note: This is an exploratory single-airport study of recorded flight events. "
                    "The file does not contain passenger counts, traveler motives, or measured emissions."
                ),
                styles["Caption"],
            ),
            PageBreak(),
        ]
    )

    add_section(story, styles, "Abstract")
    add_para(
        story,
        styles,
        "This study characterizes flight-event patterns at Shanghai Hongqiao International Airport (SHA) during China's National Day holiday, October 1-7, 2026, using {:,} records across {} local dates. It addresses a calendar-classification problem in short-window transport analysis: the adjacent seven-day periods share weekdays with the holiday week but contain different official day types, including Mid-Autumn public holidays before the study period and a Saturday adjusted workday after it. The National Day week contains {:,} records ({:.1f} per day), compared with {:.1f} and {:.1f} records per day in the preceding and following windows. The single adjusted workday, October 10, contains {:,} records; {:.2f}% of its known-status records are marked canceled. The holiday-week cancellation share is {:.2f}%, compared with {:.2f}% before and {:.2f}% after. The analysis contributes a calendar-aware descriptive baseline for airport service patterns, an explicit account of how make-up workdays affect comparison-window interpretation, and a data-boundary framework separating flight-event supply from passenger demand, validated performance, and emissions. Because the dataset contains no passenger, alternative-mode, or verified emissions measures, results are descriptive and do not establish traveler behavior or sustainability impacts.".format(
            len(rows),
            len(date_counts),
            period_rows["National Day"]["events"],
            period_rows["National Day"]["per_day"],
            period_rows["Pre-holiday"]["per_day"],
            period_rows["Post-holiday"]["per_day"],
            calendar_summary["adjusted_workday"][0]["events"],
            100
            * calendar_summary["adjusted_workday"][0]["canceled"]
            / calendar_summary["adjusted_workday"][0]["known"],
            period_rows["National Day"]["cancel_rate"] * 100,
            period_rows["Pre-holiday"]["cancel_rate"] * 100,
            period_rows["Post-holiday"]["cancel_rate"] * 100,
        ),
    )
    add_para(
        story,
        styles,
        "Keywords: air transportation; holiday travel; adjusted workday; flight-service patterns; calendar effects; Shanghai Hongqiao",
        "Caption",
    )

    add_section(story, styles, "1. Introduction and problem statement")
    add_para(
        story,
        styles,
        "Holiday periods are planning-relevant because travel activity and transport-service provision may vary with the timing of public holidays, work schedules, and the surrounding calendar. In China, an extended public holiday can be paired with officially designated make-up workdays on weekends. The calendar day of week is therefore not, on its own, a sufficient descriptor of whether a date is a working day or a holiday. Treating a make-up workday as an ordinary Saturday can confound comparisons of flight-service activity and lead to misleading conclusions about holiday-related change.",
    )
    add_para(
        story,
        styles,
        "A second problem is measurement. Airport flight-event records describe scheduled services and status labels, but they are not passenger counts and do not directly measure demand, airport capacity, congestion, or environmental impact. Transport planning and sustainability assessments require outcomes and system boundaries matched to the question (IPCC, 2022; ITF, 2023). If event records are interpreted as passenger behavior, or schedule counts as realized throughput, the analysis exceeds what the data can support.",
    )
    add_para(
        story,
        styles,
        "The study addresses these problems through a calendar-aware descriptive analysis of Shanghai Hongqiao Airport (SHA). It compares the October 1-7, 2026 National Day period with weekday-aligned adjacent windows, examines scheduled-hour and directional-route profiles, and reports status-based cancellation proportions. Calendar classifications from the supplied dataset are interpreted against the official 2026 holiday schedule (General Office of the State Council, 2025). The term 'flight behavior' is operationalized as flight-service patterns; the analysis does not infer individual traveler choices.",
    )

    add_section(story, styles, "2. Objectives, research questions, and contribution")
    add_para(
        story,
        styles,
        "The objective is to describe how recorded airport service activity is distributed around the National Day holiday and to establish whether the holiday calendar, including an adjusted workday, changes the interpretation of adjacent-period comparisons.",
    )
    for question in (
        "RQ1. How does the number of recorded arrival and departure flight events per day during October 1-7 compare with the adjacent seven-day periods?",
        "RQ2. Do the distribution of scheduled flight times and the most frequently recorded directional routes differ during the holiday week?",
        "RQ3. How do recorded cancellation proportions differ across the pre-holiday, holiday, and post-holiday windows?",
        "RQ4. What flight-event pattern is recorded on the adjusted workday immediately after the National Day holiday, and how does it compare descriptively with other calendar-day types in the sample?",
    ):
        add_para(story, styles, question)
    add_para(
        story,
        styles,
        "The questions are descriptive, not causal. The study makes three contributions. First, it provides a reproducible, single-airport baseline of daily event volumes, scheduled-hour shares, route frequencies, and status-based cancellations for a Chinese National Day period. Second, it explicitly incorporates official calendar day type, showing why weekday-aligned windows are not necessarily comparable when they include public holidays or make-up workdays. Third, it sets clear interpretive boundaries between service-event records and unobserved passenger demand, validated operational performance, and sustainability outcomes. The contribution is a transparent case analysis and measurement framework, not a causal estimate or a general model of Chinese holiday travel.",
    )

    add_section(story, styles, "3. Study context, data, and methods")
    add_para(
        story,
        styles,
        "The analysis uses the supplied sha_master.csv file. It contains {:,} unique event_id records and covers {} local dates, from {} through {}. Each record describes an arrival or departure event at SHA, with fields for local date and hour, directional route, displayed status, and calendar classification. The seven-day study windows are September 24-30 (pre-National Day), October 1-7 (National Day), and October 8-14 (post-National Day). They are equal in length and begin on the same weekday, but their official calendar types differ: September 25-27 are Mid-Autumn public holidays, October 1-7 are National Day public holidays, and October 10 is designated as an adjusted workday in the official 2026 holiday schedule (General Office of the State Council, 2025). The schedule also designates September 20 as a workday, but that date falls outside the supplied dataset. Thus weekday alignment does not make these periods fully calendar-equivalent.".format(
            len(rows),
            len(date_counts),
            min(date_counts).isoformat(),
            max(date_counts).isoformat(),
        ),
    )
    add_para(
        story,
        styles,
        "The primary volume measure is the count of event records per local date, split by arrival and departure. For the comparison table, the daily mean is total event records divided by the seven dates. A canceled event remains in the event-record volume because it was part of the listed service, but it is not an operated flight. Route frequencies count directional event records. The hourly plot compares each window's share of all its records by scheduled local hour, avoiding direct comparisons of unequal totals. The calendar-type plot groups daily totals by the dataset's calendar_day_type field and shows each date separately. The adjusted-workday category contains one date only, so it is presented as a single-case observation rather than a general estimate.",
    )
    add_para(
        story,
        styles,
        "Cancellation proportion is the number of records whose status is 'Canceled' divided by records with a nonblank status other than 'Unknown'. Rows with blank or unknown status are excluded from this denominator and reported as missing status. No inferential statistical test is used: there are only three short, adjacent windows and no control for weather, capacity, schedule changes, or other concurrent conditions. The analysis is reproducible from the included Python script.",
    )
    add_para(
        story,
        styles,
        "Ethics and privacy: the report aggregates operational event data and does not reproduce flight identifiers or attempt to infer personal travel histories. Any further work using passenger-level or booking data would require appropriate access controls and ethical review.",
    )

    add_section(story, styles, "4. Results")
    add_para(
        story,
        styles,
        "Across the seven holiday dates, the file contains {:,} flight-event records: {:,} arrivals and {:,} departures. The mean is {:.1f} records per day, a {:.1f}% difference from the pre-National Day daily mean and a {:.1f}% difference from the post-National Day mean. These values are similar to the preceding week and higher than the following week in this sample; they should not be treated as passenger demand or airport throughput.".format(
            period_rows["National Day"]["events"],
            period_rows["National Day"]["arrivals"],
            period_rows["National Day"]["departures"],
            period_rows["National Day"]["per_day"],
            100
            * (
                period_rows["National Day"]["per_day"]
                / period_rows["Pre-holiday"]["per_day"]
                - 1
            ),
            100
            * (
                period_rows["National Day"]["per_day"]
                / period_rows["Post-holiday"]["per_day"]
                - 1
            ),
        ),
    )
    add_figure(
        story,
        styles,
        figures["daily"],
        "Figure 1. Daily arrival and departure event records in the full dataset. Shading marks October 1-7. Records include events displayed as canceled and therefore are not counts of completed flights.",
    )
    add_para(
        story,
        styles,
        "Figure 1 places the holiday week within the full 31-date observation period. Daily counts vary, while arrivals and departures remain close in number. The display supports inspection of short-run variation but does not identify whether it reflects holiday travel, airline scheduling, data capture, or operational disruptions.",
    )
    add_results_table(story, styles, period_rows)
    add_figure(
        story,
        styles,
        figures["periods"],
        "Figure 2. Equal-length, weekday-aligned windows. The right panel uses known-status records only; the count of known records differs by period. Calendar types also differ across windows.",
    )
    add_para(
        story,
        styles,
        "The holiday period has {:,} canceled records among {:,} known-status records ({:.2f}%). The corresponding proportions are {:,} of {:,} ({:.2f}%) before the holiday and {:,} of {:,} ({:.2f}%) afterward. The direction of this descriptive difference should be interpreted cautiously: {:,} post-holiday records have blank or unknown status, compared with {:,} before and {:,} during the holiday, and the data do not explain the reasons for cancellation.".format(
            period_rows["National Day"]["canceled"],
            period_rows["National Day"]["known"],
            period_rows["National Day"]["cancel_rate"] * 100,
            period_rows["Pre-holiday"]["canceled"],
            period_rows["Pre-holiday"]["known"],
            period_rows["Pre-holiday"]["cancel_rate"] * 100,
            period_rows["Post-holiday"]["canceled"],
            period_rows["Post-holiday"]["known"],
            period_rows["Post-holiday"]["cancel_rate"] * 100,
            period_rows["Post-holiday"]["unknown"],
            period_rows["Pre-holiday"]["unknown"],
            period_rows["National Day"]["unknown"],
        ),
    )
    add_figure(
        story,
        styles,
        figures["hours"],
        "Figure 3. Each line shows the percentage distribution of event records by scheduled local hour within a seven-day window. The profile describes schedule timing, not passenger arrival times or congestion.",
    )
    add_para(
        story,
        styles,
        "The hourly profiles make it possible to assess whether records are concentrated in different parts of the day, while normalizing for each window's total. This is a schedule-composition measure. No conclusion about queues or congestion follows without airport capacity, runway, taxi, and actual movement data.",
    )
    add_figure(
        story,
        styles,
        figures["routes"],
        "Figure 4. Ten most frequent directional routes in the October 1-7 records. SHA-origin routes are departures; routes ending in SHA are arrivals. A record count is not a passenger count.",
    )
    add_para(
        story,
        styles,
        "The leading observed connections are Shenzhen-SHA and SHA-Shenzhen, followed by Guangzhou-SHA and SHA-Guangzhou, and the Beijing-SHA and SHA-Beijing pair. Directional labels are kept separate because an arrival and a departure on the same city pair are different service events. The chart describes event frequency in this airport file, not the number of unique travelers or the full size of each destination market.",
    )
    add_figure(
        story,
        styles,
        figures["calendar"],
        "Figure 5. One point per observed local date, grouped by the dataset's calendar-day classification. n gives the number of dates in each category. The adjusted-workday category has one observation only (October 10).",
    )
    adjusted_day = calendar_summary["adjusted_workday"][0]
    add_para(
        story,
        styles,
        "The dataset marks Saturday, October 10 as an adjusted workday following the seven-day National Day holiday, consistent with the official 2026 holiday arrangement. That date has {:,} flight-event records ({:,} arrivals and {:,} departures); {:,} of {:,} known-status records are labeled canceled ({:.2f}%). This observed count is below the sample's ordinary-weekend daily mean ({:.1f} across {} dates), but only one adjusted workday is present, so the contrast cannot establish a general adjusted-workday effect. Importantly, the post-National Day seven-day comparison includes October 10; its mean and cancellation proportion therefore combine a make-up workday with ordinary weekdays and a Sunday.".format(
            adjusted_day["events"],
            sum(row["direction"] == "arrival" for row in rows if row["_date"] == adjusted_day["date"]),
            sum(row["direction"] == "departure" for row in rows if row["_date"] == adjusted_day["date"]),
            adjusted_day["canceled"],
            adjusted_day["known"],
            100 * adjusted_day["canceled"] / adjusted_day["known"],
            sum(item["events"] for item in calendar_summary["weekend"])
            / len(calendar_summary["weekend"]),
            len(calendar_summary["weekend"]),
        ),
    )
    add_para(
        story,
        styles,
        "The preceding comparison week also includes September 25-27, classified in the source calendar as the Mid-Autumn public holiday. Thus, the earlier period is not a fully ordinary baseline either. The three seven-day windows remain useful descriptive context, but differences between them may reflect the mix of official holidays, adjusted workdays, and ordinary days as well as other factors.",
    )

    add_section(story, styles, "5. Discussion and planning implications")
    add_para(
        story,
        styles,
        "The data support a modest finding: recorded flight-event volume per day during October 1-7 is close to the immediately preceding weekday-aligned week, while the following week has fewer records per day. Cancellations are less frequent as a share of known statuses during the holiday week than in either neighboring window. These are observed associations in one short sample, not evidence that the holiday improved airport performance or that a particular policy caused the differences.",
    )
    add_para(
        story,
        styles,
        "The Chinese make-up workday arrangement is a meaningful part of the travel-calendar context. October 10 falls on a Saturday but is designated an adjusted workday, rather than an ordinary weekend. Since the post-holiday comparison window includes this date and the dataset has no other adjusted workday, a calendar-aware analysis should report it separately and avoid generalizing from it. Similarly, September 25-27 are Mid-Autumn public holidays, which limits the interpretation of the preceding period as a non-holiday baseline.",
    )
    add_para(
        story,
        styles,
        "For airport operations and transportation planning, the results identify the value of calendar-aware monitoring: daily event counts, scheduled-hour shares, routes, cancellations, and the official work/rest calendar should be considered together. However, this file does not establish passenger volumes, terminal or runway capacity, or queues, and the reported patterns cannot be interpreted as realized airport throughput. Future operational analysis should connect scheduled services to verified movement times, capacity and disruption data.",
    )
    add_para(
        story,
        styles,
        "A follow-up study could link verified flight movements to aircraft type and route distance, collect passenger volumes or defensible load-factor estimates, and compare available rail and air itineraries for selected corridors. Adding airport-rail access time, fares, and accessibility measures would connect the analysis to urban integration and social equity. Emissions could then be estimated with an explicitly documented method and uncertainty range. A longer multi-year sample and matched comparison dates would help separate holiday timing from weekday, season, weather, and disruption effects.",
    )

    add_section(story, styles, "6. Limitations")
    for limitation in (
        "The unit is a flight-event record, not a passenger or trip. Multiple records do not identify unique travelers, trip purpose, or mode choice.",
        "The analysis covers one airport and 31 dates, with only one National Day period. Adjacent weeks are useful context, not a causal control group.",
        "Only one adjusted workday (October 10) appears in the sample, so its flight-event count and status profile are a single-date case, not a representative estimate. The comparison windows also include Mid-Autumn and National Day public holidays.",
        "Status labels may be incomplete or time-sensitive. The post-holiday comparison has more blank or unknown statuses, changing the observed cancellation denominator.",
        "The dataset does not provide measured airport capacity, weather, air traffic control restrictions, aircraft rotations, passenger volumes, fares, mode alternatives, emissions, or traveler characteristics.",
        "Timing semantics in the wider dataset are marked unverified. This report therefore avoids interpreting timestamp differences as validated delays.",
        "The capture process and completeness of the source file cannot be independently verified from the supplied CSV alone.",
    ):
        add_para(story, styles, limitation)

    add_section(story, styles, "7. Conclusions")
    add_para(
        story,
        styles,
        "This study documents flight-event patterns around China's October 1-7, 2026 National Day holiday at Shanghai Hongqiao Airport. In weekday-aligned seven-day comparisons, the holiday period averages {:.1f} event records per day, compared with {:.1f} in the preceding window and {:.1f} in the following window. The observed known-status cancellation share is {:.2f}% during the holiday, versus {:.2f}% before and {:.2f}% after. The following window includes one adjusted workday, October 10, while the preceding window includes three Mid-Autumn public holidays; these calendar differences constrain period-to-period interpretation. Route, hourly, and calendar-type profiles add descriptive detail about service patterns. These results are useful for transportation planning, but are not estimates of passenger demand, causation, congestion, emissions, or traveler choice.".format(
            period_rows["National Day"]["per_day"],
            period_rows["Pre-holiday"]["per_day"],
            period_rows["Post-holiday"]["per_day"],
            period_rows["National Day"]["cancel_rate"] * 100,
            period_rows["Pre-holiday"]["cancel_rate"] * 100,
            period_rows["Post-holiday"]["cancel_rate"] * 100,
        ),
    )
    add_para(
        story,
        styles,
        "The principal contribution is a reproducible descriptive baseline paired with a calendar-aware interpretation of comparison windows. Broader assessment of sustainable aviation and surface-mode alternatives requires linked passenger, alternative-mode, equity, and emissions information. Future research should extend the observation period across multiple years, include comparable holiday and non-holiday dates, and link verified operational, passenger, and environmental measures.",
    )

    add_section(story, styles, "References")
    references = (
        "Intergovernmental Panel on Climate Change. (2022). Climate Change 2022: Mitigation of Climate Change. Contribution of Working Group III to the Sixth Assessment Report of the Intergovernmental Panel on Climate Change. Cambridge University Press. https://doi.org/10.1017/9781009157926",
        "International Transport Forum. (2023). ITF Transport Outlook 2023. OECD Publishing, Paris. https://doi.org/10.1787/b6cc9ad5-en",
        "General Office of the State Council of the People's Republic of China. (2025, November 4). Notice on the arrangement of some public holidays in 2026 (Guo Ban Fa Ming Dian [2025] No. 7). October 1-7 are the National Day holiday; September 25-27 are the Mid-Autumn Festival holiday; September 20 and October 10 are adjusted workdays. https://www.gov.cn/zhengce/content/202511/content_7047090.htm",
        "User-supplied dataset. (2026). sha_master.csv [CSV file; flight-event records associated with Shanghai Hongqiao Airport].",
    )
    for reference in references:
        add_para(story, styles, reference, "Reference")
    add_para(
        story,
        styles,
        "Reproducibility: run `python scripts/generate_national_day_report.py` from the SHA-flight-data project directory. The script reads sha_master.csv and regenerates this PDF and its five figures.",
        "Caption",
    )

    def page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Roman", 8.5)
        canvas.setFillColor(colors.HexColor("#687785"))
        canvas.drawCentredString(A4[0] / 2, 11 * mm, str(doc.page))
        if doc.page > 1:
            canvas.setFont("Times-Italic", 8)
            canvas.drawString(24 * mm, A4[1] - 13 * mm, "National Day flight activity at SHA")
        canvas.restoreState()

    document.build(story, onFirstPage=page_number, onLaterPages=page_number)
    return len(rows), len(date_counts), len(story)


def main():
    parser = argparse.ArgumentParser(
        description="Generate a publication-style National Day flight research PDF."
    )
    parser.add_argument("--input", type=Path, default=DATA, help="Input flight CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output PDF.")
    args = parser.parse_args()
    rows, dates, _ = build_report(args.output, args.input)
    print("Wrote {} from {:,} records across {} dates.".format(args.output, rows, dates))


if __name__ == "__main__":
    main()
