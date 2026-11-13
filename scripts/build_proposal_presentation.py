"""Build a research-proposal presentation with clearly labeled preliminary results."""

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches

from build_final_project_presentation import (
    BG,
    BLUE,
    FIG,
    MUTED,
    NAVY,
    ORANGE,
    PALE,
    RED,
    RESULTS,
    TEAL,
    WHITE,
    add_card,
    add_header,
    add_image_fit,
    add_notes,
    add_rect,
    add_text,
    color,
    make_hourly_delay_graph,
)


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "final_project_word" / "Holiday_Flight_Disruption_Patterns.pptx"


def add_calendar_slide(prs, blank):
    slide = prs.slides.add_slide(blank)
    add_header(
        slide,
        "Study context • official calendar",
        "The sample spans the National Day break and adjusted workday",
        4,
        "China’s official calendar can designate weekend dates as working days.",
    )
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
                in_sample = day >= 22
                public_holiday = False
                adjusted_workday = day == 20
            else:
                in_sample = day <= 22
                public_holiday = day <= 7
                adjusted_workday = day == 10
            if public_holiday:
                fill, text_fill = BLUE, WHITE
            elif adjusted_workday:
                fill, text_fill = ORANGE, WHITE
            elif in_sample:
                fill, text_fill = "DCEAF5", NAVY
            else:
                fill, text_fill = "F1F4F7", "9AA8B5"
            label = f"{day}*" if month.startswith("SEPTEMBER") and day == 20 else str(day)
            add_rect(slide, x, y, cell_w, cell_h, fill, rounded=True)
            add_text(slide, label, x, y + 0.01, cell_w, cell_h - 0.02, 14,
                     text_fill, public_holiday or adjusted_workday, PP_ALIGN.CENTER)

    legend_y = 5.67
    for x, fill, label, width in (
        (0.82, "DCEAF5", "Study window", 1.55),
        (3.25, BLUE, "Public holiday", 1.75),
        (5.95, ORANGE, "Make-up workday", 2.05),
        (9.10, "F1F4F7", "Outside window", 1.85),
    ):
        add_rect(slide, x, legend_y + 0.045, 0.22, 0.22, fill, rounded=True)
        add_text(slide, label, x + 0.31, legend_y, width, 0.32, 12, NAVY, True)
    add_text(
        slide,
        "A make-up workday is an official working day on a weekend. "
        "Oct 10 is observed; Sep 20* is outside the sample.",
        0.84, 6.13, 11.7, 0.36, 14, NAVY, True,
    )
    add_text(
        slide,
        "Source: State Council General Office, 2026 holiday arrangement (2025 notice).",
        0.84, 6.78, 11.6, 0.18, 9, MUTED,
    )
    add_notes(
        slide,
        "The proposal analyzes September 22 through October 22. October 1–7 are "
        "National Day public holidays; October 10 is a Saturday designated as a "
        "working day. September 20 was also designated a working day but is outside "
        "the dataset. Official calendar labels are therefore kept separate from "
        "ordinary weekend labels. Source: General Office of the State Council of "
        "the People's Republic of China, 2025 notice on 2026 public-holiday "
        "arrangements: https://www.gov.cn/zhengce/content/202511/content_7047090.htm",
    )
    return slide


def build():
    results = json.loads(RESULTS.read_text(encoding="utf-8"))
    hourly_delay_figure = make_hourly_delay_graph(results)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333333), Inches(7.5)
    blank = prs.slide_layouts[6]

    # 1. Proposal title
    slide = prs.slides.add_slide(blank)
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color(NAVY)
    add_rect(slide, 0, 0, 0.16, 7.5, TEAL)
    add_text(slide, "RESEARCH PROPOSAL", 0.82, 0.72, 11.8, 0.36,
             15, "91C9BD", True)
    add_text(
        slide,
        "China’s National Day Calendar\nand Flight Activity at SHA",
        0.82, 1.45, 11.8, 1.50, 34, WHITE, True,
    )
    add_text(
        slide,
        "Research questions, data collection, methodology, and preliminary results",
        0.86, 3.18, 11.5, 0.62, 19, "DCE7F0",
    )
    for x, label, value in (
        (0.85, "AIRPORT", "Shanghai Hongqiao"),
        (4.72, "OBSERVATION WINDOW", "22 Sep–22 Oct 2026"),
        (8.59, "SAMPLE", f'{results["rows"]:,} event records'),
    ):
        add_rect(slide, x, 5.15, 3.5, 1.0, "254560", rounded=True)
        add_text(slide, label, x + 0.18, 5.29, 3.12, 0.22, 11, "B8C8D7", True)
        add_text(slide, value, x + 0.18, 5.58, 3.12, 0.4, 17, WHITE, True)
    add_text(slide, "All results shown are preliminary and descriptive.",
             0.86, 6.62, 11.5, 0.32, 13, "DCE7F0", True)
    add_notes(
        slide,
        "Introduce this as a research proposal grounded in an existing one-month "
        "sample. The results are preliminary descriptions, not final causal findings.",
    )

    # 2. Rationale and study aim
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Background & rationale",
               "Why calendar classification matters", 2)
    add_card(
        slide, 0.78, 1.70, 5.75, 2.08, "Calendar context",
        "Weekend ≠ always a rest day",
        "China’s official holiday schedule can designate weekend dates as working days.",
        BLUE,
    )
    add_card(
        slide, 6.80, 1.70, 5.75, 2.08, "Operational question",
        "Do records differ by date type?",
        "Compare flight-event volume, cancellations, and eligible departure-time gaps.",
        ORANGE,
    )
    add_rect(slide, 0.82, 4.20, 11.68, 1.30, PALE, rounded=True)
    add_text(slide, "Study aim", 1.08, 4.43, 1.55, 0.34, 15, TEAL, True)
    add_text(
        slide,
        "Describe service-event patterns across the National Day period and examine "
        "the observed 10 October adjusted workday in its calendar context.",
        2.55, 4.36, 9.40, 0.62, 19, NAVY, True,
    )
    add_text(
        slide,
        "Scope: one airport, one month, one observed adjusted workday.",
        0.98, 5.95, 11.3, 0.45, 16, MUTED, True,
    )
    add_notes(
        slide,
        "The motivation is to avoid treating every Saturday or Sunday as the same "
        "calendar type. This proposal describes the supplied SHA flight-event sample "
        "and does not claim that the holiday calendar causes any observed difference.",
    )

    # 3. Research questions
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Research questions",
               "Three questions organize the proposed analysis", 3)
    questions = [
        ("RQ1", "Flight volume & cancellations",
         "How did event volume and cancellation rates vary before, during, and after the holiday?",
         BLUE),
        ("RQ2", "Long-delay concentration",
         "Were departures meeting the ≥60-minute timestamp-gap threshold concentrated on particular dates or hours?",
         ORANGE),
        ("RQ3", "Adjusted workday",
         "How did 10 October compare with ordinary weekend dates in the observed records?",
         TEAL),
    ]
    for index, (tag, title, detail, accent) in enumerate(questions):
        y = 1.62 + index * 1.58
        add_rect(slide, 0.72, y, 11.85, 1.30, PALE, rounded=True)
        add_rect(slide, 0.93, y + 0.22, 0.78, 0.78, accent, rounded=True)
        add_text(slide, tag, 0.94, y + 0.24, 0.76, 0.72, 16, WHITE, True,
                 PP_ALIGN.CENTER)
        add_text(slide, title, 1.98, y + 0.12, 10.1, 0.42, 20, NAVY, True)
        add_text(slide, detail, 1.98, y + 0.58, 10.1, 0.55, 15, MUTED)
    add_text(slide, "Unit: a recorded arrival or departure event, not a passenger.",
             0.86, 6.58, 11.6, 0.28, 13, MUTED, True)
    add_notes(
        slide,
        "The questions cover calendar phases, concentration in long timestamp gaps, "
        "and the October 10 adjusted-workday case. Each is answered descriptively "
        "with this one-month file.",
    )

    # 4. Calendar context
    add_calendar_slide(prs, blank)

    # 5. Data and collection
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Data collection",
               "A retrospective sample from flight-history pages", 5)
    add_card(
        slide, 0.72, 1.68, 3.82, 2.0, "Sample",
        f'{results["rows"]:,} records',
        f'{results["dates"]} observed dates at SHA',
        BLUE,
    )
    add_card(
        slide, 4.76, 1.68, 3.82, 2.0, "Source pages",
        "841 URLs",
        "Flightradar24 flight-history pages involving SHA",
        TEAL,
    )
    add_card(
        slide, 8.80, 1.68, 3.82, 2.0, "Retrieval",
        "22–23 Oct 2026",
        "Flight-event dates in the file: 22 Sep–22 Oct 2026",
        ORANGE,
    )
    add_rect(slide, 0.78, 4.05, 11.74, 1.75, PALE, rounded=True)
    add_text(slide, "Collection and preparation", 1.02, 4.27, 4.0, 0.36,
             17, NAVY, True)
    add_text(
        slide,
        "Visible history-table rows were mapped into the project CSV. Source-page "
        "URLs and retrieval timestamps were retained; listed origin and destination "
        "identify SHA arrivals and departures.",
        1.02, 4.73, 11.0, 0.78, 16, NAVY,
    )
    add_text(
        slide,
        "Coverage caveat: the collected records do not verify a complete scheduled-flight list.",
        0.90, 6.15, 11.4, 0.42, 14, RED, True,
    )
    add_notes(
        slide,
        "The CSV has 23,705 event records and 841 distinct source URLs. The pages "
        "were retrieved on October 22–23, 2026, while the flight-event dates span "
        "September 22 to October 22. This is a retrospective capture, not continuous "
        "monitoring, and the sample does not prove complete schedule coverage.",
    )

    # 6. Proposed analysis and operational definitions
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Methodology",
               "How the research questions are addressed", 6)
    steps = [
        ("1", "Calendar phases",
         "Compare equal seven-day pre-holiday, National Day, and post-holiday windows.",
         BLUE),
        ("2", "Cancellation measure",
         "Cancelled records ÷ records with known status; report the denominator.",
         ORANGE),
        ("3", "Departure-gap measure",
         "Among known-status, non-cancelled departures with both timestamps, flag gaps ≥60 minutes.",
         TEAL),
        ("4", "Adjusted-workday context",
         "Describe 10 October beside 17 October and other weekends; keep public holidays separate.",
         RED),
    ]
    for index, (number, title, detail, accent) in enumerate(steps):
        y = 1.55 + index * 1.12
        add_rect(slide, 0.86, y + 0.10, 0.52, 0.52, accent, rounded=True)
        add_text(slide, number, 0.87, y + 0.11, 0.50, 0.50, 15, WHITE, True,
                 PP_ALIGN.CENTER)
        add_text(slide, title, 1.62, y + 0.02, 3.0, 0.34, 17, NAVY, True)
        add_text(slide, detail, 4.25, y - 0.02, 7.9, 0.68, 15, MUTED)
    add_rect(slide, 0.86, 6.10, 11.55, 0.52, "FFF4E8", rounded=True)
    add_text(
        slide,
        "Timestamp semantics are unverified: the ≥60-minute indicator is exploratory, not an official delay measure.",
        1.08, 6.17, 11.1, 0.36, 13, NAVY, True,
    )
    add_notes(
        slide,
        "The seven-day windows are equal in length but not calendar-identical. "
        "Cancellation rates use known-status records only. Delay summaries use "
        "eligible non-cancelled departures and an analytical 60-minute cutoff. "
        "The source does not verify timestamp semantics.",
    )

    # 7. Preliminary result: phases
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Preliminary results • RQ1",
               "Recorded volume was similar; cancellation rates varied", 7,
               "Descriptive summaries for three equal-length seven-day windows.")
    accents = [BLUE, TEAL, ORANGE]
    for index, (period, accent) in enumerate(zip(results["periods"], accents)):
        x = 0.72 + index * 4.05
        add_rect(slide, x, 1.88, 3.78, 3.68, PALE, rounded=True)
        add_text(slide, period["label"].upper(), x + 0.22, 2.13, 3.34, 0.33,
                 13, accent, True)
        add_text(slide, f'{period["events"]:,}', x + 0.22, 2.61, 3.3, 0.62,
                 29, NAVY, True)
        add_text(slide, f'{period["per_day"]:.1f} events per day',
                 x + 0.24, 3.26, 3.25, 0.38, 15, MUTED)
        add_rect(slide, x + 0.22, 3.78, 3.34, 0.02, "D3DEE8")
        add_text(slide, f'{period["cancel_pct"]:.2f}%',
                 x + 0.22, 4.01, 3.25, 0.52, 24, accent, True)
        add_text(
            slide,
            f'{period["canceled"]} / {period["known"]} known-status records cancelled',
            x + 0.24, 4.59, 3.2, 0.55, 13, NAVY,
        )
    add_text(
        slide,
        "Preliminary only: calendar composition differs across the windows.",
        0.92, 5.96, 11.3, 0.42, 15, MUTED, True,
    )
    add_notes(
        slide,
        "These are preliminary descriptive results from three seven-day windows. "
        "The pre-holiday window contains Mid-Autumn holidays and the post-holiday "
        "window contains October 10, an adjusted workday. Do not treat the windows "
        "as controlled groups.",
    )

    # 8. Preliminary result: daily pattern
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Preliminary results • RQ1",
               "Daily patterns provide context for the phase averages", 8)
    add_image_fit(slide, FIG / "daily_trends.png", 0.45, 1.52, 8.15, 4.95)
    top_cancel = results["top_cancellation_dates"][0]
    add_card(
        slide, 8.78, 1.93, 3.82, 1.86, "Highest observed daily cancellation rate",
        f'{top_cancel["date"][5:]} • {top_cancel["cancel_pct"]:.2f}%',
        f'{top_cancel["canceled"]} of {top_cancel["known"]} known-status records',
        RED,
    )
    add_text(
        slide,
        "The one-month series is descriptive; a peak date is not a recurring risk estimate.",
        8.86, 4.22, 3.60, 0.96, 15, MUTED,
    )
    add_notes(
        slide,
        "The graph is the report figure. September 29 has the highest observed daily "
        "cancellation rate: 62 of 761 known-status records, or 8.15%. This is one "
        "date in one month and does not establish a recurring risk.",
    )

    # 9. Preliminary result: delay concentrations
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Preliminary results • RQ2",
               "Long timestamp gaps vary by date and scheduled hour", 9,
               "The ≥60-minute threshold is exploratory; timestamp semantics are unverified.")
    add_image_fit(slide, FIG / "extreme_dates.png", 0.42, 1.70, 6.75, 4.55)
    add_image_fit(slide, hourly_delay_figure, 7.20, 1.70, 5.68, 4.55)
    add_text(
        slide,
        f'{results["extreme_gap_records"]:,} / {results["eligible_gap_records"]:,} '
        f'eligible departures met the threshold '
        f'({results["extreme_gap_pct"]:.2f}%).',
        0.86, 6.30, 11.55, 0.38, 14, NAVY, True,
    )
    add_notes(
        slide,
        "Preliminary findings: 514 of 11,560 eligible departures have a recorded "
        "gap of at least 60 minutes. The largest date-level share is October 19 "
        "(99/380, 26.05%). The daytime band shares range from 2.43% in the morning "
        "to 6.84% in the evening. These timestamp comparisons are exploratory, "
        "not validated operational delays.",
    )

    # 10. Preliminary result: adjusted workday comparison
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Preliminary results • RQ3",
               "One observed adjusted-workday comparison", 10,
               "10 October (adjusted workday) versus 17 October (ordinary Saturday).")
    add_image_fit(slide, FIG / "adjusted_workday.png", 0.42, 1.58, 8.30, 4.8)
    oct10 = next(row for row in results["adjusted_workday_comparison"]
                 if row["date"] == "2026-10-10")
    oct17 = next(row for row in results["adjusted_workday_comparison"]
                 if row["date"] == "2026-10-17")
    add_rect(slide, 8.88, 1.92, 3.80, 3.60, PALE, rounded=True)
    add_text(slide, "10 OCTOBER", 9.12, 2.16, 3.3, 0.3, 12, MUTED, True)
    add_text(slide, f'{oct10["events"]} events',
             9.12, 2.52, 3.3, 0.46, 23, RED, True)
    add_text(slide,
             f'{oct10["canceled"]}/{oct10["known"]} cancellations '
             f'({oct10["cancel_pct"]:.2f}%)',
             9.12, 3.05, 3.3, 0.60, 14, NAVY)
    add_text(slide,
             f'{oct10["gap60_count"]}/{oct10["eligible_gap_departures"]} '
             'met ≥60 min threshold',
             9.12, 3.72, 3.3, 0.56, 14, NAVY)
    add_rect(slide, 9.12, 4.40, 3.25, 0.02, "D3DEE8")
    add_text(slide, "17 OCTOBER", 9.12, 4.60, 3.3, 0.28, 12, MUTED, True)
    add_text(
        slide,
        f'{oct17["events"]} events • {oct17["canceled"]}/{oct17["known"]} '
        f'cancelled ({oct17["cancel_pct"]:.2f}%) • '
        f'{oct17["gap60_count"]}/{oct17["eligible_gap_departures"]} '
        'met threshold',
        9.12, 4.93, 3.25, 0.55, 12, NAVY,
    )
    add_text(
        slide,
        "Preliminary, one-date contrast—not an adjusted-workday effect. "
        "Zero at ≥60 minutes does not rule out shorter delays.",
        0.86, 6.44, 11.8, 0.38, 13, MUTED, True,
    )
    add_notes(
        slide,
        "October 10 has 682 recorded events, a 4.41% cancellation share, and 0 of "
        "323 eligible departures meeting the ≥60-minute threshold. October 17 has "
        "775 events, a 1.03% cancellation share, and 14 of 384 eligible departures "
        "meeting it. This is a preliminary one-date description. It does not mean "
        "there were no shorter delays and cannot establish a calendar effect.",
    )

    # 11. Scope and interpretation
    slide = prs.slides.add_slide(blank)
    add_header(slide, "Scope & interpretation",
               "How to read the preliminary results", 11)
    limits = [
        ("ONE MONTH", "22 Sep–22 Oct 2026", BLUE),
        ("ONE OBSERVED WORKDAY", "10 October; Sep 20 is outside the file", ORANGE),
        ("EVENT RECORDS", "Not passengers or a verified full schedule", TEAL),
        ("UNVERIFIED TIMESTAMPS", "≥60-minute result is an exploratory indicator", RED),
    ]
    for i, (label, detail, accent) in enumerate(limits):
        y = 1.68 + i * 0.98
        add_rect(slide, 0.90, y, 3.05, 0.62, accent, rounded=True)
        add_text(slide, label, 1.03, y + 0.08, 2.78, 0.42, 12, WHITE, True)
        add_text(slide, detail, 4.30, y + 0.05, 7.80, 0.48, 16, NAVY)
    add_rect(slide, 0.90, 5.90, 11.40, 0.70, PALE, rounded=True)
    add_text(
        slide,
        "The proposal is to characterize these observed patterns; the preliminary results do not identify causes.",
        1.14, 6.02, 10.95, 0.48, 15, NAVY, True,
    )
    add_notes(
        slide,
        "Close by restating the boundaries of the proposal. This sample covers one "
        "month, includes one of the two adjusted workdays, contains event records "
        "rather than passenger data or a verified complete schedule, and has "
        "unverified timestamp semantics. The preliminary results describe patterns "
        "only and do not identify causes.",
    )

    prs.core_properties.title = (
        "Research Proposal: China’s National Day Calendar and Flight Activity at SHA"
    )
    prs.core_properties.subject = "Proposal with preliminary descriptive results"
    prs.save(PRESENTATION)
    print(PRESENTATION)
    print(f"Slides: {len(prs.slides)}; all result slides are labeled preliminary.")


if __name__ == "__main__":
    build()
