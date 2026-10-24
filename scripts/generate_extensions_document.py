"""Build an editable Word report from the reproducible research extensions."""

import json
import math
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from explore_research import analyze


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_extensions_report.docx"
FIGURES = ROOT / "research_extensions_figures"


def equivalent_results(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            equivalent_results(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            equivalent_results(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-12)
    return left == right


def build_document():
    results = analyze(ROOT / "sha_master.csv")
    saved = json.loads((ROOT / "research_extensions_results.json").read_text(encoding="utf-8"))
    if not equivalent_results(results, saved):
        raise ValueError("Saved results are stale. Rerun scripts/explore_research.py.")
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin = section.right_margin = Mm(24)
    section.top_margin, section.bottom_margin = Mm(23), Mm(20)
    section.footer_distance = Mm(11)
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(10.5)
    normal.paragraph_format.line_spacing = Pt(15)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.widow_control = True
    for name, size, color in (
        ("Title", 23, "17324D"),
        ("Heading 1", 15, "17324D"),
        ("Heading 2", 12, "285A7A"),
    ):
        style = doc.styles[name]
        style.font.name = "Times New Roman"
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor.from_string(color)
        style.font.bold = True
        style.paragraph_format.keep_with_next = True
    doc.styles["Caption"].font.name = "Times New Roman"
    doc.styles["Caption"].font.size = Pt(9)
    doc.styles["Caption"].paragraph_format.keep_with_next = False
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run()
    run.font.name, run.font.size = "Times New Roman", Pt(9)
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    run._r.append(field)
    body_text = []

    def paragraph(text, count=True):
        p = doc.add_paragraph(text)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if count:
            body_text.append(text)
        return p

    def heading(text, level=1):
        doc.add_heading(text, level=level)
        body_text.append(text)

    def table(caption, headers, rows):
        doc.add_paragraph(caption, style="Caption")
        t = doc.add_table(rows=1, cols=len(headers))
        t.style = "Light Shading Accent 1"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        for cell, text in zip(t.rows[0].cells, headers):
            cell.text = str(text)
        repeat = OxmlElement("w:tblHeader")
        t.rows[0]._tr.get_or_add_trPr().append(repeat)
        for row in rows:
            cells = t.add_row().cells
            for cell, text in zip(cells, row):
                cell.text = str(text)
        for row in t.rows:
            tr_properties = row._tr.get_or_add_trPr()
            tr_properties.append(OxmlElement("w:cantSplit"))
            for cell in row.cells:
                for p in cell.paragraphs:
                    p.paragraph_format.space_after = Pt(4)
                    p.paragraph_format.line_spacing = Pt(12)
                    for run in p.runs:
                        run.font.size = Pt(9)
        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def figure(filename, caption):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(FIGURES / filename), width=Mm(162))
        doc.add_paragraph(caption, style="Caption")

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Mm(35)
    title = doc.add_paragraph(
        "Beyond Averages:\nTimestamp Gaps and Cancellation Concentration\n"
        "at Shanghai Hongqiao Airport",
        style="Title",
    )
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for text in (
        "Proposed revised research report",
        "Exploratory analysis of 22 September–22 October 2026",
        "",
        "Student: [Add your name]",
        "Course: [Add course name and code]",
        "Instructor: [Add instructor name]",
        "Submission date: [Add date]",
        "",
        "Scope note: This report extends the original departure-time analysis. "
        "Obtain instructor approval if it changes the approved proposal.",
        "Measurement note: Recorded timestamp differences are not validated "
        "operational delays. Operating-carrier comparisons are not supported.",
    ):
        p = doc.add_paragraph(text)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    word_note = doc.add_paragraph()
    word_note.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()

    heading("Abstract")
    paragraph(
        "This study examines three complementary patterns in 23,705 flight-event records "
        "associated with Shanghai Hongqiao Airport across 31 local service dates. First, "
        "evening departures have a lower median recorded departure timestamp gap than "
        "morning departures, but a larger fraction of gaps of at least 60 minutes. A "
        "within-route, within-date comparison estimates an evening excess of 3.60 "
        "percentage points, with an exploratory date-cluster bootstrap interval of "
        "0.96–7.74 points. Second, 82.6% of paired SHA departure records whose departure "
        "gap is at least 15 minutes have an arrival gap below 15 minutes. This apparent "
        "reduction is descriptive and may reflect different schedule and event definitions. "
        "Third, five dates account for 47.6% of cancellations but 15.8% of known-status "
        "records. The findings show why central tendency, extreme-tail risk, paired "
        "measurements and temporal concentration should be examined separately. They "
        "do not establish causal effects or verified operational punctuality."
    )

    heading("1. Introduction")
    paragraph(
        "A single average can give an incomplete account of flight performance. A traveler "
        "may care about the typical departure experience, the chance of a very large "
        "departure discrepancy, whether a later departure is followed by a later arrival, "
        "or the risk of cancellation. These are different outcomes. A schedule period "
        "can look favorable on one measure and unfavorable on another, while a monthly "
        "cancellation rate can conceal substantial variation across individual dates."
    )
    paragraph(
        "The existing course analysis describes recorded departure-time differences by "
        "hour and compares morning with evening within route-weekday groups. This "
        "report extends that work rather than treating the original mean comparison as "
        "the only useful question. It studies distributional differences, paired departure "
        "and arrival timestamps, and cancellation concentration. The objective is to "
        "identify informative patterns while keeping the interpretation proportional to "
        "the evidence available in the supplied file."
    )
    paragraph(
        "Measurement is central to this objective. Every row marks timing semantics as "
        "unverified, and the operating-carrier field is blank throughout. Consequently, "
        "the report uses the expression recorded timestamp gap rather than validated "
        "operational delay. A subtraction can be arithmetically correct even when its "
        "two timestamps refer to different operational events. The dataset also covers "
        "only one airport and one month; completeness against an independent airport "
        "movement register has not been established."
    )
    paragraph(
        "The research questions are: (1) Do evening departures combine a smaller typical "
        "gap with a greater extreme-gap fraction, including when compared within the "
        "same route and date? (2) How frequently does a departure gap of at least "
        "15 minutes accompany an arrival gap below 15 minutes? (3) How concentrated "
        "are cancellations across dates, and how cautiously should calendar-category "
        "differences be interpreted? These questions were developed after inspecting "
        "the data and are explicitly exploratory rather than preregistered hypotheses."
    )

    heading("2. Literature and analytical framework")
    paragraph(
        "Mayer and Sinai (2003) study network effects, congestion externalities and hubbing "
        "in air travel. Their work provides context for considering schedule structure "
        "rather than treating every timestamp discrepancy as an isolated flight attribute. "
        "It does not establish that the patterns in this SHA file are caused by congestion. "
        "The present study has no validated measure of runway demand relative to capacity, "
        "air-traffic-control restrictions or connection-bank design, and therefore does "
        "not estimate those mechanisms."
    )
    paragraph(
        "The distinction between the center and the tail of a distribution is also "
        "substantively important. The median answers what a central observation looks "
        "like; a high percentile describes a more extreme part of the observed "
        "distribution; a threshold fraction describes how often a specified condition "
        "occurs. None is a substitute for the others. Reporting all three avoids the "
        "misleading conclusion that a period with the smaller median must be preferable "
        "under every definition of performance."
    )
    paragraph(
        "Efron (1979) develops the bootstrap as a resampling approach to uncertainty. "
        "Cameron and Miller (2015) discuss why dependence within clusters matters for "
        "inference. Flights associated with one date may share conditions, so treating "
        "every flight as independent could exaggerate precision. This report resamples "
        "whole local service dates. With only 31 clusters, the intervals remain "
        "exploratory summaries of observed-date variability, not assurances of "
        "population coverage or protection against measurement error."
    )
    paragraph(
        "These ideas motivate a descriptive framework with three safeguards. Outcomes "
        "are defined explicitly from fields in the file, uncertainty is summarized at "
        "the date level where feasible, and alternative interpretations are considered "
        "before operational explanations are proposed. Matching on route and date "
        "reduces some compositional differences but is not randomization. Likewise, "
        "a paired arithmetic reduction between departure and arrival gaps is not an "
        "independent measurement of aircraft recovery or schedule padding."
    )

    heading("3. Methods")
    heading("3.1 Data, units and inclusion criteria", 2)
    paragraph(
        "The supplied file contains 23,705 unique event identifiers: 11,873 arrival "
        "records and 11,832 departure records. Local service dates run from "
        "22 September to 22 October 2026 inclusive. The unit is a flight-event record, "
        "not a passenger or an independently verified aircraft rotation. Although "
        "identifiers are unique within the file, this does not prove that all real-world "
        "movements are represented or that event identities have been fully validated."
    )
    paragraph(
        "A known status is any nonblank status other than Unknown, after trimming "
        "whitespace and ignoring case. Canceled records remain in cancellation "
        "denominators but are excluded from timing comparisons. There are 34 "
        "unknown-status records and 487 canceled records. Departure-gap analyses "
        "additionally require both scheduled and actual departure timestamps, leaving "
        "11,560 records. This complete-case design can introduce selection if missing "
        "or unresolved records differ systematically from observed completed records."
    )
    paragraph(
        "Paired analyses additionally require scheduled departure, actual departure, "
        "scheduled arrival and recorded landing timestamps. The SHA departure cohort "
        "contains 11,551 paired records; the SHA arrival cohort contains 11,599. The "
        "cohorts are reported separately because their endpoints and SHA service-date "
        "definitions differ. Within departures, 262 unknown or canceled rows and "
        "19 additional rows lacking a paired timestamp reconcile to the full total; "
        "the corresponding arrival exclusions are 259 and 15."
    )
    heading("3.2 Outcome definitions", 2)
    paragraph(
        "All differences are calculated from timezone-aware UTC timestamps and expressed "
        "in minutes. Departure gap equals actual departure minus scheduled departure. "
        "Arrival gap equals recorded landing minus scheduled arrival. Positive values "
        "mean the recorded event is later than schedule; negative values mean it is "
        "earlier. The 15-minute and 60-minute thresholds are descriptive choices for "
        "this exploration, not validated regulatory delay classifications."
    )
    paragraph(
        "The paired reduction equals departure gap minus arrival gap. Algebraically, "
        "this is also scheduled duration minus recorded elapsed duration. The identity "
        "is checked during computation, but it provides no independent verification "
        "of event meaning. In particular, a scheduled gate-arrival time and an observed "
        "landing time can differ even without operational improvement. The conditional "
        "percentage uses records with departure gap at least 15 minutes as its "
        "denominator and those with arrival gap below 15 minutes as its numerator."
    )
    heading("3.3 Morning–evening comparison and uncertainty", 2)
    paragraph(
        "Morning is 06:00–11:59 and evening is 17:00–22:59 Shanghai local scheduled "
        "departure time, retaining the original notebook's windows. Other hours remain "
        "part of the full departure dataset but are not included in this contrast. "
        "Unadjusted summaries report each window's mean, median, 95th percentile and "
        "fraction at least 60 minutes. These describe the observed sample rather than "
        "a causal effect of choosing a departure hour."
    )
    paragraph(
        "For matching, records are grouped by directional route and local date. A cell "
        "is included when it has at least one eligible morning and one eligible "
        "evening record. Within each cell, the morning mean or threshold fraction is "
        "subtracted from the evening equivalent. The overall estimate is the "
        "equal-weight mean of cell contrasts. Thus it targets the average eligible "
        "route-date cell, not the average flight, and excludes routes lacking "
        "observations in both windows."
    )
    paragraph(
        "Uncertainty intervals use 2,000 whole-date bootstrap replicates with seed "
        "20261024, taking the 2.5th and 97.5th percentiles of replicate estimates. "
        "For matched analyses, each sampled date brings its observed eligible cells "
        "and their contrasts; eligibility is determined within date and is not "
        "recreated by pooling duplicate dates. Paired conditional fractions resample "
        "date-level numerator and denominator totals. For SHA arrivals, the cluster "
        "is the SHA arrival service date, not necessarily the origin departure date."
    )
    paragraph(
        "Two checks assess robustness of the extreme-tail contrast: requiring at least "
        "two records in each matched window, and omitting each date in turn. Paired "
        "results are also recalculated after excluding records flagged in either "
        "identity-review field, and route medians are examined for routes with at "
        "least 100 paired observations. These are sensitivity descriptions, not "
        "corrections for all possible bias or substitutes for source validation."
    )
    heading("3.4 Cancellation concentration and calendar categories", 2)
    paragraph(
        "Cancellation rates divide canceled records by known-status records. Daily "
        "summaries combine arrival and departure events for an airport-event description, "
        "without assuming they represent independent traveler experiences. Dates are "
        "ranked by cancellation count, and the five largest are compared with the "
        "remaining dates. Because this selection deliberately chooses the largest "
        "counts after inspection, its concentration statistic is not a prospective "
        "risk rule and is not assigned a significance test."
    )
    paragraph(
        "Calendar categories use the dataset's existing labels: ordinary weekday, "
        "public holiday, weekend and adjusted workday. Both the number of dates and "
        "the number of records are reported. Date-bootstrap intervals are provided "
        "only for categories with at least two dates; the one-date adjusted-workday "
        "category has no such interval. Neither these labels nor their comparisons "
        "can isolate holidays from weather, schedule changes or other date-specific "
        "conditions that are not measured here."
    )
    heading("3.5 Reproducibility and interpretation rules", 2)
    paragraph(
        "The analysis script recomputes outcomes directly from the input timestamps "
        "rather than relying solely on precomputed gap fields. It checks unique "
        "event identifiers, positive leg durations, consistent date-category labels "
        "and the paired arithmetic identity. Independent validation also reconciles "
        "cohort exclusions to direction totals and recomputes daily cancellation "
        "denominators. These checks detect several calculation or processing errors, "
        "but they cannot establish that a source timestamp represents the intended "
        "physical event."
    )
    paragraph(
        "Interpretation follows the selected estimand. Percentage-point contrasts "
        "are absolute differences between fractions, whereas the approximate "
        "2.8-fold unadjusted comparison is a ratio. The matched percentage-point "
        "contrast should not be described as an adjusted risk ratio. Likewise, "
        "conditional arrival percentages apply only to observed paired records "
        "that meet the departure threshold; they do not describe canceled "
        "flights or the full scheduled-flight population. Keeping those "
        "denominators visible prevents apparently similar percentages from "
        "being compared as if they measured the same event."
    )

    heading("4. Results")
    heading("4.1 Lower evening median, greater extreme-tail fraction", 2)
    tail = results["morning_evening_tail"]
    table(
        "Table 1. Unadjusted departure-gap summaries by local scheduled window.",
        ["Window", "Records", "Mean (min)", "Median (min)", "P95 (min)", "Gap ≥60 (%)"],
        [
            [label, f"{tail[key]['n']:,}"] + [
                f"{tail[key][metric]:.2f}"
                for metric in ("mean", "median", "p95", "ge60_pct")
            ]
            for key, label in (("morning", "Morning"), ("evening", "Evening"))
        ],
    )
    paragraph(
        "Morning contributes 4,531 records and evening contributes 3,406. The median "
        "is 18.88 minutes in the morning and 15.96 minutes in the evening, so the "
        "central evening observation has a smaller gap. However, the 95th percentile "
        "is 44.18 minutes in the morning versus 72.73 minutes in the evening. The "
        "fraction at least 60 minutes is 2.43% versus 6.84%, an unadjusted ratio "
        "of approximately 2.8. The evening mean is also slightly larger despite "
        "its smaller median."
    )
    figure(
        "tail_risk.png",
        "Figure 1. Central tendency and extreme-tail measures give different morning–evening "
        "comparisons. Bars describe unadjusted observed records; they are not causal estimates.",
    )
    paragraph(
        "The matched comparison includes 860 route-date cells, 6,948 records and all "
        "31 dates. The equal-cell average evening-minus-morning mean difference is "
        "+0.52 minutes, with a date-bootstrap interval of −2.31 to +4.71 minutes. "
        "By contrast, the matched difference in the fraction at least 60 minutes is "
        "+3.60 percentage points, with an interval of +0.96 to +7.74 points. The "
        "observed tail difference therefore persists in this matched description "
        "even though the average-gap contrast is close to zero."
    )
    table(
        "Table 2. Within-route, within-date contrasts; all signs are evening minus morning.",
        ["Comparison", "Cells", "Estimate", "95% date-bootstrap interval"],
        [
            ["Mean gap", "860", "+0.52 min", "−2.31 to +4.71 min"],
            ["Gap ≥60 fraction", "860", "+3.60 pp", "+0.96 to +7.74 pp"],
            ["Mean gap; ≥2 per window", "644", "+0.50 min", "−2.49 to +4.81 min"],
            ["Gap ≥60; ≥2 per window", "644", "+3.86 pp", "+0.93 to +8.21 pp"],
        ],
    )
    paragraph(
        "The stricter matching rule retains 644 cells across all 31 dates and gives "
        "an extreme-fraction difference of +3.86 percentage points. Omitting each "
        "date in turn gives differences ranging from +1.79 to +3.93 points, so no "
        "single omitted date reverses the direction. These checks support the "
        "descriptive stability of the selected contrast, but the exploratory "
        "choice of outcome and windows still requires caution. They do not "
        "establish that changing a flight's hour would change its outcome."
    )
    heading("4.2 The paired departure–arrival pattern", 2)
    pair_rows = []
    for direction in ("arrival", "departure"):
        summary = results["paired_timestamps"][direction]
        ci = summary["arrival_lt15_among_departure_ge15_date_bootstrap_ci_pct"]
        pair_rows.append([
            "SHA " + direction + "s",
            f"{summary['n']:,}",
            f"{summary['departure']['median']:.2f}",
            f"{summary['arrival']['median']:.2f}",
            f"{summary['arrival_lt15_among_departure_ge15_pct']:.2f}%",
            f"{ci[0]:.2f}–{ci[1]:.2f}%",
        ])
    table(
        "Table 3. Paired timestamp summaries. Conditional fraction: arrival gap <15 "
        "among records with departure gap ≥15.",
        ["Cohort", "Paired n", "Median dep. (min)", "Median arr. (min)", "Conditional %", "95% interval"],
        pair_rows,
    )
    paragraph(
        "In the SHA departure cohort, the median departure gap is +17.30 minutes "
        "and the median arrival gap is −8.97 minutes. Among the 6,923 paired records "
        "whose departure gap is at least 15 minutes, 5,721 have an arrival gap "
        "below 15 minutes. This is 82.64%, with a date-bootstrap interval of "
        "78.68%–86.37%. The criterion means less than 15 minutes after scheduled "
        "arrival; it does not require an early arrival or an exact on-time event."
    )
    paragraph(
        "The SHA arrival cohort shows a similar descriptive pattern: 4,125 of "
        "5,096 records meeting the departure threshold have arrival gaps below "
        "15 minutes, or 80.95%, with an interval of 78.46%–83.66%. The median "
        "paired reduction is 27.32 minutes for SHA departures and 29.68 minutes "
        "for SHA arrivals. These are medians of record-level paired reductions, "
        "not subtractions of separately computed cohort medians."
    )
    figure(
        "paired_timestamps.png",
        "Figure 2. Paired-cohort medians and conditional arrival-gap fractions. Error bars "
        "are exploratory 95% date-bootstrap intervals. Event semantics remain unverified.",
    )
    paragraph(
        "After excluding identity-review flags, conditional percentages are 82.66% "
        "for SHA departures and 80.93% for SHA arrivals, very close to the main "
        "results. For each cohort, all 31 routes with at least 100 paired records "
        "have a positive median paired reduction. This suggests the arithmetic "
        "pattern is not confined to one qualifying route. It does not resolve "
        "the possibility that the same event-definition mismatch is present "
        "systematically across routes."
    )
    heading("4.3 Cancellations are concentrated on particular dates", 2)
    cancellations = results["cancellations"]
    table(
        "Table 4. Five dates with the largest observed cancellation counts.",
        ["Date", "Canceled", "Known-status records", "Cancellation rate (%)"],
        [
            [day["date"], day["canceled"], day["known"], f"{day['canceled_pct']:.2f}"]
            for day in cancellations["top5_dates"]
        ],
    )
    paragraph(
        "The five selected dates contain 232 of 487 cancellations, or 47.64%, "
        "while accounting for 15.84% of known-status records. Their combined "
        "cancellation rate is 6.19%, compared with 1.28% on the other dates. "
        "The highest cancellation count occurs on 29 September, with 62 of "
        "761 known-status records canceled. The contrast demonstrates temporal "
        "concentration in this file, not that the selected dates form a "
        "predefined high-risk category."
    )
    figure(
        "cancellation_dates.png",
        "Figure 3. Daily cancellation rates among known-status event records. Orange "
        "identifies the five dates selected retrospectively by cancellation count.",
    )
    table(
        "Table 5. Calendar-category cancellation summaries; pp denotes percentage points elsewhere.",
        ["Category", "Dates", "Known", "Canceled", "Rate (%)", "95% interval (%)"],
        [
            [
                group["category"].replace("_", " "),
                group["dates"], f"{group['known']:,}", group["canceled"],
                f"{group['canceled_pct']:.2f}",
                "Not estimable" if group["date_bootstrap_ci_pct"] is None else
                "–".join(f"{value:.2f}" for value in group["date_bootstrap_ci_pct"]),
            ]
            for group in cancellations["calendar"]
        ],
    )
    paragraph(
        "Public holidays have a cancellation rate of 2.42% across ten dates, "
        "compared with 1.93% across 17 ordinary weekdays. Their separate "
        "date-bootstrap intervals overlap, but overlap is not itself a formal "
        "test of a difference or proof of equality. Weekends contribute only "
        "three dates. The adjusted-workday rate is 4.41%, but it comes entirely "
        "from one date. A large number of records within that date does not "
        "provide independent replication of adjusted-workday conditions."
    )

    heading("5. Discussion")
    paragraph(
        "The first contribution is to separate typical outcomes from extreme-tail "
        "risk. Saying that evening is better because its median is smaller "
        "would omit the larger fraction of very large gaps. Saying that "
        "evening is uniformly worse would also be inaccurate. The matched "
        "mean contrast is small, whereas the matched extreme-fraction contrast "
        "is positive. A defensible summary states both results and specifies "
        "which outcome supports each statement."
    )
    paragraph(
        "The second contribution is measurement-aware interpretation of paired "
        "timestamps. The common combination of later departure timestamps and "
        "earlier arrival timestamps is striking, but an appealing operational "
        "story is not necessarily the correct one. Different event definitions, "
        "scheduled buffers, timestamp provenance or other recording processes "
        "could contribute. Claims about pilots flying faster, deliberate "
        "padding or successful delay recovery require additional evidence "
        "that this study does not contain."
    )
    paragraph(
        "The third contribution is to distinguish calendar labels from "
        "date-specific concentration. The concentration chart identifies where "
        "many cancellations occur, but it cannot explain why. A holiday "
        "interpretation would require stronger design and additional observations, "
        "including ordinary and holiday periods across a longer span. Weather "
        "and operational restrictions are not available, and cancellation "
        "effects may connect several related events rather than representing "
        "independent decisions for every row."
    )
    paragraph(
        "Several limitations apply jointly. The sample is restricted to one "
        "airport and 31 dates, so annual seasonality and general airport "
        "performance are outside its scope. Complete-case filtering may "
        "select a nonrepresentative set of records. Matched analyses retain "
        "only route-date cells observed in both windows and weight them "
        "equally. Bootstrap intervals address resampling variability, not "
        "unknown measurement errors, missing confounders, incomplete coverage "
        "or the exploratory search that preceded these questions."
    )
    paragraph(
        "Practical recommendations must therefore remain modest. The observed "
        "patterns justify further data validation and a replication study, "
        "not advice that passengers should always choose a particular hour "
        "or airline. An independently collected month could test the "
        "predefined morning–evening extreme-gap comparison. Verified event "
        "definitions would make paired timing interpretations more credible. "
        "A documented observation frame, weather measures and validated "
        "operator identities would support more ambitious research questions."
    )
    paragraph(
        "A useful replication would select its outcome and thresholds before "
        "examining the new month. The primary descriptive target could be "
        "the equal-cell evening-minus-morning difference in the fraction of "
        "departure gaps of at least 60 minutes, retaining the same windows "
        "and matching criteria. Reporting all eligible dates, the matched "
        "sample coverage and any exclusions would help distinguish a "
        "repeated pattern from one driven by changes in observation or "
        "schedule composition. A changed result would be informative rather "
        "than a reason to search for a different favorable threshold."
    )
    paragraph(
        "The figures should also be read in their proper roles. The first "
        "shows unadjusted distribution summaries and should be accompanied "
        "by the matched estimates in Table 2. The second separates inbound "
        "and outbound cohorts and displays uncertainty for a conditional "
        "fraction, not for every bar. The third highlights retrospectively "
        "selected cancellation dates. Clear captions and explicit units "
        "make these distinctions visible and prevent a visually persuasive "
        "chart from carrying a claim that the underlying analysis does "
        "not support."
    )
    paragraph(
        "Finally, record-level findings are not passenger-weighted measures. "
        "The file does not provide passenger loads, missed connections, "
        "rebooking outcomes or the costs associated with a disruption. "
        "A small number of canceled events could affect many travelers, "
        "while a large timestamp discrepancy on another event could affect "
        "fewer. The research therefore evaluates patterns in observed "
        "flight-event records, not total traveler welfare or an airport's "
        "overall service quality."
    )

    heading("6. Conclusion")
    paragraph(
        "This exploratory study finds that evening departures can have a smaller "
        "median recorded gap while showing a larger extreme-gap fraction, "
        "including within matched routes and dates. It also documents a "
        "frequent reduction between recorded departure and arrival gaps and "
        "substantial cancellation concentration on a few dates. The strongest "
        "conclusion is methodological as well as empirical: averages, tail "
        "fractions, paired outcomes and temporal concentration reveal different "
        "features of the same dataset and should not be conflated."
    )
    paragraph(
        "The findings are useful as a transparent, reproducible and measurement-aware course-project analysis, "
        "provided they are presented as descriptive associations. Timing "
        "semantics remain unverified, operating-carrier comparisons cannot "
        "be supported, and no causal mechanism has been identified. "
        "Reproducible computation, explicit denominators, sensitivity checks "
        "and candid limitations make the conclusions more defensible than "
        "a stronger-sounding but unsupported operational claim."
    )

    doc.add_heading("References", level=1)
    references = [
        "Cameron, A. C., & Miller, D. L. (2015). A practitioner's guide to "
        "cluster-robust inference. Journal of Human Resources, 50(2), 317–372. "
        "https://doi.org/10.3368/jhr.50.2.317",
        "Efron, B. (1979). Bootstrap methods: Another look at the jackknife. "
        "The Annals of Statistics, 7(1), 1–26. https://doi.org/10.1214/aos/1176344552",
        "Mayer, C., & Sinai, T. (2003). Network effects, congestion externalities, "
        "and air traffic delays: Or why not all delays are evil. American Economic "
        "Review, 93(4), 1194–1215. https://doi.org/10.1257/000282803769206269",
        "SHA flight dataset. (2026). sha_master.csv [User-supplied flight-event dataset; "
        "analyzed 24 October 2026]. Source URLs and retrieval timestamps are included "
        "in the file. Event semantics and operating-carrier identities are unverified.",
    ]
    for reference in references:
        p = paragraph(reference, count=False)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.left_indent = Mm(6)
        p.paragraph_format.first_line_indent = Mm(-6)
    doc.add_heading("Appendix A. Reproducibility and submission checklist", level=1)
    for text in (
        "Numerical source: research_extensions_results.json, recomputed from sha_master.csv "
        "by scripts/explore_research.py. Notebook: research_extensions.ipynb. "
        "Figures: research_extensions_figures. This Word generator refuses to build "
        "if the saved numerical results differ from a fresh analysis.",
        "Rebuild numbers: uv run python scripts/explore_research.py. "
        "Rebuild this document: uv run --group report python scripts/generate_extensions_document.py. "
        "If the input data change, rerun the research notebook to refresh its three figures "
        "before generating a report; figure files are not regenerated by this document builder.",
        "Before submission: replace the cover placeholders; confirm the approved research scope "
        "and course word-count rules; check all figures and references; disclose tool assistance "
        "if required by course policy; retain the unverified-timestamp warning. "
        "The original notebook and original PDF report have not been replaced.",
    ):
        paragraph(text, count=False)
    count = len(re.findall(r"\b[\w]+(?:[-'][\w]+)*\b", " ".join(body_text)))
    word_note.text = (
        f"Main-text word count: {count:,} (abstract and sections 1–6, including headings; "
        "excluding tables, captions, cover, references and appendix)."
    )
    doc.core_properties.title = "Beyond Averages: Timestamp Gaps and Cancellation Concentration at SHA"
    doc.core_properties.subject = "Exploratory course research report"
    doc.core_properties.keywords = "SHA; timestamp gaps; extreme-tail risk; cancellation; exploratory"
    doc.core_properties.comments = "Generated from reproducible research results; cover details require completion."
    doc.save(OUTPUT)
    print(f"Saved {OUTPUT}; main-text words={count}; tables={len(doc.tables)}; figures={len(doc.inline_shapes)}")


if __name__ == "__main__":
    build_document()
