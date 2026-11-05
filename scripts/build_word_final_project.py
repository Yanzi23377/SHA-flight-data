"""Build the three-question Word report and documented Jupyter notebook."""
from pathlib import Path
import json
import re

import nbformat
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

from build_final_project import ROOT, read, analysis

OUT = ROOT / "final_project_word"
FIG = ROOT / "final_project" / "figures"


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


def build_notebook(res):
    nb = nbformat.v4.new_notebook(metadata={"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}})
    nb.cells = [
        nbformat.v4.new_markdown_cell("""# SHA Flight-Service Patterns Around China's 2026 National Day Holiday

**Approved proposal questions:**
1. How did flight-service volume and cancellation proportions vary before, during, and after the holiday?
2. Were cancellations and extreme recorded departure-time gaps concentrated on particular dates or departure hours?
3. What does the October 10 adjusted workday reveal about weekday/weekend labels?

This notebook is documented and reproducible. It uses the supplied `sha_master.csv`. A ≥60-minute scheduled-to-actual departure gap is a pre-defined recorded timestamp feature, not a verified operational delay.

**Scope and data boundary:** The unit of observation is a flight-event record. This is not a passenger-demand, congestion, emissions, or causal study."""),
        nbformat.v4.new_code_cell("""from pathlib import Path
import csv
from collections import defaultdict
from datetime import date, timedelta, datetime

DATA = Path('sha_master.csv')
if not DATA.exists():
    DATA = Path('..') / 'sha_master.csv'
with DATA.open(newline='', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
for r in rows:
    r['_date'] = date.fromisoformat(r['local_date'])
    r['_hour'] = int(r['local_hour'])
print(f'{len(rows):,} records; {len({r["local_date"] for r in rows})} dates')
print(f'Unique event IDs: {len({r["event_id"] for r in rows})}')"""),
        nbformat.v4.new_markdown_cell("""## Methods and definitions

- **Known status:** status is neither blank nor `unknown`.
- **Cancellation proportion:** cancellations ÷ known-status records.
- **Period comparison:** three 7-day windows with all 7 dates present.
- **Extreme recorded gap:** `actual_departure_utc - scheduled_departure_utc >= 60` minutes among known-status, non-cancelled departures with both timestamps.
- **Hour bands:** morning 06–11, afternoon 12–16, evening 17–22, and night/other 23–05.
- The source records `timing_semantics_verified=false` throughout, so timestamp differences are not called operational delays."""),
        nbformat.v4.new_code_cell("""def known(r):
    return r['status_display'].strip().lower() not in ('', 'unknown')
def cancelled(r):
    return r['status_display'].strip().lower() == 'canceled'
def pct(n,d):
    return 100*n/d if d else 0

def summarize(rs):
    k = [r for r in rs if known(r)]
    c = sum(cancelled(r) for r in k)
    return {'events':len(rs), 'known':len(k), 'unknown':len(rs)-len(k), 'cancelled':c,
            'cancellation_pct':pct(c,len(k))}

holiday = date(2026,10,1)
periods = [('Pre-holiday', holiday-timedelta(days=7), holiday-timedelta(days=1)),
           ('National Day', holiday, holiday+timedelta(days=6)),
           ('Post-holiday', holiday+timedelta(days=7), holiday+timedelta(days=13))]
for label,start,end in periods:
    subset=[r for r in rows if start <= r['_date'] <= end]
    s=summarize(subset)
    print(label, start, end, s, f"events/day={len(subset)/7:.1f}")"""),
        nbformat.v4.new_markdown_cell("""## RQ1 — Calendar phase and daily trend

The period table is intentionally supplemented with daily values. Period averages can conceal a high-cancellation date within a generally low-cancellation window. The following chart plots both flight-event volume and cancellation proportion for every available date."""),
        nbformat.v4.new_code_cell("""import matplotlib.pyplot as plt
from matplotlib.dates import DayLocator, DateFormatter
from collections import defaultdict
by_date=defaultdict(list)
for r in rows: by_date[r['_date']].append(r)
daily=[(d,summarize(rs)) for d,rs in sorted(by_date.items())]
fig,ax=plt.subplots(2,1,figsize=(9,6.5),sharex=True)
dates=[d for d,_ in daily]
ax[0].plot(dates,[s['events'] for d,s in daily],marker='o',ms=3)
ax[0].set_ylabel('Flight events'); ax[0].set_title('Daily flight-event volume')
ax[1].plot(dates,[s['cancellation_pct'] for d,s in daily],marker='o',ms=3,color='#e07a32')
ax[1].axvspan(holiday, holiday+timedelta(days=7), color='#e07a32', alpha=.12)
ax[1].set_ylabel('Cancellation (%)'); ax[1].set_xlabel('Local date')
ax[1].xaxis.set_major_locator(DayLocator(interval=3)); ax[1].xaxis.set_major_formatter(DateFormatter('%b %-d'))
fig.tight_layout(); plt.show()
print('Calendar qualifiers: 25–27 Sep = Mid-Autumn public holiday; 1–7 Oct = National Day holiday; 10 Oct = adjusted workday.')"""),
        nbformat.v4.new_markdown_cell("""## RQ2 — Concentration on dates and hours

The numerator is a date/hour count of **recorded** extreme gaps. It is compared with the eligible known-status, non-cancelled departure denominator. Cancellations are analysed separately and are not eligible for departure-gap calculation."""),
        nbformat.v4.new_code_cell("""from datetime import datetime

def parse_dt(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))
eligible=[]
missing=0
for r in rows:
    if r['direction']!='departure' or not known(r) or cancelled(r):
        continue
    if not r['scheduled_departure_utc'] or not r['actual_departure_utc']:
        missing += 1; continue
    gap=(parse_dt(r['actual_departure_utc'])-parse_dt(r['scheduled_departure_utc'])).total_seconds()/60
    eligible.append((r,gap))

date_ext=[]
for d in sorted({r['_date'] for r,g in eligible}):
    gs=[g for r,g in eligible if r['_date']==d]
    date_ext.append((d,len(gs),sum(g>=60 for g in gs),pct(sum(g>=60 for g in gs),len(gs))))
print('eligible',len(eligible),'missing',missing,'extreme',sum(g>=60 for r,g in eligible))
print('Top date rows:',sorted(date_ext,key=lambda x:(-x[3],-x[2]))[:5])

bands=defaultdict(list)
for r,g in eligible:
    h=r['_hour']; band='Morning (06–11)' if 6<=h<=11 else ('Afternoon (12–16)' if 12<=h<=16 else ('Evening (17–22)' if 17<=h<=22 else 'Night/other'))
    bands[band].append(g)
for band,gs in sorted(bands.items()):
    print(band, 'n=',len(gs),'extreme=',sum(g>=60 for g in gs),'pct=',round(pct(sum(g>=60 for g in gs),len(gs)),2))"""),
        nbformat.v4.new_markdown_cell("""The date-level view is not a test of recurring causation. October 10 is examined separately because ordinary weekday/weekend labels are not sufficient descriptions in China's adjusted-workday calendar."""),
        nbformat.v4.new_code_cell("""def cancellation_table(rs):
    s=summarize(rs)
    print(s)
    return s

print('Top cancellation dates')
top=sorted(daily,key=lambda ds:(-ds[1]['cancellation_pct'],ds[0].isoformat()))[:5]
for d,s in top:
    print(d.isoformat(), s)

print('October 10 adjusted workday')
cancellation_table([r for r in rows if r['_date']==date(2026,10,10)])
print('Ordinary weekends')
for d,s in daily:
    r=by_date[d][0]
    if r['calendar_day_type']=='weekend':
        print(d.isoformat(),s)"""),
        nbformat.v4.new_markdown_cell("""## RQ3 — Adjusted workday case study

October 10 was officially a Saturday adjusted workday. There is only one adjusted workday in the dataset, and exactly three ordinary weekend dates. Therefore, all apparent contrasts are observations about these particular dates—not estimates of a general adjusted-workday effect."""),
        nbformat.v4.new_code_cell("""adjusted = summarize([r for r in rows if r['_date']==date(2026,10,10)])
ordinary = [(d,s) for d,s in daily if by_date[d][0]['calendar_day_type']=='weekend']
labels=['10 Oct\\nadjusted']+[d.strftime('%d %b')+'\\nweekend' for d,s in ordinary]
values=[adjusted['cancellation_pct']]+[s['cancellation_pct'] for d,s in ordinary]
fig,ax=plt.subplots(figsize=(8,4))
ax.bar(labels,values,color=['#be4b48','#2878b5','#2878b5','#2878b5'])
ax.set_ylabel('Cancellation (%)'); ax.set_title('October 10 compared with ordinary weekend dates')
ax.grid(axis='y',alpha=.25); fig.tight_layout(); plt.show()
print('Events:', adjusted['events'], '| known:', adjusted['known'], '| cancelled:', adjusted['cancelled'], '| rate:', adjusted['cancellation_pct'])"""),
        nbformat.v4.new_markdown_cell("""## Conclusions

The notebook reproduces the three approved questions from the source CSV. Period comparisons show that calendar status is an important qualifier. Cancellation and extreme-gap indicators are concentrated in specific dates and tend to differ across hour bands. The October 10 result is consistent with the conclusion that conventional weekday/weekend labels omit make-up workdays, but it cannot identify a causal or general effect. Remaining analysis should combine this exploratory evidence with passenger demand, operational records, weather, and more years of airport data.""")
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

    heading('Abstract'); para('This report examines three approved research questions using 23,705 flight-event records from Shanghai Hongqiao Airport (SHA) spanning 22 September to 22 October 2026. It compares three equal seven-day calendar periods around the National Day holiday, investigates concentration in cancellations and extreme recorded departure timestamp gaps, and interprets one adjusted workday relative to the three ordinary weekend dates available in the dataset. Pre-holiday records cover 24–30 September, including Mid-Autumn public holidays on 25–27 September. The National Day period covers 1–7 October. Post-holiday records cover 8–14 October and include Saturday 10 October, officially an adjusted workday. Event volume per day was 764.4 before, 768.7 during, and 732.3 after the holiday. Known-status cancellation proportions were 3.74%, 1.91%, and 2.41%, respectively. Among 11,560 known-status, non-cancelled departures with complete departure timestamps, 514 records (4.45%) had a gap of at least 60 minutes. Extreme gaps were highly concentrated: 99 of 380 eligible departures on 19 October and 75 of 335 on 26 September met the threshold. Across scheduled-hour bands, the rate increased from 2.43% in the morning to 4.82% in the afternoon and 6.84% in the evening. October 10 had 682 event records and 30 cancellations among 680 known-status records (4.41%), above the 1.54%, 1.03%, and 0.00% rates on the three ordinary weekend dates. These findings are descriptive. The timestamp semantics are unverified, the data do not measure passenger demand or congestion, and one airport, one year, and one date for adjusted workdays cannot support causal or general calendar effects. The analysis nevertheless demonstrates that a flight-service calendar should distinguish public holidays and make-up workdays rather than treat date labels as ordinary weekdays or weekends.')
    heading('Keywords'); para('National Day holiday; flight-service patterns; cancellation; timestamp gap; adjusted workday; Shanghai Hongqiao Airport')
    heading('1. Introduction and problem statement')
    para('Transport planning depends on calendar context as well as averages. In China, public holidays may be linked to ordinary weekends and adjusted workdays, creating official dates that do not follow the usual weekday–weekend distinction. A Saturday declared an adjusted workday can be a work schedule rather than an ordinary weekend. At the same time, a weekly average can conceal sharp changes on individual dates or hours. Flight-event records provide useful evidence about scheduled service and recorded status, but their interpretation requires precise definitions and limits. This report uses three approved questions to examine the relationship between calendar phases, disruption indicators, and adjusted-workday classification in one airport dataset.')
    para('The policy motivation is operational, not passenger-oriented. If cancellation proportions or unusually large recorded timestamp gaps cluster on specific dates or hours, airport managers may gain a more targeted basis for monitoring. They cannot infer from those patterns alone that a public holiday caused disruption, or that staffing, weather, congestion, or airline operations explain the pattern. The dataset also does not include passenger counts, delay verification, route demand, weather, runway operations, or aircraft rotation. The report therefore uses the terms “flight-service volume” and “recorded timestamp gap” instead of passenger demand or verified delay.')
    heading('1.1 Literature review')
    para('Air transport research commonly conceptualizes delays as network outcomes that emerge from interactions among schedules, airport resources, aircraft rotations, and downstream recovery. Pyrgiotis, Malone, and Odoni (2013) model delay propagation in large airport networks and show that a late arrival or departure can affect later flights. This is relevant to interpreting a dataset that contains both cancellation status and time-paired records, because an aggregate punctuality measure does not identify whether disruption began at SHA or was carried forward from another flight or airport. The present data contain no preceding flight, crew, airport, aircraft-rotation, or weather identifiers, so propagation cannot be tested.')
    para('Mayer and Sinai (2003) study network effects and congestion externalities from hubbing. Their analysis demonstrates that scheduled concentration can create passenger convenience and also operational trade-offs. Their concept helps explain why service counts at a particular hour or airport should not automatically be interpreted as demand or congestion. A schedule bank may reflect passenger connection demand, airline hub design, infrastructure constraints, or operational recovery. In this project, hourly schedule bands are therefore used only to describe measured flight-event timing. No inference is made about the mechanism that produced an observed profile.')
    para('Chen and Lin (2021) emphasize airport, route, and network perspectives when studying East Asian flight delays. Their framework supports this report’s decision not to rely on a single airport-wide average. The route and hour of a flight can be associated with scheduling patterns and the likelihood of a particular outcome. Yet this report has an even narrower question: concentration in descriptive indicators across dates and scheduled hours. A full route-level causal model would require aircraft rotation, turnaround, weather, traffic, and carrier or operational detail absent from the supplied file.')
    para('For distributions, a mean may obscure tail risk. Koenker and Bassett (1978) established quantile methods for understanding relationships across the distribution, and their insight applies descriptively here: the 60-minute threshold distinguishes a small proportion of unusually large recorded gaps from typical observations. The threshold is not a universal definition of delay and is not validated against actual operations. It is a transparent exposure rule intended to identify high-magnitude date/hour features. A proportion above that threshold is therefore reported alongside the 60-minute threshold and its eligible denominator.')
    para('Research on holiday travel also cautions against assuming that conventional calendar categories capture Chinese work schedules. Public-holiday administration and adjusted workdays shift ordinary weekend and weekday labels. Official guidance identifies 1–7 October 2026 as National Day holiday, 25–27 September as Mid-Autumn Festival holiday, and 10 October as an adjusted workday (General Office of the State Council, 2025). This official calendar framework supports the central methodological concern: a chronological before/after comparison cannot be calendar-neutral unless the calendar composition is described.')
    para('Finally, inference at the wrong unit can create false precision. Cameron and Miller (2015) explain that clustered observations require dependency-aware sampling. Flight records on the same date may share weather or network conditions, while records in a one-airport dataset are not independent replications of a national transport system. Accordingly, this report uses simple descriptive denominators and does not claim significance tests or confidence intervals for causal effects. Date and hour patterns are reviewed explicitly, and the strongest conclusions are limited to within-dataset associations.')
    heading('1.2 Scope, contribution and research questions')
    para('This report contributes a calendar-aware, exploratory synthesis of 23,705 records at one airport. It combines (1) equal-length period comparisons, (2) daily and hourly disruption indicators, and (3) a carefully bounded adjusted-workday case study. The 60-minute threshold is distinguished from verified operational delay throughout. This approach adds value beyond a simple cancellation average because it identifies whether apparent differences occur consistently across dates or appear concentrated in a few unusual observations.')
    for text in ['**RQ1.** How did flight-service volume and cancellation proportions vary before, during, and after China’s National Day holiday? The analysis compares equal-length periods and daily trends, accounts for Mid-Autumn public holidays in the pre-holiday period, and reports missing status data.', '**RQ2.** Were cancellation proportions and extreme recorded departure-time gaps concentrated on particular dates or departure hours? The analysis identifies unusual dates and compares morning, afternoon, and evening patterns using the 60-minute threshold for extreme timestamp gaps.', '**RQ3.** What does the adjusted workday on 10 October reveal about the limitations of using weekday and weekend labels to interpret flight-service patterns in China? The analysis compares 10 October with the three ordinary weekend dates and treats the comparison as a single-date case study.']:
        para(text)
    heading('2. Methods')
    heading('2.1 Data and unit of analysis')
    para('The source is `sha_master.csv`, supplied for this project. It contains 23,705 unique `event_id` records covering 31 local dates from 22 September through 22 October 2026. Every record describes either an arrival or departure event. Available fields include local date and hour, direction, route, status display, weekday, public-holiday classification, adjusted-workday flag, calendar-day type, scheduled departure and arrival timestamps, and actual departure or landed-status timestamps. The unit of observation is a flight-event record, not a passenger, journey, aircraft movement, or unique flight rotation. The period results include both directions. The timestamp-gap analysis uses departure records only because scheduled and actual departure timestamps define that outcome.')
    heading('2.2 Calendar period construction')
    para('The National Day period is 1–7 October 2026. The equal-length pre-holiday period is 24–30 September, and the post-holiday period is 8–14 October. Each period has seven dates and begins on a Thursday. The official Mid-Autumn public-holiday dates 25–27 September are within the pre-holiday window. 10 October, included in the post-holiday window, is an adjusted workday. This means period averages are comparable in length but not calendar-homogeneous. The analysis reports period composition rather than describing the three windows as equivalent control, treatment, and post periods.')
    heading('2.3 Status and cancellation measures')
    para('Status was treated as known when `status_display` was neither blank nor `unknown`. A record was cancelled when status was exactly `canceled` after text trimming and case normalization. Cancellation proportion for a date or period equals cancelled known-status records divided by all known-status records. Blank or unknown records were excluded from the numerator and denominator. This denominator is essential because a missing-status record cannot be assumed cancelled or completed. Daily cancellation figures also allow assessment of within-period variation.')
    heading('2.4 Recorded timestamp gaps')
    para('The recorded departure gap was calculated as actual departure UTC minus scheduled departure UTC. The project retained only known-status, non-cancelled departure records with complete scheduled and actual departure timestamps. Missing or unusable records were excluded and counted. A gap was classified as extreme when it was at least 60 minutes. The chosen threshold is a pre-specified descriptive classification, not a sector-specific regulatory definition. It does not distinguish a data issue from an operational delay. The source marks `timing_semantics_verified=false` for every record. Therefore, all timestamp analysis is reported as “recorded” or “extreme recorded timing” and not as verified flight delay.')
    para('For hour analysis, scheduled local departure hour was grouped into morning (06–11), afternoon (12–16), evening (17–22), and night/other (23–05). These bands make the three requested daytime phases comparable and retain the remaining sparse hours explicitly. Counts and proportions were calculated within each band. Date concentration was summarized using the eligible departures on each date and the proportion reaching the 60-minute threshold. Cancellation concentration was summarized by known-status denominators on individual dates.')
    heading('2.5 Adjusted-workday and ordinary-weekend comparison')
    para('Calendar-day type is taken from the supplied dataset and reconciled with its adjusted-workday flag. 10 October is classified as an adjusted workday. The ordinary-weekend comparison uses 11, 17, and 18 October, the three dates classified as ordinary weekend. Event volume and known-status cancellation proportion are reported on each date. The result is intentionally a single-date, n-of-one case study. A difference cannot establish an adjusted-workday effect because the one date is confounded with seasonal, network, schedule, weather, and data-recording conditions. The ordinary-weekend comparison is used to illustrate why Saturday as a date label is insufficient, not to estimate a general effect.')
    heading('2.6 Software and reproducibility')
    para('Analysis was reproduced in Python using the standard library and matplotlib. The report and figures were generated from `sha_master.csv` by `scripts/build_word_final_project.py`. The accompanying Jupyter notebook is `sha_national_day_final.ipynb`. Validation checks ensure that event IDs are unique, all three periods contain every required date, and each timestamp gap agrees with `timing_difference_minutes`. Outputs include this Word report, its figures, and machine-readable summary values. Findings are exploratory and are not suitable for population or causal inference.')

    heading('3. Results')
    heading('3.1 RQ1: Flight volume and cancellation proportion')
    periods=res['periods']
    add_table(doc,'Table 1. Equal-length National Day period comparison.', ['Phase','Dates','Events','Events/day','Known status','Unknown status','Cancelled','Cancellation %'], [[p['label'],f"{p['start']} to {p['end']}",f"{p['events']:,.0f}",f"{p['per_day']:.1f}",f"{p['known']:,.0f}",f"{p['unknown']:,.0f}",f"{p['canceled']:,.0f}",f"{p['cancel_pct']:.2f}%"] for p in periods])
    para('National Day period event volume was close to the pre-holiday mean: 5,381 records over seven days, or 768.7 per day, compared with 5,351 records, or 764.4 per day, before the holiday. The post-holiday period had 5,126 records, or 732.3 per day. Thus, holiday-period volume was not unusually high or low relative to the preceding period, but it was lower than the pre-holiday rate and 4.7% below the pre-holiday average on a per-day basis.')
    para('Cancellation proportion showed a larger difference. The known-status denominator was 5,348 before, 5,380 during, and 5,097 after. The period rates were 3.74%, 1.91%, and 2.41%, respectively. The rate increased from 1.91% during the holiday to 2.41% afterwards, but remained below the pre-holiday level. Missing status was concentrated in the post-holiday period: 29 of 5,126 records had blank or unknown status, compared with three before and one during the holiday. This missingness changes the denominator and should prevent a literal comparison of raw cancellation counts.')
    para('Daily patterns reveal why period averages are insufficient. Figure 1 plots event volume and cancellation proportion together across all study dates. Before the holiday, cancellation proportion peaked on 26 September at 6.24% and 29 September at 8.15%. On 1 October, the first National Day date, the cancellation proportion was only 0.38%; it rose to 4.95% on 3 October and fell to zero on 7 October. The post-holiday period also varied sharply: 5.46% on 8 October compared with 0.40% on 12 October. These daily changes show that the National Day result is not a stable plateau but a sequence of individually different dates.')
    picture('daily_trends.png','Figure 1. Daily flight-event records and known-status cancellation proportions, 22 September–22 October 2026.')
    heading('3.2 RQ2: Concentration of cancellations and extreme gaps')
    para('The eligible timestamp-gap denominator was 11,560 known-status, non-cancelled departures with complete scheduled and actual departure timestamps. This denominator differs from the entire dataset because cancelled and unknown-status records were removed, and 10 departure records lacked complete paired departure timestamps. A total of 514 records reached the 60-minute threshold, equal to 4.45% of eligible records. The 514 threshold classifications are not operational delay counts. They are a high-magnitude pattern in the recorded time difference.')
    add_table(doc,'Table 2. Dates with the largest extreme-gap proportions.', ['Date','Eligible departures','Gaps ≥60 min','Extreme %'], [[d['date'],d['records'],d['extreme_n'],f"{d['extreme_pct']:.2f}%"] for d in res['extreme_dates']])
    para('Extreme gaps were unevenly distributed. 19 October had 99 threshold cases among 380 eligible departures (26.05%), the largest proportion in the date summary. 26 September had 75 among 335 (22.39%), and 2 October had 35 among 367 (9.54%). These three dates alone represented 209 of 514 extreme observations. The contrast between 19 October and the overall 4.45% rate was large, while 24 and 18 September were not in the highest date concentration due to lower eligible denominators and threshold counts. Concentration could reflect operational conditions, recorded-timestamp quality, schedule construction, or unobserved network effects.')
    para('Figure 2 makes the date pattern directly visible. The plot identifies only date-level rank; it does not provide a statistical test or imply that 19 October and 26 September are recurring risk dates. Both dates are one-off observations in a short 31-date sample. They are plausible monitoring targets for future collection of additional operational data, not established causal outliers.')
    picture('extreme_dates.png','Figure 2. Highest date-level proportions of extreme recorded departure gaps (≥60 minutes).')
    add_table(doc,'Table 3. Cancellation proportion on the five highest-cancellation dates.', ['Date','Known status','Cancelled','Cancellation %'], [[d['date'],d['known'],d['canceled'],f"{d['cancel_pct']:.2f}%"] for d in res['top_cancellation_dates']])
    para('The top cancellation date was 29 September, with 62 cancellations among 761 known-status records (8.15%). 26 September had 45 of 721 (6.24%), 28 September had 46 of 751 (6.13%), 8 October had 42 of 769 (5.46%), and 3 October had 37 of 748 (4.95%). The period-level holiday rate does not obscure these spikes. However, cancellations and extreme gaps did not peak on precisely the same dates. 26 September appeared among both highest-cancellation and highest-extreme-gap dates, but 29 September and 19 October did not. This supports treating cancellation and timestamp gap as complementary outcomes rather than one general disruption construct.')
    hour_order={'Morning':0,'Afternoon':1,'Evening':2,'Night/other':3}
    add_table(doc,'Table 4. Extreme recorded gaps by scheduled local-hour band.', ['Hour band','Eligible departures','Gaps ≥60 min','Extreme %'], [[h['hour_band'],h['records'],h['extreme_n'],f"{h['extreme_pct']:.2f}%"] for h in sorted(res['hourly_gaps'],key=lambda x:hour_order[x['hour_band'].split(' ')[0]])])
    para('The four daytime bands showed a clear descriptive gradient in threshold proportion. Morning departures had 110 extreme gaps among 4,531 eligible records (2.43%). Afternoon departures had 170 among 3,529 (4.82%), and evening departures had 233 among 3,406 (6.84%). The residual night/other band had only 94 records and one extreme gap (1.06%), too sparse for a stable comparison. The morning-to-evening increase was 4.41 percentage points. It does not mean that evening departures are causally more delayed; evening schedules may differ in route mix, airline, aircraft rotation, measurement lag, or network congestion.')
    heading('3.3 RQ3: October 10 adjusted-workday case study')
    oct=res['oct10']
    add_table(doc,'Table 5. October 10 and ordinary weekend comparison.', ['Date / classification','Events','Known','Cancelled','Cancellation %'], [[oct['date']+' / adjusted workday',oct['events'],oct['known'],oct['canceled'],f"{oct['cancel_pct']:.2f}%"]]+[[d['date']+' / ordinary weekend',d['events'],d['known'],d['canceled'],f"{d['cancel_pct']:.2f}%"] for d in res['ordinary_weekends']])
    para('October 10 had 682 flight-event records and 680 known-status records. Thirty records were cancelled, giving a 4.41% cancellation proportion. The three ordinary weekend dates had 718, 775, and 777 records. Their known-status cancellation rates were 1.54% on 11 October, 1.03% on 17 October, and 0.00% on 18 October. Relative to these observations, October 10 had both fewer events than the 775–777 ordinary-weekend dates and a higher cancellation proportion than all three.')
    picture('adjusted_workday.png','Figure 3. October 10 versus ordinary weekend dates in event volume and cancellation proportion.')
    para('The figure should not be interpreted as a general adjusted-workday effect. It is a one-date comparison within one airport and one 31-date window. October 10’s cancellation rate could reflect ordinary date-to-date variation, specific flight rotations, weather, network conditions, schedule mix, or incomplete status. The observed contrast demonstrates only that a Saturday label contains too little calendar information. 10 October is not an ordinary weekend in the official Chinese calendar and should not be grouped automatically with 11 October merely because both dates appear on Saturday/Sunday. Likewise, 10 October is not included in a general comparison as a representative of all adjusted workdays.')
    heading('4. Conclusions')
    para('The main answer to RQ1 is that flight-event volume was broadly stable across adjacent periods but cancellation proportion was not. The pre-holiday period averaged 764.4 events per day and had 3.74% cancellations; the National Day period averaged 768.7 events and had 1.91%; and the post-holiday period averaged 732.3 events and had 2.41%. This apparent stability masks substantial within-period variation and missing-status concentration. The pre-holiday period included 25–27 September Mid-Autumn public holidays, and the post-holiday period included 10 October’s adjusted workday. Therefore, “before, during, and after” is chronological, not calendar-neutral.')
    para('For RQ2, the key finding is concentration rather than uniform disruption. One cancellation date, 29 September, reached 8.15%, and 19 October accounted for 26.05% of eligible departures in the extreme-gap category. The 60-minute timestamp feature rose from 2.43% in the morning to 4.82% in the afternoon and 6.84% in the evening. These results support monitoring both unusual dates and scheduled-hour bands. They do not establish why the patterns occurred or whether they would recur. Cancellation and extreme-gap rankings are not identical, reinforcing that cancellation and time-gap outcomes should be reported separately.')
    para('For RQ3, 10 October illustrates a specific limitation of weekday/weekend labels. It was an adjusted workday falling on Saturday, and it had 682 records with a 4.41% cancellation proportion, above the three ordinary weekend observations. Yet n=1 cannot represent the adjusted-workday category. The result is evidence that ordinary weekend aggregation can conceal an administratively different workday, not evidence that adjusted workdays generally produce higher cancellations. Conventional labels need supplementation with public-holiday and adjusted-workday classifications.')
    heading('4.1 Implications')
    para('Airport planners can use the findings as a prioritization list for monitoring and further data collection. Dates with elevated cancellation or extreme-gap indicators should be investigated using weather, airline operations, aircraft rotations, connection banks, runway availability, and passenger load. Hour bands should be monitored in the context of route and schedule mix. Calendar-aware planning should retain official-day classification and avoid treating a make-up workday simply as a weekend. This is particularly relevant for short pre/post holiday comparisons, where a small number of special calendar dates can influence aggregate results.')
    heading('4.2 Limitations')
    para('The data describe 31 dates and one airport. They cannot establish national, seasonal, or passenger-travel patterns. Post-holiday status completeness was lower than in the National Day window, and cancellation proportions rely on records with known status. The timestamp-gap field is unverified and may not represent a validated operational event. The 60-minute threshold was created for this analysis rather than provided by an authoritative operational definition. No weather, demand, capacity, or network variables are available for mechanism tests. Repeated observations within dates are likely dependent. Consequently, no inferential claim or causal language is appropriate.')
    para('Several common interpretive risks remain. Flight-event count is not passenger demand. A cancellation proportion is not the probability of any individual passenger being disrupted. A large timestamp gap is not necessarily a delay or a “poor” operational outcome. A holiday comparison is not a controlled experiment. The study should therefore be used to develop monitoring hypotheses and collect better operational and passenger data, not to rank causes or justify policy in isolation.')
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
    notebook=build_notebook(res)
    report,words=build_report(res)
    if not 3000 <= words <= 6000:
        raise RuntimeError(f'Main-text word count is outside requirement: {words}')
    print(report)
    print(notebook)
    print(f'Main-text words: {words}')

if __name__=='__main__': main()
