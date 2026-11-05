#!/usr/bin/env python3
"""Reproduce the three-question SHA National Day final project."""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sha_master.csv"
OUT = ROOT / "final_project"
FIG = OUT / "figures"
HOLIDAY = date(2026, 10, 1)
PERIODS = (
    ("Pre-holiday", HOLIDAY-timedelta(days=7), HOLIDAY-timedelta(days=1)),
    ("National Day", HOLIDAY, HOLIDAY+timedelta(days=6)),
    ("Post-holiday", HOLIDAY+timedelta(days=7), HOLIDAY+timedelta(days=13)),
)
NAVY, BLUE, TEAL, ORANGE, RED = "#17324d", "#2878B5", "#5A9E8F", "#E07A32", "#BE4B48"


def pct(n, d): return 100*n/d if d else 0.0
def parse_dt(v): return datetime.fromisoformat(v.replace("Z", "+00:00"))
def known(r): return r["status_display"].strip().lower() not in ("", "unknown")
def canceled(r): return r["status_display"].strip().lower() == "canceled"
def window_hour(h):
    return "Morning (06-11)" if 6 <= h <= 11 else ("Afternoon (12-16)" if 12 <= h <= 16 else ("Evening (17-22)" if 17 <= h <= 22 else "Night/other (23-05)"))


def read():
    with DATA.open(newline="", encoding="utf-8-sig") as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        r["_date"] = date.fromisoformat(r["local_date"])
        r["_hour"] = int(r["local_hour"])
    return rows


def rate(rows):
    k=[r for r in rows if known(r)]
    return {"events":len(rows),"known":len(k),"unknown":len(rows)-len(k),"canceled":sum(canceled(r) for r in k),"cancel_pct":pct(sum(canceled(r) for r in k),len(k))}


def daily(rows):
    groups=defaultdict(list)
    for r in rows: groups[r["_date"]].append(r)
    out=[]
    for d, rs in sorted(groups.items()):
        x=rate(rs); x.update(date=d.isoformat(),weekday=rs[0]["weekday"],day_type=rs[0]["calendar_day_type"])
        out.append(x)
    return out


def analysis(rows):
    ds=daily(rows)
    periods=[]
    for label,start,end in PERIODS:
        rs=[r for r in rows if start<=r["_date"]<=end]
        present={r["_date"] for r in rs}; expected={start+timedelta(days=i) for i in range(7)}
        assert present==expected
        x=rate(rs); x.update(label=label,start=start.isoformat(),end=end.isoformat(),per_day=len(rs)/7)
        periods.append(x)
    eligible=[]
    missing_gap=0
    for r in rows:
        if r["direction"] != "departure" or not known(r) or canceled(r): continue
        if not r["scheduled_departure_utc"] or not r["actual_departure_utc"]:
            missing_gap += 1; continue
        gap=(parse_dt(r["actual_departure_utc"])-parse_dt(r["scheduled_departure_utc"])).total_seconds()/60
        if abs(gap-float(r["timing_difference_minutes"]))>1e-6: raise AssertionError("timestamp mismatch")
        eligible.append((r,gap))
    extreme=[(r,g) for r,g in eligible if g>=60]
    date_groups=defaultdict(list); hour_groups=defaultdict(list)
    for r,g in eligible: date_groups[r["_date"]].append(g)
    for r,g in eligible: hour_groups[window_hour(r["_hour"])].append(g)
    hourly=[{"hour_band":h,"records":len(gs),"extreme_n":sum(g>=60 for g in gs),"extreme_pct":pct(sum(g>=60 for g in gs),len(gs)),"median_gap":sorted(gs)[len(gs)//2]} for h,gs in hour_groups.items()]
    unusual=[]
    for d,gs in date_groups.items():
        unusual.append({"date":d.isoformat(),"records":len(gs),"extreme_n":sum(g>=60 for g in gs),"extreme_pct":pct(sum(g>=60 for g in gs),len(gs))})
    unusual.sort(key=lambda x:(-x["extreme_n"],-x["extreme_pct"],x["date"]))
    cancellations=sorted(ds,key=lambda x:(-x["cancel_pct"],x["date"]))[:5]
    cancellation_count=[x for x in ds if x["canceled"]]
    ordinary_weekends=[x for x in ds if x["day_type"]=="weekend"]
    oct10=[r for r in rows if r["_date"]==date(2026,10,10)]
    oct10_stats=rate(oct10)
    oct10_stats.update(date="2026-10-10",adjusted_workday=True)
    return {"rows":len(rows),"dates":len(ds),"periods":periods,"daily":ds,"eligible_gap_records":len(eligible),"missing_gap_records":missing_gap,"extreme_gap_records":len(extreme),"extreme_gap_pct":pct(len(extreme),len(eligible)),"hourly_gaps":hourly,"extreme_dates":unusual[:5],"top_cancellation_dates":cancellations,"ordinary_weekends":ordinary_weekends,"oct10":oct10_stats}


def fig1(res):
    fig,axs=plt.subplots(2,1,figsize=(8.2,7.2),sharex=True)
    ds=res["daily"]
    xs=[date.fromisoformat(x["date"]) for x in ds]
    axs[0].plot(xs,[x["events"] for x in ds],marker="o",ms=3.1,color=BLUE,lw=1.5)
    axs[0].set_ylabel("Flight events")
    axs[0].set_title("A. Daily flight-event volume")
    axs[0].grid(axis="y",alpha=.25)
    axs[1].plot(xs,[x["cancel_pct"] for x in ds],marker="o",ms=3.1,color=ORANGE,lw=1.5)
    axs[1].axvspan(HOLIDAY,HOLIDAY+timedelta(days=7),color=ORANGE,alpha=.10)
    axs[1].set_ylabel("Cancellation, % of known status")
    axs[1].set_xlabel("Local date")
    axs[1].yaxis.set_major_formatter(PercentFormatter())
    axs[1].set_title("B. Daily cancellation proportion")
    axs[1].grid(axis="y",alpha=.25)
    axs[1].xaxis.set_major_locator(mdates.DayLocator(interval=3)); axs[1].xaxis.set_major_formatter(mdates.DateFormatter("%b %-d"))
    fig.tight_layout(); p=FIG/"daily_trends.png"; fig.savefig(p,dpi=220,bbox_inches="tight"); plt.close(fig); return p


def fig2(res):
    dates=res["extreme_dates"]
    fig,ax=plt.subplots(figsize=(8.2,4.2))
    y=[f"{x['date']}" for x in dates][::-1]; vals=[x["extreme_pct"] for x in dates][::-1]
    ax.barh(y,vals,color=ORANGE); ax.set_xlabel("Extreme gaps (≥60 min), % of eligible departures")
    ax.set_title("Dates with the largest extreme-gap counts")
    ax.grid(axis="x",alpha=.25); ax.xaxis.set_major_formatter(PercentFormatter())
    fig.tight_layout(); p=FIG/"extreme_dates.png"; fig.savefig(p,dpi=220,bbox_inches="tight"); plt.close(fig); return p


def fig3(res):
    labels=["Oct 10\nadjusted workday"]+[f"{d['date']}\nordinary weekend" for d in res["ordinary_weekends"]]
    ev=[res["oct10"]["events"]]+[d["events"] for d in res["ordinary_weekends"]]
    cp=[res["oct10"]["cancel_pct"]]+[d["cancel_pct"] for d in res["ordinary_weekends"]]
    fig,axs=plt.subplots(1,2,figsize=(8.2,4.2))
    axs[0].bar(labels,ev,color=[RED,BLUE,BLUE,BLUE]); axs[0].set_ylabel("Flight events")
    axs[0].set_title("A. Recorded event volume")
    axs[1].bar(labels,cp,color=[RED,BLUE,BLUE,BLUE]); axs[1].set_ylabel("Cancellation, %")
    axs[1].yaxis.set_major_formatter(PercentFormatter()); axs[1].set_title("B. Cancellation proportion")
    for ax in axs: ax.grid(axis="y",alpha=.25)
    fig.autofmt_xdate(rotation=25); fig.tight_layout()
    p=FIG/"adjusted_workday.png"; fig.savefig(p,dpi=220,bbox_inches="tight"); plt.close(fig); return p


def build_md(res, figures):
    p=res["periods"]
    text=["# SHA Flight-Service Patterns Around China's 2026 National Day Holiday", "", "## Abstract", "", "This final project presents a descriptive, single-airport analysis of 23,705 flight-event records at Shanghai Hongqiao Airport (SHA), covering September 22-October 22, 2026. It addresses three revised questions: calendar-phase differences, concentration of cancellations and extreme recorded departure timestamp gaps, and the interpretive limitation of comparing an adjusted workday with ordinary weekends. Equal seven-day windows are used for RQ1. A gap of at least 60 minutes is an exploratory timestamp feature, not a verified operational delay. Results identify date-hour patterns but do not establish causation.", "", "## Research questions", "", "1. **RQ1 — Calendar:** How did flight-service volume and cancellation proportions vary before, during, and after the National Day holiday?", "2. **RQ2 — Disruption:** Were cancellation proportions and extreme departure-time gaps concentrated on particular dates or departure hours?", "3. **RQ3 — Interpretation:** What does October 10 reveal about comparing weekday/weekend labels in China?", "", "## RQ1: Equal-length holiday-phase comparison", ""]
    text += [f"| Phase | Dates | Events | Events/day | Known status | Unknown status | Cancellations | Cancellation % |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in p:
        text.append(f"| {x['label']} | {x['start']} to {x['end']} | {x['events']:,} | {x['per_day']:.1f} | {x['known']:,} | {x['unknown']:,} | {x['canceled']} | {x['cancel_pct']:.2f}% |")
    text += ["", "The period means mask substantial day-to-day variation. The pre-holiday window contains Mid-Autumn public holidays on September 25-27; the post-holiday window includes the adjusted workday on October 10. The cancellation denominator is explicitly reported because missing or unknown status is not the same as non-cancellation.", "", f"![Daily trends](figures/{figures[0].name})", "", "**Missing status data:** 34 of 23,705 records have missing/unknown status (0.14%). The known-status denominator used for cancellation proportions is therefore 23,671.", "", "## RQ2: Dates and hours of disruption indicators", "", "The denominator for the timestamp-gap analysis is known-status, non-cancelled departures with complete scheduled and actual departure timestamps: {:,} records. Missing or unusable timestamps remove {:,} departures. The 60-minute threshold is pre-specified: a gap ≥60 minutes is **extreme recorded timing**, not a confirmed operational delay. The supplied `timing_semantics_verified` field is false for every record.".format(res["eligible_gap_records"],res["missing_gap_records"]), "", f"Overall, {res['extreme_gap_records']} of {res['eligible_gap_records']} eligible departures ({res['extreme_gap_pct']:.2f}%) have an extreme gap.", ""]
    text += ["| Highest extreme-gap dates | Eligible departures | ≥60-minute gaps | Extreme proportion |", "|---|---:|---:|---:|"]
    for x in res["extreme_dates"]:
        text.append(f"| {x['date']} | {x['records']} | {x['extreme_n']} | {x['extreme_pct']:.2f}% |")
    text += ["", "**Highest cancellation dates:**"]
    text += ["| Date | Known status | Cancellations | Cancellation % |", "|---|---:|---:|---:|"]
    for x in res["top_cancellation_dates"]:
        text.append(f"| {x['date']} | {x['known']} | {x['canceled']} | {x['cancel_pct']:.2f}% |")
    text += ["", f"![Extreme-gap dates](figures/{figures[1].name})", "", "| Departure hour band | Eligible departures | Extreme gaps | Extreme proportion |", "|---|---:|---:|---:|"]
    for x in sorted(res["hourly_gaps"],key=lambda z:("Morning" not in z["hour_band"],"Afternoon" not in z["hour_band"],"Evening" not in z["hour_band"])):
        text.append(f"| {x['hour_band']} | {x['records']} | {x['extreme_n']} | {x['extreme_pct']:.2f}% |")
    text += ["", "The afternoon category is included because it can separate the middle of the operating day from morning and evening. Patterns are descriptive. Date clustering may reflect the small number of observations on a date and should not be read as evidence of recurring airport, airline, weather, or passenger-demand effects.", "", "## RQ3: October 10 adjusted-workday case study", "", f"October 10 has {res['oct10']['events']} flight events, {res['oct10']['known']} known-status records, and {res['oct10']['canceled']} cancellations ({res['oct10']['cancel_pct']:.2f}%). It should not be pooled with ordinary Saturday records or ordinary weekdays.", ""]
    text += ["| Date/class | Events | Known | Cancellations | Cancellation % |", "|---|---:|---:|---:|---:|"]
    text.append(f"| 2026-10-10 / adjusted workday | {res['oct10']['events']} | {res['oct10']['known']} | {res['oct10']['canceled']} | {res['oct10']['cancel_pct']:.2f}% |")
    for x in res["ordinary_weekends"]:
        text.append(f"| {x['date']} / ordinary weekend | {x['events']} | {x['known']} | {x['canceled']} | {x['cancel_pct']:.2f}% |")
    text += ["", f"![Adjusted-workday comparison](figures/{figures[2].name})", "", "The comparison shows one date, not a general adjusted-workday effect. The ordinary-weekend reference also has only three observations. Relative to this small set, October 10 has the greatest observed cancellation proportion (4.41%), but that fact cannot establish that being an adjusted workday caused the difference. Calendar labels, demand, operations, and data-recording conditions remain confounded.", "", "## Implications and limitations", "", "Airport planners can use unusual dates and hour bands as monitoring targets because the analysis indicates where descriptive disruption indicators are concentrated. It does not identify causes or prove that patterns recur in future years. The data measure flight-event records, not passenger demand or airport congestion. Timestamp gaps are exploratory and unverified as operational delay. A pre/post comparison is associational; only one year and one airport are observed.", "", "## Reproducibility", "", "Run `uv run python scripts/build_final_project.py`. The script validates a unique event_id and all seven dates in each period, verifies that every recorded timestamp gap matches `timing_difference_minutes`, and writes `final_project_results.json`, figures, this Markdown report, and `final_project.pdf`."]
    path=OUT/"final_project.md"; path.write_text("\n".join(text),encoding="utf-8")
    return path


def build_pdf(res, md_path):
    styles=getSampleStyleSheet(); styles.add(ParagraphStyle(name="Cover",parent=styles["Title"],fontSize=22,leading=27,alignment=TA_CENTER,textColor=colors.HexColor(NAVY)))
    styles.add(ParagraphStyle(name="Sub",parent=styles["Normal"],fontSize=10,leading=14,alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Body2",parent=styles["BodyText"],fontSize=9.3,leading=13.5,alignment=1))
    doc=SimpleDocTemplate(str(OUT/"final_project.pdf"),pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,topMargin=16*mm,bottomMargin=16*mm)
    s=[]
    s += [Spacer(1,22*mm),Paragraph("SHA Flight-Service Patterns Around China’s 2026 National Day Holiday",styles["Cover"]),Spacer(1,8*mm),Paragraph("Final project — calendar, disruption concentration, and adjusted-workday interpretation",styles["Sub"]),Spacer(1,8*mm),Paragraph("Shanghai Hongqiao Airport · September 22–October 22, 2026",styles["Sub"]),PageBreak()]
    md=md_path.read_text(encoding="utf-8")
    sections=[]
    for block in md.split("\n\n"):
        if block.startswith("!["):
            name=block.split("(",1)[1].split(")",1)[0]; p=OUT/name
            s += [Image(str(p),width=174*mm,height=92*mm,kind="proportional")]
        elif block.startswith("# "):
            s += [Paragraph(block[2:],styles["Title"])]
        elif block.startswith("## "):
            s += [Paragraph(block[3:],styles["Heading1"])]
        elif block.startswith("|"):
            lines=[x for x in block.splitlines() if not set(x.replace("|","").replace("-","").strip())<=set()]
            cells=[]
            for line in lines:
                if set(line.replace("|","").replace("-","").strip()) == set(): continue
                if all(c in "|-: " for c in line): continue
                cells.append([c.strip() for c in line.strip("|").split("|")])
            if cells:
                table=Table(cells,repeatRows=1,hAlign="LEFT")
                table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(NAVY)),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("VALIGN",(0,0),(-1,-1),"TOP"),("GRID",(0,0),(-1,-1),.25,colors.grey),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#EEF3F7")])]))
                s += [table,Spacer(1,3*mm)]
        else:
            if block.strip() and not block.startswith("|"):
                s += [Paragraph(block.replace("**", ""),styles["Body2"]),Spacer(1,2*mm)]
    doc.build(s)


def main():
    OUT.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
    rows=read()
    assert len(rows)==len({r["event_id"] for r in rows})
    res=analysis(rows)
    figures=[fig1(res),fig2(res),fig3(res)]
    md=build_md(res,figures)
    build_pdf(res,md)
    (OUT/"final_project_results.json").write_text(json.dumps(res,indent=2),encoding="utf-8")
    print(f"Created {md} and {OUT/'final_project.pdf'}")

if __name__=="__main__": main()
