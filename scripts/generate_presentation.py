"""Create a visual, editable presentation with detailed speaker notes."""

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
NAVY = "142D46"
BLUE = "2878B5"
ORANGE = "E07A32"
GREEN = "33866B"
MUTED = "58697A"
PALE = "EDF3F8"
WHITE = "FFFFFF"
BG = "FAFCFE"


def build():
    data = json.loads((ROOT / "research_extensions_results.json").read_text(encoding="utf-8"))
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333333), Inches(7.5)
    tail = data["morning_evening_tail"]
    paired = data["paired_timestamps"]["departure"]
    cancellations = data["cancellations"]

    def rect(slide, x, y, width, height, color, rounded=False):
        shape = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
            Inches(x), Inches(y), Inches(width), Inches(height),
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(color)
        shape.line.fill.background()
        if rounded:
            shape.adjustments[0] = 0.08
        return shape

    def text(slide, value, x, y, width, height, size=24, color=NAVY,
             bold=False, align=PP_ALIGN.LEFT):
        shape = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(width), Inches(height))
        frame = shape.text_frame
        frame.word_wrap = True
        frame.margin_left = frame.margin_right = Inches(0.02)
        frame.margin_top = frame.margin_bottom = 0
        frame.vertical_anchor = MSO_ANCHOR.MIDDLE
        for index, line in enumerate(value.split("\n")):
            p = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            p.text = line
            p.alignment = align
            p.space_after = Pt(5)
            p.font.name = "Aptos"
            p.font.size = Pt(size)
            p.font.bold = bold
            p.font.color.rgb = RGBColor.from_string(color)
        return shape

    def slide(title, eyebrow, notes, subtitle=None):
        s = prs.slides.add_slide(prs.slide_layouts[6])
        s.background.fill.solid()
        s.background.fill.fore_color.rgb = RGBColor.from_string(BG)
        rect(s, 0, 0, 13.333, 0.08, BLUE)
        text(s, eyebrow.upper(), 0.55, 0.27, 12.2, 0.28, 13, BLUE, True)
        text(s, title, 0.55, 0.8, 12.2, 0.88, 32, bold=True)
        if subtitle:
            text(s, subtitle, 0.58, 1.72, 12.1, 0.48, 18, MUTED)
        rect(s, 0.55, 6.99, 12.2, 0.015, "D9E3EC")
        text(s, "SHA \u2022 22 Sep\u201322 Oct 2026 \u2022 exploratory timestamp analysis",
             0.58, 7.10, 11.4, 0.22, 11, MUTED)
        text(s, str(len(prs.slides)), 12.1, 7.08, 0.6, 0.27, 12, MUTED,
             align=PP_ALIGN.RIGHT)
        s.notes_slide.notes_text_frame.text = notes
        return s

    def card(s, x, y, width, number, label, color=BLUE, detail=None):
        rect(s, x, y, width, 2.55, PALE, True)
        text(s, number, x + 0.22, y + 0.24, width - 0.44, 0.9, 45, color, True)
        text(s, label, x + 0.22, y + 1.21, width - 0.44, 0.82, 22, bold=True)
        if detail:
            text(s, detail, x + 0.22, y + 2.02, width - 0.44, 0.35, 15, MUTED)

    def banner(s, value, y=6.2, color=NAVY):
        rect(s, 0.6, y, 12.1, 0.57, color, True)
        text(s, value, 0.8, y + 0.04, 11.7, 0.46, 19, WHITE, True)

    def bars(s, x, y, width, height, values, labels, colors, maximum, suffix=""):
        # Fixed bounds keep the editable bar shapes and labels inside the panel.
        baseline = y + height
        rect(s, x, baseline, width, 0.018, "B7C6D4")
        bar_width = min(1.05, width / (len(values) * 2.5))
        for index, (value, label, color) in enumerate(zip(values, labels, colors)):
            center = x + width * (index + 0.5) / len(values)
            bar_height = height * value / maximum
            rect(s, center - bar_width / 2, baseline - bar_height,
                 bar_width, bar_height, color)
            text(s, f"{value:.1f}{suffix}", center - 0.85, baseline - bar_height - 0.48,
                 1.7, 0.4, 25, color, True, PP_ALIGN.CENTER)
            text(s, label, center - 1.1, baseline + 0.13, 2.2, 0.4,
                 19, MUTED, align=PP_ALIGN.CENTER)

    s = slide(
        "Beyond averages", "Research presentation \u2022 Shanghai Hongqiao",
        "Opening (about 30 seconds): This presentation asks what averages hide in the "
        "supplied SHA flight-event records. Preview the three stories: typical gaps versus "
        "extreme gaps, paired departure and arrival timestamps, and cancellation concentration. "
        "Emphasize that this is an exploratory analysis, not a verified operational delay study. "
        "Replace the name and course placeholders before presenting. Main deck: slides 1\u201312, "
        "approximately 8\u201310 minutes. Slides 13\u201314 are backup material.",
    )
    text(s, "Timestamp gaps & cancellation concentration", 0.6, 2.0, 11.8, 0.7, 28, MUTED)
    for x, number, label, color in (
        (0.6, "01", "Typical \u2260 extreme", BLUE),
        (4.73, "02", "Departure \u2260 arrival", ORANGE),
        (8.86, "03", "Dates \u2260 averages", GREEN),
    ):
        card(s, x, 3.05, 3.87, number, label, color)
    text(s, "[Your name]  \u2022  [Course]  \u2022  [Presentation date]", 0.65, 6.28, 11.9, 0.4, 18, MUTED)

    s = slide(
        "One airport. One month. Three lenses.", "The dataset",
        "Use 40 seconds to define the observation frame. There are 23,705 unique event "
        "IDs, split into 11,873 arrivals and 11,832 departures, across 31 SHA local dates. "
        "The timing analysis uses 11,560 departure records after excluding canceled, "
        "unknown-status and missing-timestamp records. Paired analyses use a different "
        "complete-case denominator. Every row marks timing_semantics_verified false. "
        "Operating-carrier identity is blank throughout; do not rank airlines. A unique "
        "ID does not establish complete or independently validated airport coverage.",
        "22 September\u201322 October 2026",
    )
    card(s, 0.6, 2.55, 3.87, f"{data['audit']['rows']:,}", "Flight-event records")
    card(s, 4.73, 2.55, 3.87, "31", "Local service dates", ORANGE)
    card(s, 8.86, 2.55, 3.87, f"{data['audit']['eligible_departures']:,}", "Timing-eligible departures", GREEN)
    banner(s, "Recorded timestamp gaps \u2014 not validated operational delays")

    s = slide(
        "What does an average hide?", "Research questions",
        "Introduce the questions in around 30 seconds. Question one asks whether central "
        "tendency and extreme-tail risk point in different directions. Question two asks "
        "about a conditional paired outcome, not aircraft recovery. Question three asks "
        "whether cancellations cluster on a few dates. All questions were selected after "
        "inspecting this file, so these are exploratory findings. No confirmatory p-values "
        "or causal claims are made.",
    )
    for y, n, title, detail, color in (
        (2.22, "1", "Typical experience or extreme risk?", "Compare morning and evening departures.", BLUE),
        (3.62, "2", "Later departure \u2192 later arrival?", "Link the timestamps within each record.", ORANGE),
        (5.02, "3", "A monthly rate or a few unusual dates?", "Measure cancellation concentration.", GREEN),
    ):
        rect(s, 0.6, y, 0.75, 0.75, color, True)
        text(s, n, 0.6, y, 0.75, 0.75, 30, WHITE, True, PP_ALIGN.CENTER)
        text(s, title, 1.65, y - 0.03, 10.6, 0.58, 26, bold=True)
        text(s, detail, 1.65, y + 0.58, 10.6, 0.4, 19, MUTED)

    s = slide(
        "Evening: lower median, heavier upper tail", "Finding 1 \u2022 Distribution",
        "Spend about one minute on this contrast. Morning means scheduled SHA local hours "
        "06:00\u201311:59; evening is 17:00\u201322:59. Morning n=4,531 and evening n=3,406. "
        "The median is lower in the evening, but the 95th percentile is much higher. "
        "The 95th percentile describes an upper-tail cutoff, not the average of the "
        "worst five percent. These are unadjusted observed distributions and not a "
        "causal effect of departure hour. Source: research_extensions_results.json, "
        "morning_evening_tail.",
        "Morning 06:00\u201311:59  |  Evening 17:00\u201322:59  \u2022  Shanghai local time",
    )
    for x, metric, title, maximum in ((0.8, "median", "MEDIAN GAP \xb7 MINUTES", 30),
                                     (7.1, "p95", "95TH PERCENTILE \xb7 MINUTES", 90)):
        text(s, title, x, 2.35, 5.25, 0.4, 17, MUTED, True)
        bars(s, x, 3.15, 5.2, 2.05,
             [tail[w][metric] for w in ("morning", "evening")],
             ["Morning", "Evening"], [BLUE, ORANGE], maximum)
    banner(s, "A smaller typical gap does not mean less extreme risk.")

    risk_ratio = tail["evening"]["ge60_pct"] / tail["morning"]["ge60_pct"]
    s = slide(
        "Extreme gaps are about 2.8\xd7 as common in evening", "Finding 1 \u2022 Tail risk",
        "Define extreme here as a recorded departure timestamp gap of at least 60 minutes. "
        "This threshold is exploratory, not an official delay category. The observed "
        "fractions are 2.4277% for morning and 6.8409% for evening; their ratio is "
        "approximately 2.82. This is an unadjusted ratio of fractions, not a matched "
        "risk ratio. The denominator includes only timing-eligible departure records "
        "in each window, so this does not include cancellation risk. Next ask whether "
        "the pattern remains when comparing the same route on the same date.",
        "Extreme = recorded departure gap \u226560 minutes",
    )
    bars(s, 0.9, 3.0, 6.5, 2.3,
         [tail[w]["ge60_pct"] for w in ("morning", "evening")],
         ["Morning", "Evening"], [BLUE, ORANGE], 9, "%")
    card(s, 8.15, 2.75, 4.0, f"{risk_ratio:.1f}\xd7", "Observed fraction ratio", ORANGE,
         "Unadjusted \u2022 not a causal effect")
    banner(s, "But could route mix or the date explain the pattern?")

    s = slide(
        "The tail difference persists within route and date", "Finding 1 \u2022 Matched comparison",
        "Explain the matching in about one minute. There are 860 route-date cells with "
        "at least one morning and one evening departure, representing 6,948 records "
        "and all 31 dates. Compute evening minus morning within each cell and then "
        "average cells equally. The mean gap contrast is +0.517 minutes, with interval "
        "\u22122.307 to +4.708. The at-least-60-minute fraction contrast is +3.600 percentage "
        "points, with interval +0.961 to +7.740. Intervals use 2,000 whole-date bootstrap "
        "replicates, seed 20261024; they are exploratory. Requiring two records per "
        "window retains 644 cells and gives +3.86 points, interval +0.93 to +8.21. "
        "Leaving one date out gives +1.79 to +3.93 points. Matching reduces measured "
        "composition differences but cannot establish causation.",
        "860 route-date cells  \u2022  31 dates  \u2022  evening minus morning",
    )
    for y, title, estimate, low, high, left, right, units, color in (
        (2.6, "Mean gap", tail["matched_mean_difference"],
         *tail["matched_mean_difference_date_bootstrap_ci"], -4, 9, "minutes", BLUE),
        (4.25, "Gap \u226560 fraction", tail["matched_ge60_difference_pp"],
         *tail["matched_ge60_difference_pp_date_bootstrap_ci"], -4, 9, "percentage points", ORANGE),
    ):
        text(s, title, 0.7, y, 3.5, 0.45, 24, bold=True)
        text(s, f"{estimate:+.2f} {units}", 0.7, y + 0.52, 4.1, 0.38, 18, color)
        x0, width = 5.05, 6.95
        scale = lambda value: x0 + (value - left) / (right - left) * width
        rect(s, scale(0), y - 0.02, 0.018, 1.02, "B7C6D4")
        rect(s, scale(low), y + 0.35, scale(high) - scale(low), 0.055, color)
        for value in (low, high):
            rect(s, scale(value), y + 0.23, 0.025, 0.3, color)
        circle = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(scale(estimate) - 0.09),
                                   Inches(y + 0.28), Inches(0.18), Inches(0.18))
        circle.fill.solid()
        circle.fill.fore_color.rgb = RGBColor.from_string(color)
        circle.line.fill.background()
        text(s, f"95% interval: {low:+.2f} to {high:+.2f}", 5.05, y + 0.7, 7.0, 0.3, 16, MUTED)
    banner(s, "Mean contrast \u2248 zero; extreme-tail contrast stays positive.")

    recovery = paired["arrival_lt15_among_departure_ge15_pct"]
    s = slide(
        "A later departure need not mean later arrival", "Finding 2 \u2022 Paired timestamps",
        "Use about one minute. Among 11,551 paired SHA departure records, 6,923 have a "
        "departure gap of at least 15 minutes. Of those, 5,721 have an arrival gap "
        "below 15 minutes: 82.64%, date-bootstrap interval 78.68%\u201386.37%. Less than "
        "15 minutes does not mean early arrival. This is a conditional percentage "
        "among complete paired records, not all scheduled flights. The inbound SHA "
        "cohort independently shows 80.95%, interval 78.46%\u201383.66%, and should not "
        "be pooled with this cohort. Departure-cohort median departure gap is +17.3 "
        "and median arrival gap \u22128.97 minutes. Do not describe these as validated "
        "operational delay recovery.",
        "SHA departure cohort \u2022 paired complete records only",
    )
    card(s, 0.6, 2.65, 3.87, f"{paired['departure_ge15_n']:,}", "Departure gap \u226515 min", BLUE)
    text(s, "\u2192", 4.48, 3.25, 0.3, 0.7, 30, MUTED, True)
    card(s, 4.85, 2.65, 3.87,
         f"{paired['arrival_lt15_among_departure_ge15_n']:,}", "Arrival gap <15 min", GREEN)
    card(s, 8.86, 2.65, 3.87, f"{recovery:.1f}%", "Conditional fraction", GREEN)
    ci = paired["arrival_lt15_among_departure_ge15_date_bootstrap_ci_pct"]
    text(s, f"95% date-bootstrap interval: {ci[0]:.1f}%\u2013{ci[1]:.1f}%",
         0.7, 5.55, 11.9, 0.4, 20, MUTED)
    banner(s, "This is a timestamp pattern \u2014 not proof of time made up in flight.")

    s = slide(
        "Before telling a story, check what the clocks measure", "Interpretation \u2022 Measurement",
        "Explain the key caveat in about 45 seconds. Departure gap minus arrival gap "
        "algebraically equals scheduled duration minus recorded elapsed duration. "
        "That identity is checked computationally, but is not independent evidence "
        "of airborne recovery. Scheduled gate events and recorded takeoff or landing "
        "events could refer to different physical moments. Schedule buffers could "
        "also contribute, but deliberate padding is not established. Every row's "
        "timing_semantics_verified flag is false. The next study must verify event "
        "definitions and timestamp provenance before claiming operational recovery.",
    )
    for x, title, detail, color in (
        (0.6, "Schedule", "What event does the\npublished time describe?", BLUE),
        (6.87, "Recorded event", "What event does the\nobserved time describe?", ORANGE),
    ):
        rect(s, x, 2.45, 5.86, 2.7, PALE, True)
        text(s, title, x + 0.3, 2.75, 5.25, 0.6, 31, color, True)
        text(s, detail, x + 0.3, 3.65, 5.25, 1.0, 24)
    banner(s, "Possible event mismatch \u2260 proven aircraft recovery")

    share = cancellations["top5_dates_share_of_cancellations_pct"]
    exposure = cancellations["top5_dates_share_of_known_records_pct"]
    s = slide(
        "Five dates account for almost half the cancellations", "Finding 3 \u2022 Concentration",
        "Spend about 45 seconds. The five dates with the largest observed cancellation "
        "counts contain 232 of 487 cancellations, or 47.64%, but only 15.84% of "
        "known-status event records. Rates are 6.19% on those dates and 1.28% on "
        "the remaining dates. Both inbound and outbound events are included for this "
        "airport-event description. Events can be related, not independent passenger "
        "experiences. The top five were selected after looking at the outcomes, so "
        "the comparison deliberately selects high-count dates. It is a concentration "
        "description, not a predictive risk rule or a statistical test.",
        "Top five dates selected by observed cancellation count",
    )
    for y, label, value, color in (
        (2.75, "Share of cancellations", share, ORANGE),
        (4.35, "Share of known-status records", exposure, BLUE),
    ):
        text(s, label, 0.7, y - 0.48, 9.5, 0.4, 24, bold=True)
        rect(s, 0.75, y + 0.15, 9.6, 0.55, PALE, True)
        rect(s, 0.75, y + 0.15, 9.6 * value / 100, 0.55, color, True)
        text(s, f"{value:.1f}%", 10.65, y - 0.02, 2.0, 0.85, 36, color, True)
    banner(s, "Cancellation rates: 6.19% on these dates vs 1.28% otherwise")

    s = slide(
        "The daily pattern is more revealing than one monthly rate", "Finding 3 \u2022 Date-level view",
        "Point to the largest bars rather than reading each date. September 29 has "
        "62 cancellations among 761 known-status records, the highest count. Orange "
        "bars mark the five dates selected retrospectively by cancellation count, "
        "not necessarily a predefined class. Public-holiday cancellation rate is "
        "2.42% across ten dates and ordinary weekday rate 1.93% across 17 dates. "
        "These descriptive comparisons do not identify a holiday effect. Adjusted "
        "workday has just one date, so it cannot support a general conclusion. "
        "Unknown status is excluded from daily denominators.",
        "Canceled \xf7 known-status event records \u2022 orange = top five dates by count",
    )
    daily = cancellations["daily"]
    top = {day["date"] for day in cancellations["top5_dates"]}
    x0, y0, width, height, maximum = 1.0, 2.65, 11.4, 2.8, 10
    for tick in (0, 4, 8):
        yy = y0 + height * (1 - tick / maximum)
        rect(s, x0, yy, width, 0.012, "D9E3EC")
        text(s, f"{tick}%", 0.42, yy - 0.17, 0.5, 0.32, 14, MUTED)
    step = width / len(daily)
    for index, day in enumerate(daily):
        bar_h = height * day["canceled_pct"] / maximum
        if bar_h:
            rect(s, x0 + step * index + 0.04, y0 + height - bar_h,
                 step - 0.08, bar_h, ORANGE if day["date"] in top else BLUE)
        if index in (0, 7, 14, 21, 30):
            text(s, day["date"][5:], x0 + step * index - 0.3,
                 y0 + height + 0.13, 0.95, 0.35, 14, MUTED, align=PP_ALIGN.CENTER)
    text(s, "29 Sep: 62 / 761 canceled (8.15%)", 0.9, 2.17, 11.4, 0.35, 20, ORANGE, True)
    banner(s, "Concentration is clear. Its cause is not identified.")

    s = slide(
        "Strong patterns. Limited claims.", "Limitations & next steps",
        "Summarize in 40 seconds. The three most important limitations are unverified "
        "timing semantics, one airport over 31 dates, and exploratory selection of "
        "questions. Weather, ATC constraints, complete aircraft rotations, passenger "
        "loads and verified operating-carrier identities are not available. Missing "
        "records can bias complete-case timing results. Date-bootstrap intervals do "
        "not address these problems. Sensitivity checks reduce concern about specific "
        "choices but do not validate a causal interpretation. Recommend event-definition "
        "verification and replication on an independent month with predefined outcomes.",
    )
    for x, n, title, detail, color in (
        (0.6, "01", "Unverified clocks", "Validate event definitions", BLUE),
        (4.73, "02", "One month, one airport", "Replicate in another month", ORANGE),
        (8.86, "03", "Exploratory, not causal", "Predefine the next test", GREEN),
    ):
        card(s, x, 2.65, 3.87, n, title, color, detail)
    banner(s, "Do not claim airline rankings, holiday effects, or proven recovery.")

    s = slide(
        "Three takeaways to remember", "Conclusion \u2022 Questions?",
        "Close in 30 seconds. First, central tendency and extreme risk are different: "
        "evening has a lower median but a heavier extreme tail in these records. "
        "Second, paired timestamps often show a reduction, but event definitions "
        "prevent a claim of verified operational recovery. Third, cancellations "
        "are concentrated on a few dates, without an identified cause. The message "
        "is not that the dataset answers everything; it is that a careful analysis "
        "can reveal more while making narrower, defensible claims. Invite questions. "
        "Use the next two backup slides for methods and references.",
    )
    for y, number, statement, color in (
        (2.45, "1", "Typical experience \u2260 extreme-tail risk", BLUE),
        (3.65, "2", "Timestamp reduction \u2260 proven recovery", ORANGE),
        (4.85, "3", "Monthly average \u2260 daily experience", GREEN),
    ):
        text(s, number, 0.75, y, 0.7, 0.7, 36, color, True)
        text(s, statement, 1.65, y, 10.6, 0.7, 28, bold=True)
    banner(s, "Look beyond averages \u2014 and stay honest about measurement.")

    s = slide(
        "Methods & robustness at a glance", "Backup \u2022 If asked",
        "This is a backup slide, not necessary in the main 8\u201310-minute narrative. "
        "Timing filter: known noncanceled departure status plus scheduled and actual "
        "departure timestamps. There are 246 canceled departures, 16 unknown-status "
        "departures and 10 additional missing-timestamp records, leaving 11,560. "
        "Paired departures additionally require scheduled arrival and landed_status_utc, "
        "leaving 11,551. Paired arrivals n=11,599. Resample whole SHA service dates "
        "2,000 times, seed 20261024. Matching weights route-date cells equally, "
        "not flights. Sensitivity min-two-per-window: 644 cells, tail contrast "
        "+3.86 pp [0.93,8.21]. Leave-one-date-out range +1.79 to +3.93 pp. "
        "Paired identity exclusion yields 82.66% conditional fraction versus 82.64% "
        "main; all 31 routes with n\u2265100 per cohort have a positive median reduction.",
    )
    details = [
        ("Timing sample", "Known, noncanceled status + required timestamps"),
        ("Matching", "Same route and date; equal cell weights"),
        ("Uncertainty", "2,000 whole-date bootstrap samples"),
        ("Sensitivity", "\u22652 records per window; leave one date out"),
        ("Paired check", "Identity-flag exclusion gives a similar fraction"),
    ]
    for index, (label, detail) in enumerate(details):
        y = 2.2 + index * 0.82
        text(s, label, 0.75, y, 2.8, 0.5, 21, BLUE, True)
        text(s, detail, 3.7, y, 8.8, 0.5, 21)

    s = slide(
        "Sources & reproducibility", "Backup \u2022 References",
        "Bibliographic context: Cameron and Miller (2015), A practitioner's guide to "
        "cluster-robust inference, Journal of Human Resources 50(2), 317\u2013372; "
        "https://doi.org/10.3368/jhr.50.2.317. Efron (1979), Bootstrap methods: Another "
        "look at the jackknife, Annals of Statistics 7(1), 1\u201326; "
        "https://doi.org/10.1214/aos/1176344552. Mayer and Sinai (2003), Network "
        "effects, congestion externalities, and air traffic delays: Or why not all "
        "delays are evil, American Economic Review 93(4),1194\u20131215; "
        "https://doi.org/10.1257/000282803769206269. These references provide context, "
        "not independent validation of the SHA outcomes. Data: user-supplied "
        "sha_master.csv, analyzed 24 October 2026. Numbers: "
        "research_extensions_results.json, generated by scripts/explore_research.py. "
        "Notebook: research_extensions.ipynb. No external airport data were added. "
        "Confirm the course's AI assistance disclosure policy and approved scope.",
    )
    for index, (label, detail) in enumerate((
        ("Data", "User-supplied SHA flight-event dataset (2026)"),
        ("Clustered inference", "Cameron & Miller (2015) \u2022 doi:10.3368/jhr.50.2.317"),
        ("Bootstrap", "Efron (1979) \u2022 doi:10.1214/aos/1176344552"),
        ("Air-transport context", "Mayer & Sinai (2003) \u2022 doi:10.1257/000282803769206269"),
    )):
        y = 2.2 + index * 0.85
        text(s, label, 0.75, y, 3.6, 0.5, 20, BLUE, True)
        text(s, detail, 4.3, y, 8.2, 0.58, 18)
    text(s, "Full citations and speaking guidance are in the slide notes.",
         0.75, 5.95, 11.8, 0.4, 19, MUTED)

    output = ROOT / "sha_research_presentation.pptx"
    prs.core_properties.title = "Beyond Averages: SHA Research"
    prs.core_properties.subject = "Exploratory timestamp gaps and cancellation concentration"
    prs.core_properties.keywords = "SHA; flight data; exploratory research; presentation"
    prs.save(output)
    print(f"Saved {output}; slides={len(prs.slides)}; all plots are editable vector shapes.")


if __name__ == "__main__":
    build()
