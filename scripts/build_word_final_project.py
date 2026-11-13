"""Build the three-question Word report and documented Jupyter notebook."""
from pathlib import Path
import json
import re

import nbformat
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from build_final_project import ROOT, read, analysis

OUT = ROOT / "final_project_word"
FIG = OUT / "figures"


def field_page(paragraph):
    run = paragraph.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._r.append(fld)


def add_table(doc, caption, headers, rows):
    doc.add_paragraph(caption, style="Caption")
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Light Shading Accent 1"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, value in zip(table.rows[0].cells, headers):
        cell.text = str(value)
    for header_cell in table.rows[0].cells:
        for run in header_cell.paragraphs[0].runs:
            run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for cell, value in zip(cells, row):
            cell.text = str(value)
    for table_row in table.rows:
        tr = table_row._tr.get_or_add_trPr()
        tr.append(OxmlElement("w:cantSplit"))
        for cell in table_row.cells:
            cell.vertical_alignment = 1
            for paragraph in cell.paragraphs:
                paragraph.paragraph_format.space_after = Pt(3)
                paragraph.paragraph_format.line_spacing = 1.0
                for run in paragraph.runs:
                    run.font.size = Pt(8.5)
    doc.add_paragraph()


def build_figures(res):
    FIG.mkdir(parents=True, exist_ok=True)

    daily = res["daily"]
    dates = [d["date"] for d in daily]
    fig, axes = plt.subplots(2, 1, figsize=(8.2, 7.2), sharex=True)
    axes[0].plot(dates, [d["events"] for d in daily], marker="o", ms=3, color="#2878b5")
    axes[0].set_ylabel("Flight-event records")
    axes[0].set_title("Daily flight-event volume")
    axes[0].grid(axis="y", alpha=.25)
    axes[1].plot(dates, [d["cancel_pct"] for d in daily], marker="o", ms=3, color="#e07a32")
    axes[1].set_ylabel("Cancellation (%)")
    axes[1].yaxis.set_major_formatter(PercentFormatter())
    axes[1].grid(axis="y", alpha=.25)
    axes[1].tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(FIG / "daily_trends.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    extreme_dates = res["extreme_dates"]
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    ax.barh(
        [x["date"] for x in extreme_dates][::-1],
        [x["extreme_pct"] for x in extreme_dates][::-1],
        color="#e07a32",
    )
    ax.set_xlabel("Departures delayed ≥60 min (% of eligible departures)")
    ax.set_title("Dates with the highest long-delay proportions")
    ax.xaxis.set_major_formatter(PercentFormatter())
    ax.grid(axis="x", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIG / "extreme_dates.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    comparison = res["adjusted_workday_comparison"]
    selected = [d for d in comparison if d["adjusted_workday"] or d["weekday"] in ("Saturday", "Sunday")]
    labels = [
        f"{d['date']}\n"
        + ("adjusted workday" if d["adjusted_workday"] else
           f"{d['public_holiday'].replace('_', ' ')} holiday" if d["public_holiday"] != "none" else
           "ordinary weekend")
        for d in selected
    ]
    colors = [
        "#be4b48" if d["adjusted_workday"] else
        "#8c8c8c" if d["public_holiday"] != "none" else
        "#2878b5"
        for d in selected
    ]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.4))
    axes[0].bar(labels, [d["arrivals"] for d in selected], color=colors, label="Arrivals")
    axes[0].bar(labels, [d["departures"] for d in selected], bottom=[d["arrivals"] for d in selected], color="#9bbbd2", label="Departures")
    axes[0].set_ylabel("Flight-event records")
    axes[0].set_title("Volume by direction")
    axes[0].legend(frameon=False, fontsize=8)
    axes[1].bar(labels, [d["cancel_pct"] for d in selected], color=colors)
    axes[1].set_ylabel("Cancellation (%)")
    axes[1].yaxis.set_major_formatter(PercentFormatter())
    axes[1].set_title("Known-status cancellations")
    axes[2].bar(labels, [d["gap60_pct"] for d in selected], color=colors)
    axes[2].set_ylabel("Departures delayed ≥60 min (%)")
    axes[2].yaxis.set_major_formatter(PercentFormatter())
    axes[2].set_title("Eligible departure delays")
    for ax in axes:
        ax.grid(axis="y", alpha=.25)
        ax.tick_params(axis="x", labelrotation=55, labelsize=7)
    fig.tight_layout()
    fig.savefig(FIG / "adjusted_workday.png", dpi=220, bbox_inches="tight")
    plt.close(fig)

    saturday_comparison = [d for d in selected if d["date"] in ("2026-10-10", "2026-10-17")]
    band_order = ["Morning (06-11)", "Afternoon (12-16)", "Evening (17-22)", "Night/other (23-05)"]
    x = list(range(len(band_order)))
    width = .36
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    for index, day in enumerate(saturday_comparison):
        counts = [day["hour_band_events"].get(band, 0) for band in band_order]
        ax.bar(
            [value + (index - .5) * width for value in x],
            counts,
            width,
            label=f"{day['date']} ({day['day_type'].replace('_', ' ')})",
            color="#be4b48" if day["adjusted_workday"] else "#2878b5",
        )
    ax.set_xticks(x, ["Morning\n06–11", "Afternoon\n12–16", "Evening\n17–22", "Night/other\n23–05"])
    ax.set_ylabel("Recorded flight-event records")
    ax.set_title("Recorded event profile: adjusted vs ordinary Saturday")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=.25)
    fig.tight_layout()
    fig.savefig(FIG / "adjusted_workday_hours.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def build_notebook(res):
    nb = nbformat.v4.new_notebook(metadata={"kernelspec": {"display_name": "Course 6611 env", "language": "python", "name": "course6611-core"}})
    nb.cells = [
        nbformat.v4.new_markdown_cell("""# SHA Flight-Service Patterns Around China's 2026 National Day Holiday

**Research questions:**
1. How did flight-service volume and cancellation rates vary before, during, and after the holiday?
2. Were cancellations and departures delayed by at least 60 minutes concentrated on particular dates or departure hours?
3. How did the October 10 adjusted workday compare with ordinary weekend dates in the observed flight-event records?

This notebook uses the supplied `sha_master.csv`. China's 2026 National Day calendar identifies September 20 and October 10 as adjusted workdays. The dataset covers September 22–October 22, so only October 10 is observed; September 20 is outside the data window, not a zero-flight observation. For this analysis, scheduled and actual departure timestamps are assumed accurate, and a difference of at least 60 minutes is treated as a departure delay.

**Scope and data boundary:** The unit of observation is a flight-event record. These data do not establish passenger demand, complete scheduled-flight coverage, or causal calendar effects."""),
        nbformat.v4.new_code_cell("""from pathlib import Path
from datetime import date, timedelta, datetime

import pandas as pd
from IPython.display import Image, display

DATA = Path('sha_master.csv')
if not DATA.exists():
    DATA = Path('..') / 'sha_master.csv'
FIG = Path('final_project_word/figures')
if not FIG.is_dir():
    FIG = Path('figures')
if not FIG.is_dir():
    raise FileNotFoundError('Report figures are missing; run scripts/build_word_final_project.py first.')
df = pd.read_csv(DATA, encoding='utf-8-sig', keep_default_na=False)
df['_date'] = pd.to_datetime(df['local_date']).dt.date
df['_hour'] = df['local_hour'].astype(int)
print(f'{len(df):,} records; {df["local_date"].nunique()} dates')
print(f'Unique event IDs: {df["event_id"].nunique()}')"""),
        nbformat.v4.new_markdown_cell("""## Methods and definitions

- **Flight status:** the source-reported flight-progress or outcome label in `status_display` (for example, `Canceled`, `Landed [time]`, `Estimated departure [time]`, or `Diverted to [airport]`).
- **Known status:** a flight-status label that is neither blank nor `unknown`.
- **Cancellation rate:** cancelled known-status records ÷ all known-status records, expressed as a percentage (a per-record share, not a time-based rate).
- **Period comparison:** RQ1 compares three consecutive 7-day windows; daily results supplement the period-level comparison.
- **Departure delay:** `actual_departure_utc - scheduled_departure_utc >= 60` minutes among known-status, non-cancelled departures with both timestamps. This analysis assumes the scheduled and actual timestamps are valid and represent the named events.
- **Hour bands:** morning 06–11, afternoon 12–16, evening 17–22, and night/other 23–05.
- **Adjusted-workday scope:** September 20 and October 10 are calendar make-up workdays, but September 20 is outside the observed date range.
- The source's `timing_semantics_verified` flag is false, but this analysis treats the timestamps as valid under the stated assumption."""),
        nbformat.v4.new_code_cell("""def known(status):
    normalized = status.str.strip().str.lower()
    return normalized.ne('') & normalized.ne('unknown')

def cancelled(status):
    return status.str.strip().str.lower().eq('canceled')

def pct(n,d):
    return 100*n/d if d else 0

def summarize(frame):
    known_status = known(frame['status_display'])
    k = int(known_status.sum())
    c = int((cancelled(frame['status_display']) & known_status).sum())
    return {'events':len(frame), 'known':k, 'unknown':len(frame)-k, 'cancelled':c,
            'cancellation_pct':pct(c,k)}"""),
        nbformat.v4.new_markdown_cell("""## RQ1 — Comparison across equal-length calendar phases

To answer how outcomes varied before, during, and after the holiday, this section first compares three consecutive seven-day windows: 24–30 September (pre-holiday), 1–7 October (National Day), and 8–14 October (post-holiday). Each window must contain all seven dates. The pre-holiday window includes the 25–27 September Mid-Autumn public holidays, while the post-holiday window includes the 10 October adjusted workday, so these are chronological—not calendar-identical—phases.

The period summaries give the before/during/after comparison. The daily chart below supplements them because period averages can conceal high- or low-cancellation dates within a window. This figure is the same report-generated `daily_trends.png` used in the Word report."""),
        nbformat.v4.new_code_cell("""holiday = date(2026,10,1)
periods = [('Pre-holiday', holiday-timedelta(days=7), holiday-timedelta(days=1)),
           ('National Day', holiday, holiday+timedelta(days=6)),
           ('Post-holiday', holiday+timedelta(days=7), holiday+timedelta(days=13))]
period_rows = []
for label,start,end in periods:
    subset=df.loc[df['_date'].between(start, end)]
    if subset['_date'].nunique() != 7:
        raise ValueError(f'{label} period must contain all 7 dates: {start} to {end}')
    summary=summarize(subset)
    period_rows.append({
        'Period': label,
        'Dates': f'{start} to {end}',
        'Events': summary['events'],
        'Events/day': len(subset)/7,
        'Known status': summary['known'],
        'Unknown status': summary['unknown'],
        'Cancellations': summary['cancelled'],
        'Cancellation rate': summary['cancellation_pct'],
    })
period_summary = pd.DataFrame(period_rows)
print('RQ1 period comparison (three complete seven-day windows):')
print(period_summary.to_string(index=False, formatters={
    'Events/day': '{:.1f}'.format,
    'Cancellation rate': '{:.2f}%'.format,
}))

by_date = {d: group for d, group in df.groupby('_date', sort=True)}
daily = [(d, summarize(group)) for d, group in by_date.items()]
display(Image(filename=str(FIG / 'daily_trends.png')))
print('Calendar qualifiers: 25–27 Sep = Mid-Autumn public holiday; 1–7 Oct = National Day holiday; 10 Oct = adjusted workday.')"""),
        nbformat.v4.new_markdown_cell("""## RQ2 — Concentration on dates and hours

The numerator is a date/hour count of departures with a delay of at least 60 minutes. It is compared with the eligible known-status, non-cancelled departure denominator. Cancellations are analysed separately and are not eligible for departure-delay calculation."""),
        nbformat.v4.new_code_cell("""departure_mask = (
    df['direction'].eq('departure')
    & known(df['status_display'])
    & ~cancelled(df['status_display'])
)
departures = df.loc[departure_mask]
has_timestamps = (
    departures['scheduled_departure_utc'].ne('')
    & departures['actual_departure_utc'].ne('')
)
missing = int((~has_timestamps).sum())
eligible = departures.loc[has_timestamps].copy()
eligible['gap'] = (
    pd.to_datetime(eligible['actual_departure_utc'], utc=True)
    - pd.to_datetime(eligible['scheduled_departure_utc'], utc=True)
).dt.total_seconds() / 60

date_ext = []
for d, group in eligible.groupby('_date', sort=True):
    extreme = int(group['gap'].ge(60).sum())
    date_ext.append((d, len(group), extreme, pct(extreme, len(group))))
print('Eligible departures:',len(eligible),'missing timestamps:',missing,
      'delays ≥60 min:',int(eligible['gap'].ge(60).sum()))
print('Highest date-level delay proportions:',sorted(date_ext,key=lambda x:(-x[3],-x[2]))[:5])

def hour_band(hour):
    if 6 <= hour <= 11:
        return 'Morning (06–11)'
    if 12 <= hour <= 16:
        return 'Afternoon (12–16)'
    if 17 <= hour <= 22:
        return 'Evening (17–22)'
    return 'Night/other'

eligible['_band'] = eligible['_hour'].map(hour_band)
for band, group in eligible.groupby('_band', sort=True):
    extreme = int(group['gap'].ge(60).sum())
    print(band, 'eligible departures=',len(group),'delays ≥60 min=',extreme,
          'delay percentage=',round(pct(extreme,len(group)),2))

display(Image(filename=str(FIG / 'extreme_dates.png')))"""),
        nbformat.v4.new_markdown_cell("""The date-level view is not a test of recurring causation. October 10 is examined separately because ordinary weekday/weekend labels are not sufficient descriptions in China's adjusted-workday calendar. The long-delay date chart is the same report-generated `extreme_dates.png` used in the Word report."""),
        nbformat.v4.new_code_cell("""print('Top cancellation dates')
top=sorted(daily,key=lambda ds:(-ds[1]['cancellation_pct'],ds[0].isoformat()))[:5]
for d,s in top:
    print(d.isoformat(), s)

print('October 10 adjusted workday')
print(summarize(df.loc[df['_date'].eq(date(2026,10,10))]))
print('Ordinary weekends')
for d,s in daily:
    if by_date[d]['calendar_day_type'].iloc[0]=='weekend':
        print(d.isoformat(),s)"""),
        nbformat.v4.new_markdown_cell("""## RQ3 — Adjusted workday case study

October 10 was officially a Saturday adjusted workday. The closest ordinary-Saturday comparison in the data is October 17. October 11 and 18 provide Sunday context; public-holiday weekend dates remain separately labelled. September 20, the other National Day make-up workday, is outside the dataset. These one-date comparisons are descriptive and cannot establish a recurring adjusted-workday effect. Hour-band counts describe recorded events, not verified scheduled capacity or passenger demand."""),
        nbformat.v4.new_code_cell("""adjusted_flag = df['adjusted_workday'].astype(str).str.lower().eq('true')
focus = df.loc[df['weekday'].isin(['Saturday', 'Sunday']) | adjusted_flag]
comparison_rows = []
for d, group in focus.groupby('_date', sort=True):
    summary = summarize(group)
    day_eligible = eligible.loc[eligible['_date'].eq(d)]
    extreme = int(day_eligible['gap'].ge(60).sum())
    band_counts = (
        group.assign(_band=group['_hour'].map(hour_band))
        .groupby('_band').size()
    )
    comparison_rows.append({
        'date': d.isoformat(),
        'weekday': group['weekday'].iloc[0],
        'calendar_day_type': group['calendar_day_type'].iloc[0],
        'public_holiday': group['public_holiday'].iloc[0],
        'events': summary['events'],
        'arrivals': int(group['direction'].eq('arrival').sum()),
        'departures': int(group['direction'].eq('departure').sum()),
        'known': summary['known'],
        'unknown': summary['unknown'],
        'cancelled': summary['cancelled'],
        'cancellation_pct': summary['cancellation_pct'],
        'eligible_gap_departures': len(day_eligible),
        'gap60_count': extreme,
        'gap60_pct': pct(extreme, len(day_eligible)),
        **{band: int(band_counts.get(band, 0)) for band in (
            'Morning (06–11)', 'Afternoon (12–16)', 'Evening (17–22)', 'Night/other'
        )},
    })
comparison = pd.DataFrame(comparison_rows)
print('Calendar make-up workdays: 2026-09-20 and 2026-10-10')
print('Observed date range:', df['local_date'].min(), 'to', df['local_date'].max())
print('September 20 is outside the dataset and is not a zero-flight observation.')
print('\\nWeekend and adjusted-workday outcomes:')
print(comparison.to_string(index=False, formatters={
    'cancellation_pct': '{:.2f}%'.format,
    'gap60_pct': '{:.2f}%'.format,
}))

display(Image(filename=str(FIG / 'adjusted_workday.png')))

matched_saturday = comparison.loc[comparison['date'].isin(['2026-10-10', '2026-10-17'])]
hour_columns = ['Morning (06–11)', 'Afternoon (12–16)', 'Evening (17–22)', 'Night/other']
print('\\nRecorded event counts by local-hour band: October 10 vs October 17')
print(matched_saturday[['date', *hour_columns]].to_string(index=False))
display(Image(filename=str(FIG / 'adjusted_workday_hours.png')))"""),
        nbformat.v4.new_markdown_cell("""## Conclusions

The observed October 10 adjusted workday had fewer recorded events and a higher cancellation rate than October 17, the closest ordinary-Saturday comparison. Under the timestamp assumption used in this analysis, its eligible departure subset had no delays ≥60 minutes, compared with 14 of 384 on October 17. This contrast is descriptive only: the dates differ in schedule and operating conditions, and event coverage is not a verified measure of scheduled capacity. Only one of the two calendar make-up workdays falls within the dataset. The findings cannot establish an adjusted-workday effect. A stronger investigation requires data for September 20, multiple comparable workdays and years, complete schedule coverage, and relevant operational and demand data.""")
    ]
    for i, cell in enumerate(nb.cells):
        cell.id = f"cell-{i:03d}"
    path = OUT / "sha_national_day_final.ipynb"
    nbformat.write(nb, path)
    return path


def build_report(res):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.left_margin = sec.right_margin = Mm(24)
    sec.top_margin, sec.bottom_margin = Mm(22), Mm(20)
    normal = doc.styles['Normal']
    normal.font.name = 'Times New Roman'; normal.font.size = Pt(10.5)
    normal.paragraph_format.line_spacing = 1.45
    normal.paragraph_format.space_after = Pt(7)
    normal.paragraph_format.widow_control = True
    for name,size,color in [('Title',24,'17324D'),('Heading 1',15,'17324D'),('Heading 2',12,'285A7A')]:
        style=doc.styles[name]; style.font.name='Times New Roman'; style.font.size=Pt(size)
        style.font.bold=True; style.font.color.rgb=RGBColor.from_string(color)
        style.paragraph_format.keep_with_next=True
    doc.styles['Caption'].font.name='Times New Roman'; doc.styles['Caption'].font.size=Pt(9)
    footer=sec.footer.paragraphs[0]; footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
    field_page(footer)
    body=[]

    def para(text):
        p=doc.add_paragraph(text); p.alignment=WD_ALIGN_PARAGRAPH.JUSTIFY; body.append(text); return p
    def heading(text,level=1):
        doc.add_heading(text,level=level); body.append(text)
    def picture(name,caption):
        p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(FIG/name),width=Mm(157))
        doc.add_paragraph(caption,style='Caption')

    doc.add_paragraph('\n'*8)
    title=doc.add_paragraph("Calendar, Disruption and the\nAdjusted Workday",style='Title'); title.alignment=WD_ALIGN_PARAGRAPH.CENTER
    sub=doc.add_paragraph("A three-question research report on flight-service patterns around China’s 2026 National Day holiday",style='Subtitle'); sub.alignment=WD_ALIGN_PARAGRAPH.CENTER
    for item in ['Shanghai Hongqiao International Airport (SHA)', 'Study period: 22 September–22 October 2026', 'Student: [Add your name]', 'Student number: [Add number]', 'Course: [Add course name and code]', 'Instructor: [Add instructor name]', 'Submission date: [Add date]']:
        p=doc.add_paragraph(item); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()

    heading('Abstract'); para('This report examines three approved research questions using 23,705 flight-event records from Shanghai Hongqiao Airport (SHA) spanning 22 September to 22 October 2026. It compares three equal seven-day calendar periods around the National Day holiday, investigates concentration in cancellations and departures delayed by at least 60 minutes, and examines the October 10 adjusted workday in calendar context. The 2026 calendar identifies September 20 and October 10 as National Day make-up workdays, but September 20 is outside the dataset. October 10 had 682 event records (342 arrivals and 340 departures), 30 cancellations among 680 known-status records (4.41%), and no qualifying delay among 323 eligible departures. The closest ordinary-Saturday comparison, October 17, had 775 event records, 8 cancellations among 775 known-status records (1.03%), and 14 delays of at least 60 minutes among 384 eligible departures (3.65%). October 10 therefore had 12.0% fewer recorded events and a 3.38-percentage-point higher cancellation rate than October 17, while its ≥60-minute delay proportion was lower. These are date-specific descriptions, not an adjusted-workday effect. For the timestamp analysis, scheduled and actual departure timestamps are assumed accurate and semantically valid; event coverage does not establish complete scheduled-flight coverage or passenger demand. Only one of the two make-up workdays falls within the observed period. The analysis demonstrates why flight-service comparisons should identify public holidays and adjusted workdays separately, while further data are needed to explain these differences.')
    heading('Keywords'); para('National Day holiday; flight-service patterns; cancellation; departure delay; adjusted workday; Shanghai Hongqiao Airport')
    heading('1. Introduction and problem statement')
    para('Transport planning depends on calendar context as well as averages. In China, public holidays may be linked to ordinary weekends and adjusted workdays, creating official dates that do not follow the usual weekday–weekend distinction. A Saturday declared an adjusted workday can be a work schedule rather than an ordinary weekend. At the same time, a weekly average can conceal sharp changes on individual dates or hours. Flight-event records provide useful evidence about scheduled service and recorded status, but their interpretation requires precise definitions and limits. This report uses three approved questions to examine the relationship between calendar phases, disruption indicators, and adjusted-workday classification in one airport dataset.')
    para('The policy motivation is operational, not passenger-oriented. If cancellation rates or delays of at least 60 minutes cluster on specific dates or hours, airport managers may gain a more targeted basis for monitoring. They cannot infer from those patterns alone that a public holiday caused disruption, or that staffing, weather, congestion, or airline operations explain the pattern. The dataset also does not include passenger counts, route demand, weather, runway operations, or aircraft rotation. The analysis treats the scheduled and actual departure timestamps as accurate for measuring delay, but event counts do not measure passenger demand.')
    heading('1.1 Literature review')
    para('Air transport research commonly conceptualizes delays as network outcomes that emerge from interactions among schedules, airport resources, aircraft rotations, and downstream recovery. Pyrgiotis, Malone, and Odoni (2013) model delay propagation in large airport networks and show that a late arrival or departure can affect later flights. This is relevant to interpreting a dataset that contains both cancellation status and time-paired records, because an aggregate punctuality measure does not identify whether disruption began at SHA or was carried forward from another flight or airport. The present data contain no preceding flight, crew, airport, aircraft-rotation, or weather identifiers, so propagation cannot be tested.')
    para('Mayer and Sinai (2003) study network effects and congestion externalities from hubbing. Their analysis demonstrates that scheduled concentration can create passenger convenience and also operational trade-offs. Their concept helps explain why service counts at a particular hour or airport should not automatically be interpreted as demand or congestion. A schedule bank may reflect passenger connection demand, airline hub design, infrastructure constraints, or operational recovery. In this project, hourly schedule bands are therefore used only to describe measured flight-event timing. No inference is made about the mechanism that produced an observed profile.')
    para('Chen and Lin (2021) emphasize airport, route, and network perspectives when studying East Asian flight delays. Their framework supports this report’s decision not to rely on a single airport-wide average. The route and hour of a flight can be associated with scheduling patterns and the likelihood of a particular outcome. Yet this report has an even narrower question: concentration in descriptive indicators across dates and scheduled hours. A full route-level causal model would require aircraft rotation, turnaround, weather, traffic, and carrier or operational detail absent from the supplied file.')
    para('For distributions, a mean may obscure tail risk. Koenker and Bassett (1978) established quantile methods for understanding relationships across the distribution, and their insight applies descriptively here: the 60-minute threshold distinguishes a small proportion of long delays from shorter observed intervals. The threshold is not a universal regulatory definition of delay; it is a transparent analytical cut-off for identifying high-magnitude date/hour patterns. A proportion above that threshold is therefore reported alongside the eligible denominator.')
    para('Research on holiday travel also cautions against assuming that conventional calendar categories capture Chinese work schedules. Public-holiday administration and adjusted workdays shift ordinary weekend and weekday labels. Official guidance identifies 1–7 October 2026 as National Day holiday, 25–27 September as Mid-Autumn Festival holiday, and 10 October as an adjusted workday (General Office of the State Council, 2025). This official calendar framework supports the central methodological concern: a chronological before/after comparison cannot be calendar-neutral unless the calendar composition is described.')
    para('Finally, inference at the wrong unit can create false precision. Cameron and Miller (2015) explain that clustered observations require dependency-aware sampling. Flight records on the same date may share weather or network conditions, while records in a one-airport dataset are not independent replications of a national transport system. Accordingly, this report uses simple descriptive denominators and does not claim significance tests or confidence intervals for causal effects. Date and hour patterns are reviewed explicitly, and the strongest conclusions are limited to within-dataset associations.')
    heading('1.2 Scope, contribution and research questions')
    para('This report contributes a calendar-aware, exploratory synthesis of 23,705 records at one airport. It combines (1) equal-length period comparisons, (2) daily and hourly disruption indicators, and (3) a carefully bounded adjusted-workday case study. For this analysis, the scheduled and actual departure timestamps are assumed to be accurate; delays of at least 60 minutes are counted using that assumption. This approach adds value beyond a simple cancellation average because it identifies whether apparent differences occur consistently across dates or appear concentrated in a few unusual observations.')
    for text in ['**RQ1.** How did flight-service volume and cancellation rates vary before, during, and after China’s National Day holiday? The analysis compares equal-length periods and daily trends, accounts for Mid-Autumn public holidays in the pre-holiday period, and reports missing status data.', '**RQ2.** Were cancellation rates and departures delayed by at least 60 minutes concentrated on particular dates or departure hours? The analysis identifies unusual dates and compares morning, afternoon, and evening patterns using the 60-minute delay threshold.', '**RQ3.** How did flight-event volume, cancellation rates, and departures delayed by at least 60 minutes on the 10 October adjusted workday compare with weekend dates? The analysis distinguishes public-holiday weekend dates and uses 17 October as the closest ordinary-Saturday reference, without treating one date as a general adjusted-workday effect.']:
        para(text)
    heading('2. Methods')
    heading('2.1 Data and unit of analysis')
    para('The source is `sha_master.csv`, supplied for this project. It contains 23,705 unique `event_id` records covering 31 local dates from 22 September through 22 October 2026. Every record describes either an arrival or departure event. Available fields include local date and hour, direction, route, status display, weekday, public-holiday classification, adjusted-workday flag, calendar-day type, scheduled departure and arrival timestamps, and actual departure or landed-status timestamps. The unit of observation is a flight-event record, not a passenger, journey, aircraft movement, or unique flight rotation. The period results include both directions. The delay analysis uses departure records only because scheduled and actual departure timestamps define that outcome.')
    heading('2.2 Calendar period construction')
    para('The National Day period is 1–7 October 2026. The equal-length pre-holiday period is 24–30 September, and the post-holiday period is 8–14 October. Each period has seven dates and begins on a Thursday. The official Mid-Autumn public-holiday dates 25–27 September are within the pre-holiday window. 10 October, included in the post-holiday window, is an adjusted workday. This means period averages are comparable in length but not calendar-homogeneous. The analysis reports period composition rather than describing the three windows as equivalent control, treatment, and post periods.')
    heading('2.3 Status and cancellation measures')
    para('The `status_display` field contains the source-reported flight-progress or outcome label for a flight event, such as `Canceled`, `Landed` followed by a time, `Estimated departure` followed by a time, or `Diverted to` followed by an airport code. It is a displayed flight status, not a separate assessment of whether the record itself is valid. A status was treated as known when this field was neither blank nor `unknown`. A record was cancelled when the status was exactly `canceled` after text trimming and case normalization. The cancellation rate for a date or period is cancelled known-status records divided by all known-status records, expressed as a percentage. It is a per-record share, not a time-based rate. Blank or unknown records were excluded from the numerator and denominator. This denominator is essential because a missing-status record cannot be assumed cancelled or completed. Daily cancellation figures also allow assessment of within-period variation.')
    heading('2.4 Departure delays')
    para('Departure delay was calculated as actual departure UTC minus scheduled departure UTC. The project retained only known-status, non-cancelled departure records with complete scheduled and actual departure timestamps. Missing or unusable records were excluded and counted. For this analysis, the scheduled and actual timestamps are assumed accurate and semantically valid, although the supplied `timing_semantics_verified` field is false. A delay was classified as long when it was at least 60 minutes. This is a pre-specified analytical threshold, not a sector-specific regulatory definition.')
    para('For hour analysis, scheduled local departure hour was grouped into morning (06–11), afternoon (12–16), evening (17–22), and night/other (23–05). These bands make the three requested daytime phases comparable and retain the remaining sparse hours explicitly. Counts and proportions were calculated within each band. Date concentration was summarized using the eligible departures on each date and the proportion reaching the 60-minute threshold. Cancellation concentration was summarized by known-status denominators on individual dates.')
    heading('2.5 Adjusted-workday and ordinary-weekend comparison')
    para('Calendar-day type is taken from the supplied dataset and reconciled with its adjusted-workday flag. The 2026 calendar marks 20 September and 10 October as National Day make-up workdays. The dataset begins on 22 September, so 20 September is not observed and must not be interpreted as a zero-flight date. 10 October is the only adjusted workday represented. For context, the comparison table reports all weekend dates in the dataset and separately identifies the public-holiday weekends on 26–27 September and 3–4 October. The Saturday 17 October is the closest available ordinary-Saturday reference for 10 October, but neither date is a repeated or controlled observation.')
    heading('2.6 Software and reproducibility')
    para('The report statistics and notebook analysis were reproduced from `sha_master.csv`; the notebook uses pandas for loading, grouping, and summaries. Figures are generated with matplotlib by `scripts/build_word_final_project.py`. Validation checks ensure that event IDs are unique, all three periods contain every required date, and each calculated departure delay agrees with `timing_difference_minutes`. Outputs include this Word report, its figures, and machine-readable summary values. Findings are exploratory and are not suitable for population or causal inference.')

    heading('3. Results')
    heading('3.1 RQ1: Flight volume and cancellation rate')
    periods=res['periods']
    add_table(doc,'Table 1. Equal-length National Day period comparison.', ['Phase','Dates','Events','Events/day','Known status','Unknown status','Cancelled','Cancellation %'], [[p['label'],f"{p['start']} to {p['end']}",f"{p['events']:,.0f}",f"{p['per_day']:.1f}",f"{p['known']:,.0f}",f"{p['unknown']:,.0f}",f"{p['canceled']:,.0f}",f"{p['cancel_pct']:.2f}%"] for p in periods])
    para('National Day period event volume was close to the pre-holiday mean: 5,381 records over seven days, or 768.7 per day, compared with 5,351 records, or 764.4 per day, before the holiday. The post-holiday period had 5,126 records, or 732.3 per day. Thus, holiday-period volume was not unusually high or low relative to the preceding period, but it was lower than the pre-holiday rate and 4.7% below the pre-holiday average on a per-day basis.')
    para('Cancellation rate showed a larger difference. The known-status denominator was 5,348 before, 5,380 during, and 5,097 after. The period rates were 3.74%, 1.91%, and 2.41%, respectively. The rate increased from 1.91% during the holiday to 2.41% afterwards, but remained below the pre-holiday level. Missing status was concentrated in the post-holiday period: 29 of 5,126 records had blank or unknown status, compared with three before and one during the holiday. This missingness changes the denominator and should prevent a literal comparison of raw cancellation counts.')
    para('Daily patterns reveal why period averages are insufficient. Figure 1 plots event volume and cancellation rate together across all study dates. Before the holiday, cancellation rate peaked on 26 September at 6.24% and 29 September at 8.15%. On 1 October, the first National Day date, the cancellation rate was only 0.38%; it rose to 4.95% on 3 October and fell to zero on 7 October. The post-holiday period also varied sharply: 5.46% on 8 October compared with 0.40% on 12 October. These daily changes show that the National Day result is not a stable plateau but a sequence of individually different dates.')
    picture('daily_trends.png','Figure 1. Daily flight-event records and known-status cancellation rates, 22 September–22 October 2026.')
    heading('3.2 RQ2: Concentration of cancellations and long delays')
    para('The eligible departure-delay denominator was 11,560 known-status, non-cancelled departures with complete scheduled and actual departure timestamps. This denominator differs from the entire dataset because cancelled and unknown-status records were removed, and 10 departure records lacked complete paired departure timestamps. A total of 514 departures had a delay of at least 60 minutes, equal to 4.45% of eligible records.')
    add_table(doc,'Table 2. Dates with the largest proportions of departures delayed by at least 60 minutes.', ['Date','Eligible departures','Delays ≥60 min','Delay ≥60 min %'], [[d['date'],d['records'],d['extreme_n'],f"{d['extreme_pct']:.2f}%"] for d in res['extreme_dates']])
    para('Long delays were unevenly distributed. 19 October had 99 delays of at least 60 minutes among 380 eligible departures (26.05%), the largest proportion in the date summary. 26 September had 75 among 335 (22.39%), and 2 October had 35 among 367 (9.54%). These three dates alone represented 209 of 514 long delays. The contrast between 19 October and the overall 4.45% rate was large, while 24 and 18 September were not in the highest date concentration due to lower eligible denominators and counts. Concentration could reflect operational conditions, schedule construction, or unobserved network effects.')
    para('Figure 2 makes the date pattern directly visible. The plot identifies only date-level rank; it does not provide a statistical test or imply that 19 October and 26 September are recurring risk dates. Both dates are one-off observations in a short 31-date sample. They are plausible monitoring targets for future collection of additional operational data, not established causal outliers.')
    picture('extreme_dates.png','Figure 2. Highest date-level proportions of departures delayed by at least 60 minutes.')
    add_table(doc,'Table 3. Cancellation rate on the five highest-cancellation dates.', ['Date','Known status','Cancelled','Cancellation %'], [[d['date'],d['known'],d['canceled'],f"{d['cancel_pct']:.2f}%"] for d in res['top_cancellation_dates']])
    para('The top cancellation date was 29 September, with 62 cancellations among 761 known-status records (8.15%). 26 September had 45 of 721 (6.24%), 28 September had 46 of 751 (6.13%), 8 October had 42 of 769 (5.46%), and 3 October had 37 of 748 (4.95%). The period-level holiday rate does not obscure these spikes. However, cancellations and long delays did not peak on precisely the same dates. 26 September appeared among both highest-cancellation and highest-delay dates, but 29 September and 19 October did not. This supports treating cancellation and departure delay as complementary outcomes rather than one general disruption construct.')
    hour_order={'Morning':0,'Afternoon':1,'Evening':2,'Night/other':3}
    add_table(doc,'Table 4. Departures delayed by at least 60 minutes by scheduled local-hour band.', ['Hour band','Eligible departures','Delays ≥60 min','Delay ≥60 min %'], [[h['hour_band'],h['records'],h['extreme_n'],f"{h['extreme_pct']:.2f}%"] for h in sorted(res['hourly_gaps'],key=lambda x:hour_order[x['hour_band'].split(' ')[0]])])
    para('The four daytime bands showed a clear descriptive gradient in long-delay proportion. Morning departures had 110 delays of at least 60 minutes among 4,531 eligible records (2.43%). Afternoon departures had 170 among 3,529 (4.82%), and evening departures had 233 among 3,406 (6.84%). The residual night/other band had only 94 records and one long delay (1.06%), too sparse for a stable comparison. The morning-to-evening increase was 4.41 percentage points. It does not mean that evening departures are causally more delayed; evening schedules may differ in route mix, airline, aircraft rotation, or network congestion.')
    heading('3.3 RQ3: October 10 adjusted-workday case study')
    comparison=res['adjusted_workday_comparison']
    def calendar_label(day):
        if day['adjusted_workday']:
            return f"{day['date']} / adjusted workday"
        if day['public_holiday'] != 'none':
            return f"{day['date']} / {day['public_holiday'].replace('_', ' ')} holiday ({day['weekday']})"
        return f"{day['date']} / ordinary {day['weekday']}"
    add_table(
        doc,
        'Table 5. Flight-event outcomes on the adjusted workday and weekend dates, separated by calendar classification.',
        ['Date / classification','Events (arrivals / departures)','Known / unknown','Cancelled / rate','Departures ≥60 min late (n/N, %)'],
        [[
            calendar_label(d),
            f"{d['events']} ({d['arrivals']} / {d['departures']})",
            f"{d['known']} / {d['unknown']}",
            f"{d['canceled']} / {d['cancel_pct']:.2f}%",
            f"{d['gap60_count']}/{d['eligible_gap_departures']} ({d['gap60_pct']:.2f}%)",
        ] for d in comparison],
    )
    hour_order=['Morning (06-11)','Afternoon (12-16)','Evening (17-22)','Night/other (23-05)']
    add_table(
        doc,
        'Table 6. Recorded event counts by local-hour band on weekend and adjusted-workday dates.',
        ['Date / classification','Morning 06–11','Afternoon 12–16','Evening 17–22','Night/other 23–05'],
        [[calendar_label(d)]+[d['hour_band_events'].get(band,0) for band in hour_order] for d in comparison],
    )
    oct10=next(d for d in comparison if d['date']=='2026-10-10')
    oct17=next(d for d in comparison if d['date']=='2026-10-17')
    volume_change=100*(oct10['events']/oct17['events']-1)
    cancellation_difference=oct10['cancel_pct']-oct17['cancel_pct']
    para(f"October 10 had {oct10['events']} recorded events ({oct10['arrivals']} arrivals and {oct10['departures']} departures), compared with {oct17['events']} ({oct17['arrivals']} arrivals and {oct17['departures']} departures) on Saturday 17 October. The October 10 count was {abs(volume_change):.1f}% lower. Its cancellation rate was {oct10['canceled']}/{oct10['known']} ({oct10['cancel_pct']:.2f}%), versus {oct17['canceled']}/{oct17['known']} ({oct17['cancel_pct']:.2f}%) on 17 October, a difference of {cancellation_difference:.2f} percentage points. Under the timestamp assumption used here, {oct10['gap60_count']} of {oct10['eligible_gap_departures']} eligible October 10 departures met the ≥60-minute delay threshold ({oct10['gap60_pct']:.2f}%); this does not mean there were no shorter delays. On October 17, {oct17['gap60_count']} of {oct17['eligible_gap_departures']} eligible departures met the threshold ({oct17['gap60_pct']:.2f}%).")
    para('The remaining ordinary weekends provide context rather than a pooled control: 11 October had 718 events and a 1.54% cancellation rate, while 18 October had 777 events and no cancellations among known-status records. Public-holiday weekends on 26–27 September and 3–4 October are labelled separately in Table 5 because they are not ordinary-weekend comparisons. Table 6 and Figure 4 show recorded local-hour profiles; these event counts do not establish complete scheduled capacity or passenger demand.')
    picture('adjusted_workday.png','Figure 3. Recorded volume by direction, cancellation rate, and ≥60-minute delay proportion on the adjusted workday and weekend dates; public-holiday weekends are identified separately.')
    picture('adjusted_workday_hours.png','Figure 4. Recorded flight-event counts by local-hour band on 10 and 17 October.')
    para('The 17 October comparison is particularly useful because it is also a Saturday and is classified as an ordinary weekend, but it remains only one other date. The lower recorded count and higher cancellation rate on 10 October may reflect specific schedules, route or airline mix, weather, network conditions, or data coverage. The lower observed long-delay proportion does not contradict the cancellation comparison: cancellation and departure-delay measures describe different outcomes and use different denominators. These descriptive differences cannot identify an adjusted-workday effect or its mechanism.')
    heading('4. Conclusions')
    para('The main answer to RQ1 is that flight-event volume was broadly stable across adjacent periods but cancellation rate was not. The pre-holiday period averaged 764.4 events per day and had 3.74% cancellations; the National Day period averaged 768.7 events and had 1.91%; and the post-holiday period averaged 732.3 events and had 2.41%. This apparent stability masks substantial within-period variation and missing-status concentration. The pre-holiday period included 25–27 September Mid-Autumn public holidays, and the post-holiday period included 10 October’s adjusted workday. Therefore, “before, during, and after” is chronological, not calendar-neutral.')
    para('For RQ2, the key finding is concentration rather than uniform disruption. One cancellation date, 29 September, reached 8.15%, and 19 October accounted for 26.05% of eligible departures delayed by at least 60 minutes. The long-delay proportion rose from 2.43% in the morning to 4.82% in the afternoon and 6.84% in the evening. These results support monitoring both unusual dates and scheduled-hour bands. They do not establish why the patterns occurred or whether they would recur. Cancellation and delay rankings are not identical, reinforcing that cancellation and delay outcomes should be reported separately.')
    para('For RQ3, the only observed adjusted workday, 10 October, had 682 recorded events and a 4.41% cancellation rate. Against the closest ordinary-Saturday comparison, 17 October, its recorded volume was 12.0% lower and its cancellation rate was 3.38 percentage points higher; 0 of 323 eligible departures met the ≥60-minute delay threshold (0.00%), compared with 14 of 384 (3.65%) on 17 October. This threshold result does not rule out shorter delays. The timestamp measure assumes the supplied scheduled and actual times are accurate, although their semantics are unverified. This contrast demonstrates that cancellation and delay outcomes need separate reporting and that weekday/weekend labels alone omit official calendar status. It does not show that the adjusted-workday designation caused any difference. September 20, the other National Day make-up workday, is outside the data window.')
    heading('4.1 Implications')
    para('Airport planners can use the findings as a prioritization list for monitoring and further data collection. Dates with elevated cancellation or long-delay indicators should be investigated using weather, airline operations, aircraft rotations, connection banks, runway availability, and passenger load. Hour bands should be monitored in the context of route and schedule mix. Calendar-aware planning should retain official-day classification and avoid treating a make-up workday simply as a weekend. This is particularly relevant for short pre/post holiday comparisons, where a small number of special calendar dates can influence aggregate results.')
    heading('4.2 Limitations')
    para('The data describe 31 dates and one airport. They cannot establish national, seasonal, or passenger-travel patterns. The calendar lists two National Day make-up workdays, but September 20 is outside the data window and only October 10 is observed. Each comparison is therefore a single-date description, not a replicated adjusted-workday sample. Recorded event volume does not establish complete scheduled-flight coverage or passenger demand. Post-holiday status completeness was lower than in the National Day window, and cancellation rates rely on records with known status. The delay analysis assumes the supplied scheduled and actual departure timestamps are accurate, although the source verification flag is false. The 60-minute threshold was created for this analysis rather than provided by an authoritative operational definition. No weather, demand, capacity, or network variables are available for mechanism tests. Repeated observations within dates are likely dependent. Consequently, no inferential claim or causal language is appropriate.')
    para('Several common interpretive risks remain. Flight-event count is not passenger demand. A cancellation rate is not the probability of any individual passenger being disrupted. A departure delayed by at least 60 minutes is not necessarily a “poor” operational outcome. A holiday comparison is not a controlled experiment. The study should therefore be used to develop monitoring hypotheses and collect better operational and passenger data, not to rank causes or justify policy in isolation.')
    heading('References')
    for ref in [
        'Cameron, A. C., & Miller, D. L. (2015). A practitioner’s guide to cluster-robust inference. Journal of Human Resources, 50(2), 317–372. https://doi.org/10.3368/jhr.50.2.317',
        'Chen, Y., & Lin, Y. (2021). Determinants of flight delays in East Asia: airport, route and network perspectives. Journal of Air Transport Management, 97, 102149.',
        'Koenker, R., & Bassett, G. (1978). Regression quantiles. Econometrica, 46(1), 33–50. https://doi.org/10.2307/1913643',
        'Mayer, C., & Sinai, T. (2003). Network effects, congestion externalities, and air traffic delays: Or why all delays are not evil. American Economic Review, 93(4), 1194–1215. https://doi.org/10.1257/000282803769206246',
        'Pyrgiotis, N., Malone, K. M., & Odoni, A. (2013). Modelling delay propagation within an airport network. Transportation Research Part C: Emerging Technologies, 27, 60–75. https://doi.org/10.1016/j.trc.2012.10.009',
        'General Office of the State Council of the People’s Republic of China. (2025). Notice on the arrangement of some public holidays in 2026 (Guo Ban Fa Ming Dian [2025] No. 7). https://www.gov.cn/zhengce/content/202511/content_7047090.htm',
    ]:
        para(ref)

    # Count the main text approximately; title and references are excluded.
    ref_start='References'
    main_words=sum(len(re.findall(r"\b[\w’'-]+\b",x)) for x in body[:body.index(ref_start)])
    note=doc.add_paragraph()
    note.alignment=WD_ALIGN_PARAGRAPH.CENTER
    note.add_run(f"Main-text word count (excluding title page and references): approximately {main_words:,}").italic=True
    path=OUT/'sha_national_day_final_report.docx'
    doc.save(path)
    return path,main_words


def main():
    OUT.mkdir(exist_ok=True)
    rows=read(); res=analysis(rows)
    (OUT/'sha_national_day_final_results.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
    build_figures(res)
    notebook=build_notebook(res)
    report,words=build_report(res)
    if not 3000 <= words <= 6000:
        raise RuntimeError(f'Main-text word count is outside requirement: {words}')
    print(report)
    print(notebook)
    print(f'Main-text words: {words}')

if __name__=='__main__': main()
