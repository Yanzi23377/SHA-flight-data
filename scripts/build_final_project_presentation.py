"""Build a presentation from the final report's results and figures."""

import json
import struct
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "final_project_word"
FIG = OUT / "figures"
RESULTS = OUT / "sha_national_day_final_results.json"
PRESENTATION = OUT / "Holiday_Flight_Disruption_Patterns.pptx"

NAVY = "17324D"
BLUE = "2878B5"
TEAL = "5A9E8F"
ORANGE = "E07A32"
RED = "BE4B48"
MUTED = "58697A"
PALE = "EDF3F8"
WHITE = "FFFFFF"
BG = "FAFCFE"


def color(value):
    return RGBColor.from_string(value)


def add_text(slide, value, x, y, width, height, size=20, fill=NAVY,
             bold=False, align=PP_ALIGN.LEFT):
    shape = slide.shapes.add_textbox(
        Inches(x), Inches(y), Inches(width), Inches(height)
    )
    frame = shape.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = Inches(0.02)
    frame.margin_top = frame.margin_bottom = 0
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    for index, line in enumerate(value.split("\n")):
        paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
        paragraph.text = line
        paragraph.alignment = align
        paragraph.space_after = Pt(4)
        paragraph.font.name = "Aptos"
        paragraph.font.size = Pt(size)
        paragraph.font.bold = bold
        paragraph.font.color.rgb = color(fill)
    return shape


def add_rect(slide, x, y, width, height, fill, rounded=False):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(width), Inches(height),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color(fill)
    shape.line.fill.background()
    if rounded:
        shape.adjustments[0] = 0.08
    return shape


def add_header(slide, section, title, page, subtitle=None):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color(BG)
    add_rect(slide, 0, 0, 13.333, 0.08, BLUE)
    add_text(slide, section.upper(), 0.55, 0.22, 12.2, 0.28, 12, BLUE, True)
    add_text(slide, title, 0.55, 0.59, 12.2, 0.62, 28, NAVY, True)
    if subtitle:
        add_text(slide, subtitle, 0.58, 1.22, 12.0, 0.38, 15, MUTED)
    add_rect(slide, 0.55, 7.00, 12.2, 0.012, "D9E3EC")
    add_text(
        slide,
        "SHA • 22 Sep–22 Oct 2026 • exploratory flight-event analysis",
        0.58, 7.08, 11.4, 0.22, 10, MUTED,
    )
    add_text(slide, str(page), 12.05, 7.07, 0.65, 0.24, 11, MUTED,
             align=PP_ALIGN.RIGHT)


def add_notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def add_card(slide, x, y, width, height, eyebrow, value, detail, accent=BLUE):
    add_rect(slide, x, y, width, height, PALE, rounded=True)
    add_text(slide, eyebrow.upper(), x + 0.22, y + 0.18, width - 0.44, 0.30,
             12, MUTED, True)
    add_text(slide, value, x + 0.22, y + 0.56, width - 0.44, 0.62,
             27, accent, True)
    add_text(slide, detail, x + 0.22, y + 1.23, width - 0.44,
             height - 1.38, 15, NAVY)


def image_dimensions(path):
    with path.open("rb") as image:
        image.seek(16)
        return struct.unpack(">II", image.read(8))


def add_image_fit(slide, path, x, y, max_width, max_height):
    width_px, height_px = image_dimensions(path)
    scale = min(max_width / width_px, max_height / height_px)
    width, height = width_px * scale, height_px * scale
    return slide.shapes.add_picture(
        str(path),
        Inches(x + (max_width - width) / 2),
        Inches(y + (max_height - height) / 2),
        width=Inches(width),
        height=Inches(height),
    )


def make_hourly_delay_graph(results):
    bands = results["hourly_gaps"]
    labels = [row["hour_band"].replace(" (", "\n(") for row in bands]
    values = [row["extreme_pct"] for row in bands]
    colors = [f"#{BLUE}", f"#{BLUE}", f"#{ORANGE}", f"#{MUTED}"]
    fig, ax = plt.subplots(figsize=(11.8, 4.8))
    bars = ax.bar(labels, values, color=colors, width=0.62)
    ax.set_ylabel("Departures delayed ≥60 min (%)")
    ax.set_title("Long-delay share by scheduled local departure hour")
    ax.yaxis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
    ax.set_ylim(0, max(values) * 1.28)
    ax.grid(axis="y", alpha=0.22)
    ax.set_axisbelow(True)
    for bar, row in zip(bars, bands):
        ax.annotate(
            f'{row["extreme_n"]}/{row["records"]}  •  {row["extreme_pct"]:.2f}%',
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 7), textcoords="offset points", ha="center",
            va="bottom", fontsize=10,
        )
    fig.tight_layout()
    path = FIG / "hourly_delay_bands.png"
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def build():
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    FIG.mkdir(exist_ok=True)
    hourly_graph = make_hourly_delay_graph(results)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333333), Inches(7.5)
    blank = prs.slide_layouts[6]

    periods = results["periods"]
    total = results["rows"]
    eligible = results["eligible_gap_records"]
    long_delays = results["extreme_gap_records"]

    # 1. Title
    slide = prs.slides.add_slide(blank)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color(NAVY)
    add_rect(slide, 0, 0, 0.16, 7.5, TEAL)
    add_text(slide, "SHA • RESEARCH PRESENTATION", 0.8, 0.72, 11.8, 0.35,
             14, "91C9BD", True)
    add_text(slide, "Flight patterns around\nChina’s 2026 National Day",
             0.8, 1.45, 11.8, 1.6, 34, WHITE, True)
    add_text(slide, "Volume, cancellations, long delays, and the adjusted workday",
             0.84, 3.25, 11.5, 0.55, 20, "DCE7F0")
    for x, label, value in (
        (0.85, "AIRPORT", "Shanghai Hongqiao (SHA)"),
        (4.72, "STUDY WINDOW", "22 Sep–22 Oct 2026"),
        (8.59, "FLIGHT-EVENT RECORDS", f"{total:,}"),
    ):
        add_rect(slide, x, 5.15, 3.5, 1.0, "254560", rounded=True)
        add_text(slide, label, x + 0.18, 5.29, 3.12, 0.22, 11, "B8C8D7", True)
        add_text(slide, value, x + 0.18, 5.58, 3.12, 0.4, 17, WHITE, True)
    add_text(slide, "Exploratory results from recorded flight-event data; not a causal study.",
             0.84, 6.62, 11.5, 0.32, 13, "DCE7F0")
    add_notes(slide, "Introduce the airport, study window, and exploratory scope. "
              "These are flight-event records, not passenger counts.")

    # 2. Research questions
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Study questions", "Three questions guide the analysis", 2)
    questions = [
        ("RQ1", "Flight volume & cancellations",
         "How did event volume and cancellation rates vary before, during, and after the holiday?",
         BLUE),
        ("RQ2", "Long-delay concentration",
         "Were departures delayed ≥60 minutes concentrated on particular dates or hours?",
         ORANGE),
        ("RQ3", "Adjusted workday",
         "How did 10 October compare with ordinary weekend dates in the observed records?",
         TEAL),
    ]
    for index, (tag, title, detail, accent) in enumerate(questions):
        y = 1.62 + index * 1.62
        add_rect(slide, 0.72, y, 11.85, 1.34, PALE, rounded=True)
        add_rect(slide, 0.93, y + 0.22, 0.78, 0.78, accent, rounded=True)
        add_text(slide, tag, 0.94, y + 0.24, 0.76, 0.72, 16, WHITE, True,
                 PP_ALIGN.CENTER)
        add_text(slide, title, 1.98, y + 0.14, 10.1, 0.42, 20, NAVY, True)
        add_text(slide, detail, 1.98, y + 0.62, 10.1, 0.55, 16, MUTED)
    add_text(slide, "Unit of analysis: a recorded arrival or departure event, not a passenger.",
             0.86, 6.58, 11.6, 0.28, 13, MUTED, True)
    add_notes(slide, "Read the three report questions. Explain that the unit is a flight-event "
              "record and that the adjusted-workday case is descriptive.")

    # 3. China holiday-calendar explanation
    slide = prs.slides.add_slide(blank)
    add_header(slide, "China's holiday calendar",
               "The full study window spans two calendar months", 3,
               "Study dates: 22 September–22 October 2026 • China can designate weekend make-up workdays.")
    weekdays = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
    cell_w, cell_h, gap_x, gap_y = 0.72, 0.46, 0.055, 0.065
    calendar_width = 7 * cell_w + 6 * gap_x
    calendar_y = 1.72
    for month, start_offset, days, x_start in (
        ("SEPTEMBER 2026", 1, 30, 0.72),
        ("OCTOBER 2026", 3, 31, 6.98),
    ):
        add_text(slide, month, x_start, calendar_y, calendar_width, 0.34,
                 17, NAVY, True, PP_ALIGN.CENTER)
        weekday_y = calendar_y + 0.42
        for column, weekday in enumerate(weekdays):
            x = x_start + column * (cell_w + gap_x)
            add_text(slide, weekday, x, weekday_y, cell_w, 0.22, 10,
                     MUTED, True, PP_ALIGN.CENTER)
        for day in range(1, days + 1):
            row, column = divmod(start_offset + day - 1, 7)
            x = x_start + column * (cell_w + gap_x)
            y = weekday_y + 0.29 + row * (cell_h + gap_y)
            if month.startswith("SEPTEMBER"):
                in_study_window = day >= 22
                is_public_holiday = False
                is_makeup_workday = day == 20
            else:
                in_study_window = day <= 22
                is_public_holiday = day <= 7
                is_makeup_workday = day == 10
            if is_public_holiday:
                fill, text_fill = BLUE, WHITE
            elif is_makeup_workday:
                fill, text_fill = ORANGE, WHITE
            elif in_study_window:
                fill, text_fill = "DCEAF5", NAVY
            else:
                fill, text_fill = "F1F4F7", "9AA8B5"
            label = f"{day}*" if month.startswith("SEPTEMBER") and day == 20 else str(day)
            add_rect(slide, x, y, cell_w, cell_h, fill, rounded=True)
            add_text(slide, label, x, y + 0.01, cell_w, cell_h - 0.02, 14,
                     text_fill, is_public_holiday or is_makeup_workday, PP_ALIGN.CENTER)

    legend_y = 5.67
    for x, fill, label, width in (
        (0.82, "DCEAF5", "Study window", 1.55),
        (3.25, BLUE, "Public holiday", 1.75),
        (5.95, ORANGE, "Make-up workday", 2.05),
        (9.10, "F1F4F7", "Outside window", 1.85),
    ):
        add_rect(slide, x, legend_y + 0.045, 0.22, 0.22, fill, rounded=True)
        add_text(slide, label, x + 0.31, legend_y, width, 0.32, 12, NAVY, True)
    add_text(slide, "A make-up workday is an officially designated working day on a weekend. "
             "Oct 10 is in the dataset; Sep 20* is outside it.",
             0.84, 6.13, 11.7, 0.36, 14, NAVY, True)
    add_text(slide, "Source: State Council General Office, 2026 holiday arrangement (2025 notice).",
             0.84, 6.78, 11.6, 0.18, 9, MUTED)
    add_notes(slide, "Explain that China’s official holiday schedule can designate "
              "weekend dates as make-up workdays. These are working days even though "
              "they fall on Saturday or Sunday. The two calendars show the complete "
              "September 22–October 22 study window. October 1–7 are National Day public "
              "holidays, and Saturday, October 10 is an adjusted workday within the "
              "dataset. Sunday, September 20 was also designated a workday; it is marked "
              "for calendar context but falls before the dataset begins. Do not treat it "
              "as a zero-flight observation. "
              "Source: General Office of the State Council of the People's Republic of "
              "China, 2025 notice on 2026 public-holiday arrangements: "
              "https://www.gov.cn/zhengce/content/202511/content_7047090.htm")

    # 4. Data and measures
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Data & method", "What the indicators measure", 4)
    add_card(slide, 0.7, 1.62, 3.82, 2.08, "Coverage", f"{total:,} records",
             "31 local dates at one airport\n22 September–22 October 2026", BLUE)
    add_card(slide, 4.76, 1.62, 3.82, 2.08, "Cancellation rate",
             "Cancelled ÷ known status",
             "Unknown or blank status is excluded from the denominator.", ORANGE)
    add_card(slide, 8.82, 1.62, 3.82, 2.08, "Departure delay",
             f"{eligible:,} eligible",
             "Known, non-cancelled departures with scheduled and actual times.", TEAL)
    add_rect(slide, 0.72, 4.08, 11.88, 1.76, "FFF4E8", rounded=True)
    add_text(slide, "Important measurement caveat", 0.98, 4.30, 11.2, 0.36,
             18, RED, True)
    add_text(
        slide,
        f"{long_delays:,} of {eligible:,} eligible departures ("
        f"{results['extreme_gap_pct']:.2f}%) had a recorded scheduled-to-actual "
        "departure gap ≥60 minutes. This is an analytical threshold, not a validated "
        "operational delay measure: timestamp semantics are unverified.",
        0.98, 4.76, 11.1, 0.8, 16, NAVY,
    )
    add_text(slide, "Event counts do not establish complete scheduled capacity or passenger demand.",
             0.86, 6.25, 11.5, 0.35, 13, MUTED, True)
    add_notes(slide, "Describe the distinct denominators. A delay record requires a known "
              "status, a non-cancelled departure, and both timestamps. The source's "
              "timestamp semantics are not verified.")

    # 4. Period comparison
    slide = prs.slides.add_slide(blank)
    add_header(slide, "RQ1 • Period comparison", "Cancellation rates differed more than volume", 5,
               "Seven dates per period; these windows are chronological, not controlled groups.")
    accents = [BLUE, TEAL, ORANGE]
    for index, (period, accent) in enumerate(zip(periods, accents)):
        x = 0.72 + index * 4.05
        add_rect(slide, x, 1.92, 3.78, 3.55, PALE, rounded=True)
        add_text(slide, period["label"].upper(), x + 0.22, 2.17, 3.34, 0.33,
                 13, accent, True)
        add_text(slide, f'{period["events"]:,}', x + 0.22, 2.68, 3.3, 0.65,
                 30, NAVY, True)
        add_text(slide, f'{period["per_day"]:.1f} events / day',
                 x + 0.24, 3.37, 3.25, 0.36, 16, MUTED)
        add_rect(slide, x + 0.22, 3.94, 3.34, 0.02, "D3DEE8")
        add_text(slide, f'{period["cancel_pct"]:.2f}%',
                 x + 0.22, 4.15, 3.25, 0.55, 25, accent, True)
        add_text(slide, f'{period["canceled"]} / {period["known"]} known-status records cancelled',
                 x + 0.24, 4.77, 3.2, 0.5, 13, NAVY)
    add_rect(slide, 0.76, 5.88, 11.78, 0.62, "E8F1F7", rounded=True)
    add_text(slide, "The pre-holiday window includes Mid-Autumn public holidays; "
             "the post-holiday window includes the 10 October adjusted workday.",
             0.98, 5.97, 11.35, 0.42, 14, NAVY)
    add_notes(slide, "Compare all three seven-day periods. The pre-holiday period includes "
              "Mid-Autumn holidays, and the post-holiday period includes an adjusted "
              "workday, so they are not calendar-neutral comparisons.")

    # 5. Daily chart from the report
    slide = prs.slides.add_slide(blank)
    add_header(slide, "RQ1 • Daily pattern", "Daily variation is hidden by period averages", 6)
    add_image_fit(slide, FIG / "daily_trends.png", 0.30, 1.38, 7.55, 5.45)
    add_text(slide, "Dates to notice", 8.05, 1.78, 4.5, 0.4, 18, NAVY, True)
    add_card(slide, 8.05, 2.30, 4.35, 1.72, "Highest cancellation rate",
             "29 Sep • 8.15%", "62 of 761 known-status records", RED)
    add_card(slide, 8.05, 4.18, 4.35, 1.72, "Post-holiday variation",
             "8 Oct • 5.46%", "42 of 769 known-status records", ORANGE)
    add_text(slide, "These peaks are one-date observations, not recurring risk estimates.",
             8.08, 6.05, 4.25, 0.6, 14, MUTED)
    add_notes(slide, "The figure plots daily event counts and known-status cancellation "
              "rates. The rate peaks at 8.15% on September 29, then varies sharply. "
              "A one-month series does not establish recurrence or cause.")

    # 6. Long-delay dates from the report
    slide = prs.slides.add_slide(blank)
    add_header(slide, "RQ2 • Date concentration", "Long-delay records cluster on a few dates", 7,
               "Long delay is defined here as a recorded departure gap ≥60 minutes.")
    add_image_fit(slide, FIG / "extreme_dates.png", 0.42, 1.78, 8.25, 4.9)
    add_text(slide, "Overall", 8.9, 2.06, 3.5, 0.35, 14, MUTED, True)
    add_text(slide, f"{long_delays:,} / {eligible:,}",
             8.9, 2.49, 3.55, 0.56, 27, NAVY, True)
    add_text(slide, f"{results['extreme_gap_pct']:.2f}% of eligible departures",
             8.92, 3.08, 3.4, 0.48, 15, MUTED)
    top = results["extreme_dates"][0]
    add_rect(slide, 8.86, 3.84, 3.82, 1.52, PALE, rounded=True)
    add_text(slide, "Highest date-level share", 9.08, 4.03, 3.4, 0.3,
             12, MUTED, True)
    add_text(slide, f'{top["date"]}: {top["extreme_n"]}/{top["records"]}',
             9.08, 4.39, 3.35, 0.36, 17, RED, True)
    add_text(slide, f'{top["extreme_pct"]:.2f}% met threshold',
             9.08, 4.82, 3.35, 0.3, 14, NAVY)
    add_text(slide, "Exploratory timestamp gaps; not verified operational delays.",
             8.9, 5.8, 3.75, 0.62, 13, MUTED)
    add_notes(slide, "Across the full eligible sample, 514 of 11,560 records meet the "
              "60-minute threshold. October 19 has the largest date-level share "
              "(99/380, 26.05%). This is descriptive and uses unverified timestamps.")

    # 7. Hourly long-delay pattern from report's table
    slide = prs.slides.add_slide(blank)
    add_header(slide, "RQ2 • Scheduled hour", "The ≥60-minute share rises across daytime bands", 8,
               "Eligible departures grouped by scheduled local departure hour.")
    add_image_fit(slide, hourly_graph, 0.62, 1.72, 12.05, 4.45)
    add_rect(slide, 0.76, 6.24, 11.78, 0.48, "FFF4E8", rounded=True)
    add_text(slide, "Morning-to-evening difference: 4.41 percentage points. "
             "Hour bands can differ in route and schedule mix.",
             0.98, 6.27, 11.3, 0.36, 14, NAVY)
    add_notes(slide, "Morning has 110/4,531 records meeting the threshold (2.43%); "
              "evening has 233/3,406 (6.84%). The contrast is descriptive and may "
              "reflect different schedules or route mix.")

    # 8. Adjusted workday comparison using report figure
    slide = prs.slides.add_slide(blank)
    add_header(slide, "RQ3 • Adjusted workday", "10 October: fewer records, more cancellations", 9,
               "Comparison with 17 October, the closest available ordinary Saturday.")
    add_image_fit(slide, FIG / "adjusted_workday.png", 0.48, 1.78, 12.35, 3.95)
    oct10 = next(row for row in results["adjusted_workday_comparison"]
                 if row["date"] == "2026-10-10")
    oct17 = next(row for row in results["adjusted_workday_comparison"]
                 if row["date"] == "2026-10-17")
    add_rect(slide, 0.82, 5.88, 11.7, 0.76, "E8F1F7", rounded=True)
    add_text(
        slide,
        f'10 Oct: {oct10["events"]} events; cancellations '
        f'{oct10["canceled"]}/{oct10["known"]} ({oct10["cancel_pct"]:.2f}%).  '
        f'17 Oct: {oct17["events"]} events; cancellations '
        f'{oct17["canceled"]}/{oct17["known"]} ({oct17["cancel_pct"]:.2f}%).',
        1.06, 6.00, 11.2, 0.5, 15, NAVY, True,
    )
    add_notes(slide, "October 10 is the only adjusted workday represented. It had "
              "682 recorded events versus 775 on October 17, with a higher "
              "cancellation rate (4.41% vs 1.03%). This is a one-date comparison.")

    # 9. Hourly event profile
    slide = prs.slides.add_slide(blank)
    add_header(slide, "RQ3 • Hourly context", "Recorded event profiles by local-hour band", 10,
               "Counts describe event records, not scheduled capacity or passenger demand.")
    add_image_fit(slide, FIG / "adjusted_workday_hours.png", 0.62, 1.8, 12.05, 4.75)
    add_text(slide, "Public-holiday weekends are shown separately in the report figure; "
             "the 10 October / 17 October comparison is highlighted.",
             0.86, 6.62, 11.65, 0.26, 12, MUTED)
    add_notes(slide, "This report figure compares hourly event counts on October 10 and "
              "October 17, with other observed weekend and holiday dates included for "
              "context. It is not a measure of passenger demand.")

    # 10. Threshold clarification
    slide = prs.slides.add_slide(blank)
    add_header(slide, "RQ3 • Reading the delay result", "“No ≥60-minute delays” does not mean “no delays”", 11)
    add_rect(slide, 0.8, 1.7, 5.55, 2.55, PALE, rounded=True)
    add_text(slide, "10 OCTOBER 2026", 1.12, 2.02, 4.9, 0.35, 13, MUTED, True)
    add_text(slide, "0 of 323", 1.12, 2.55, 4.9, 0.72, 34, TEAL, True)
    add_text(slide, "eligible departures met the ≥60-minute threshold",
             1.12, 3.35, 4.85, 0.57, 16, NAVY)
    add_rect(slide, 6.82, 1.7, 5.55, 2.55, PALE, rounded=True)
    add_text(slide, "17 OCTOBER 2026", 7.14, 2.02, 4.9, 0.35, 13, MUTED, True)
    add_text(slide, f'{oct17["gap60_count"]} of {oct17["eligible_gap_departures"]}',
             7.14, 2.55, 4.9, 0.72, 34, BLUE, True)
    add_text(slide, "eligible departures met the ≥60-minute threshold",
             7.14, 3.35, 4.85, 0.57, 16, NAVY)
    add_text(slide, "Shorter delays may have occurred. Timestamps are assumed accurate for "
             "the calculation, but their semantics are unverified.",
             0.95, 4.82, 11.4, 0.9, 19, RED, True)
    add_text(slide, "The comparison cannot establish that adjusted-workday status caused "
             "any difference.",
             0.95, 5.95, 11.4, 0.48, 16, MUTED)
    add_notes(slide, "Be precise: zero of 323 eligible records met the study's threshold "
              "on October 10. That statement does not rule out delays below 60 minutes. "
              "The timestamp definitions are unverified.")

    # 11. Conclusions and limitations
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Conclusions", "What the report supports—and what it does not", 12)
    conclusions = [
        ("01", "Volume was broadly similar across adjacent seven-day windows.",
         "Daily variability and calendar composition still matter.", BLUE),
        ("02", "Cancellations and long-delay records peaked on different dates.",
         "Treat them as distinct outcomes and use their own denominators.", ORANGE),
        ("03", "The observed adjusted-workday contrast is descriptive only.",
         "Only one of two calendar make-up workdays is in the dataset.", TEAL),
    ]
    for index, (number, title, detail, accent) in enumerate(conclusions):
        y = 1.62 + index * 1.28
        add_text(slide, number, 0.82, y + 0.04, 0.72, 0.56, 24, accent, True)
        add_text(slide, title, 1.76, y, 10.65, 0.43, 19, NAVY, True)
        add_text(slide, detail, 1.78, y + 0.48, 10.6, 0.38, 15, MUTED)
    add_rect(slide, 0.82, 5.73, 11.7, 0.85, "FFF4E8", rounded=True)
    add_text(slide, "Next: add complete scheduled-flight coverage, September 20, "
             "multiple years, and weather / operational context.",
             1.08, 5.91, 11.15, 0.48, 16, NAVY, True)
    add_notes(slide, "Conclude with the distinct outcomes and descriptive scope. "
              "A stronger study needs repeated adjusted workdays, full schedules, "
              "and relevant operational covariates.")

    # 12. Source
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Source & reproducibility", "Report figures and analysis", 13)
    add_text(slide, "Primary source", 0.9, 1.75, 2.3, 0.35, 14, BLUE, True)
    add_text(slide, "sha_master.csv • SHA flight-event records, 22 Sep–22 Oct 2026",
             0.9, 2.15, 11.35, 0.55, 19, NAVY, True)
    add_text(slide, "Analysis outputs", 0.9, 3.05, 2.6, 0.35, 14, BLUE, True)
    add_text(slide, "final_project_word/sha_national_day_final_report.docx\n"
             "final_project_word/sha_national_day_final_results.json\n"
             "final_project_word/figures/",
             0.9, 3.45, 11.2, 1.35, 17, NAVY)
    add_text(slide, "Rebuild this deck with:\n"
             "uv run --group report python scripts/build_final_project_presentation.py",
             0.9, 5.22, 11.3, 0.9, 16, MUTED)
    add_notes(slide, "The charts in this deck use the figures and structured results "
              "generated for the final report. The hour-band chart is rendered directly "
              "from the report's hourly summary.")

    prs.save(PRESENTATION)
    print(PRESENTATION)
    print(f"Slides: {len(prs.slides)}; embedded report graphs: 4; generated hourly graph: {hourly_graph}")


if __name__ == "__main__":
    build()
