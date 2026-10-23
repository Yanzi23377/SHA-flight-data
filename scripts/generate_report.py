import argparse
import csv
import re
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research_report.md"
DATA = ROOT / "sha_master.csv"
DEFAULT_OUTPUT = ROOT / "research_report.pdf"
FIGURE_DIR = ROOT / "plots" / "report"


def word_count(text: str) -> int:
    text = re.sub(r"\[\[FIGURE:[^\]]+\]\]", "", text)
    return len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", text))


def inline_markup(text: str) -> str:
    formatted = escape(text)
    formatted = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', formatted)
    formatted = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", formatted)
    formatted = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", formatted)
    formatted = re.sub(
        r"(https://doi\.org/[^\s]+)",
        r'<link href="\1" color="#1a5a85">\1</link>',
        formatted,
    )
    return formatted


def make_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontName="Times-Bold",
            fontSize=23,
            leading=29,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#17324d"),
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            "Cover",
            parent=styles["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            leading=19,
            alignment=TA_CENTER,
            spaceAfter=9,
        )
    )
    styles.add(
        ParagraphStyle(
            "BodyAcademic",
            parent=styles["BodyText"],
            fontName="Times-Roman",
            fontSize=10.5,
            leading=15,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
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
            textColor=colors.HexColor("#17324d"),
            spaceBefore=13,
            spaceAfter=9,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "Subsection",
            parent=styles["Heading2"],
            fontName="Times-Bold",
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#285a7a"),
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            "Reference",
            parent=styles["BodyAcademic"],
            alignment=TA_LEFT,
            leftIndent=16,
            firstLineIndent=-16,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "CoverNote",
            parent=styles["Cover"],
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#555555"),
        )
    )
    return styles


def add_paragraphs(
    story,
    lines,
    styles,
    reference_mode=False,
    figures=None,
):
    paragraph_lines = []

    def flush_paragraph():
        if paragraph_lines:
            text = " ".join(line.strip() for line in paragraph_lines)
            style = styles["Reference"] if reference_mode else styles["BodyAcademic"]
            story.append(Paragraph(inline_markup(text), style))
            paragraph_lines.clear()

    for line in lines:
        if not line.strip():
            flush_paragraph()
        elif line.startswith("[[FIGURE:") and line.endswith("]]"):
            flush_paragraph()
            figure_key = line[len("[[FIGURE:") : -2]
            if figures is None or figure_key not in figures:
                raise ValueError("Unknown report figure marker: {}".format(figure_key))
            path, caption = figures[figure_key]
            append_figure(story, styles, path, caption)
        elif line.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[4:]), styles["Subsection"]))
        elif line.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[3:]), styles["Section"]))
        elif line.startswith("# "):
            flush_paragraph()
        elif line.startswith("- "):
            flush_paragraph()
            story.append(
                Paragraph(
                    "&bull;&nbsp;&nbsp;" + inline_markup(line[2:]),
                    styles["BodyAcademic"],
                )
            )
        else:
            paragraph_lines.append(line)
    flush_paragraph()


def prepare_departures():
    with DATA.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))

    departures = []
    for row in rows:
        if row["direction"] != "departure":
            continue
        status = row["status_display"].strip().casefold()
        if status in ("canceled", "unknown", ""):
            continue
        if not row["scheduled_departure_utc"] or not row["actual_departure_utc"]:
            continue
        scheduled = datetime.fromisoformat(
            row["scheduled_departure_utc"].replace("Z", "+00:00")
        )
        actual = datetime.fromisoformat(
            row["actual_departure_utc"].replace("Z", "+00:00")
        )
        row["deviation_minutes"] = (
            actual - scheduled
        ).total_seconds() / 60
        row["hour"] = int(row["local_hour"])
        departures.append(row)
    return departures


def percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def create_report_figures():
    departures = prepare_departures()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure_paths = []

    deviations = [row["deviation_minutes"] for row in departures]
    clipped_count = sum(value > 120 for value in deviations)
    figure, axes = plt.subplots(figsize=(8, 4.5))
    axes.hist(deviations, bins=52, range=(-10, 120), color="#2878B5", edgecolor="white")
    axes.axvline(statistics.median(deviations), color="#E07A32", linewidth=2, label="Median")
    axes.axvline(percentile(deviations, 0.95), color="#5A9E6F", linewidth=2, label="95th percentile")
    axes.set(
        title="Distribution of recorded departure-time differences",
        xlabel="Actual minus scheduled timestamp (minutes; positive = later)",
        ylabel="Departure records",
    )
    axes.text(
        0.99,
        0.95,
        "x-axis shown to 120 min\n{} records beyond range; maximum {:.1f} min".format(
            clipped_count, max(deviations)
        ),
        transform=axes.transAxes,
        ha="right",
        va="top",
        fontsize=8,
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"},
    )
    axes.legend(frameon=False)
    axes.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    path = FIGURE_DIR / "departure_difference_distribution.png"
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    figure_paths.append(path)

    hourly = defaultdict(list)
    for row in departures:
        hourly[row["hour"]].append(row["deviation_minutes"])
    hours = sorted(hourly)
    medians = [statistics.median(hourly[hour]) for hour in hours]
    p90s = [percentile(hourly[hour], 0.90) for hour in hours]
    counts = [len(hourly[hour]) for hour in hours]

    figure, axis = plt.subplots(figsize=(8, 4.5))
    count_axis = axis.twinx()
    count_axis.bar(hours, counts, color="#d9e5ee", width=0.75, label="Records")
    count_axis.set_ylabel("Eligible departure records")
    count_axis.set_zorder(0)
    axis.set_zorder(1)
    axis.patch.set_alpha(0)
    axis.plot(hours, medians, marker="o", color="#2878B5", label="Median")
    axis.plot(hours, p90s, marker="s", color="#E07A32", label="90th percentile")
    axis.axhline(0, color="gray", linewidth=1, linestyle="--")
    axis.set(
        title="Recorded departure-time difference by scheduled hour",
        xlabel="Scheduled local hour at SHA",
        ylabel="Actual minus scheduled (minutes)",
    )
    axis.set_xticks(hours)
    axis.grid(axis="y", alpha=0.25)
    lines, labels = axis.get_legend_handles_labels()
    count_lines, count_labels = count_axis.get_legend_handles_labels()
    axis.legend(lines + count_lines, labels + count_labels, frameon=False, loc="upper left")
    figure.tight_layout()
    path = FIGURE_DIR / "departure_difference_by_hour.png"
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    figure_paths.append(path)

    matched_groups = defaultdict(lambda: {"morning": [], "evening": []})
    for row in departures:
        if 6 <= row["hour"] < 12:
            window = "morning"
        elif 17 <= row["hour"] < 23:
            window = "evening"
        else:
            continue
        matched_groups[(row["route"], row["weekday"])][window].append(
            row["deviation_minutes"]
        )
    differences = [
        statistics.mean(group["evening"]) - statistics.mean(group["morning"])
        for group in matched_groups.values()
        if len(group["morning"]) >= 5 and len(group["evening"]) >= 5
    ]
    figure, axes = plt.subplots(figsize=(8, 4.5))
    axes.hist(differences, bins=25, color="#5A9E6F", edgecolor="white")
    axes.axvline(0, color="black", linewidth=1, linestyle="--", label="No difference")
    axes.axvline(
        statistics.mean(differences),
        color="#2878B5",
        linewidth=2,
        label="Mean matched difference",
    )
    axes.set(
        title="Matched evening-minus-morning differences",
        xlabel="Difference in mean timestamp gap (minutes)",
        ylabel="Route-weekday groups",
    )
    axes.legend(frameon=False)
    axes.grid(axis="y", alpha=0.25)
    figure.tight_layout()
    path = FIGURE_DIR / "matched_morning_evening_differences.png"
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    figure_paths.append(path)

    return figure_paths


def append_figure(story, styles, path, caption):
    from reportlab.lib.utils import ImageReader

    available_width = A4[0] - 48 * mm
    available_height = 105 * mm
    image_width, image_height = ImageReader(str(path)).getSize()
    scale = min(
        available_width / image_width,
        available_height / image_height,
    )
    story.append(
        Image(
            str(path),
            width=image_width * scale,
            height=image_height * scale,
            hAlign="CENTER",
        )
    )
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(inline_markup(caption), styles["Reference"]))
    story.append(Spacer(1, 5 * mm))


def build_report(output_path: Path) -> int:
    source_text = SOURCE.read_text(encoding="utf-8")
    lines = source_text.splitlines()
    introduction_index = next(
        index for index, line in enumerate(lines) if line.startswith("## 1. Introduction")
    )
    references_index = next(
        index for index, line in enumerate(lines) if line == "## References"
    )
    title = next(line[2:].strip() for line in lines if line.startswith("# "))
    report_words = word_count("\n".join(lines[introduction_index:references_index]))
    discussion_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("## 5. Discussion and conclusions")
    )
    styles = make_styles()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=24 * mm,
        leftMargin=24 * mm,
        topMargin=23 * mm,
        bottomMargin=20 * mm,
        title=title,
        author="",
        subject="Exploratory analysis of SHA departure-time differences",
    )
    story = [
        Spacer(1, 42 * mm),
        Paragraph(inline_markup(title), styles["ReportTitle"]),
        Paragraph(
            "Recorded scheduled-to-actual departure-time differences by "
            "scheduled hour, route and weekday at Shanghai Hongqiao Airport",
            styles["Cover"],
        ),
        Spacer(1, 20 * mm),
    ]

    cover_lines = lines[
        next(index for index, line in enumerate(lines) if line == "## Title page") + 1 :
        introduction_index
    ]
    for line in cover_lines:
        if line.startswith("**") and line.endswith("**"):
            story.append(
                Paragraph(inline_markup(line[2:-2]), styles["Cover"])
            )
        elif line.strip():
            story.append(
                Paragraph(inline_markup(line.replace("  ", " ")), styles["Cover"])
            )
        else:
            story.append(Spacer(1, 4 * mm))
    story.append(
        Paragraph(
            "Main text word count (title page and references excluded): "
            + str(report_words),
            styles["CoverNote"],
        )
    )
    story.append(PageBreak())

    figure_paths = create_report_figures()
    report_figures = {
        "distribution": (
            figure_paths[0],
            "Figure 1. Distribution of recorded departure-time differences. The horizontal axis is limited to -10 to 120 minutes for readability; the annotation reports observations beyond this range and the observed maximum.",
        ),
        "hourly": (
            figure_paths[1],
            "Figure 2. Median and 90th-percentile recorded timestamp differences by scheduled local hour. Background bars show eligible record counts, which describe the observed schedule sample and are not a direct congestion measure.",
        ),
        "matched": (
            figure_paths[2],
            "Figure 3. Distribution of evening-minus-morning mean differences across route-weekday groups with at least five records in each window. Positive values indicate a higher evening mean; the dashed line marks zero.",
        ),
    }
    add_paragraphs(
        story,
        lines[introduction_index:discussion_index],
        styles,
        figures=report_figures,
    )
    add_paragraphs(story, lines[discussion_index:references_index], styles)
    add_paragraphs(story, lines[references_index:], styles, reference_mode=True)

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Times-Roman", 9)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawCentredString(A4[0] / 2, 11 * mm, str(doc.page))
        canvas.restoreState()

    document.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return report_words


def main():
    parser = argparse.ArgumentParser(
        description="Build the PDF report from research_report.md."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="PDF output path (default: research_report.pdf).",
    )
    args = parser.parse_args()
    count = build_report(args.output)
    print("Wrote {} (main text: {} words).".format(args.output, count))


if __name__ == "__main__":
    main()
