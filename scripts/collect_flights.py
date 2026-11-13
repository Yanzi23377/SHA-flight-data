"""Collect permitted flight-page history, with explicit discovery/coverage limits."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from http.cookiejar import LoadError, MozillaCookieJar
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page

if __package__:
    from .fetch_flights import flight_number_from_url, load_cookie_jar
else:
    from fetch_flights import flight_number_from_url, load_cookie_jar


ROOT = Path(__file__).resolve().parents[1]
BASE = "https://www.flightradar24.com/data/flights"
SHA_ZONE = timezone(timedelta(hours=8))
FLIGHT_NUMBER = re.compile(r"[A-Z0-9]{2,3}[0-9]{1,4}[A-Z]?")

# Read only the flight table, not account/session fields elsewhere in the page.
EXTRACT_HISTORY = r"""() => {
    const table = document.querySelector('#tbl-datatable');
    if (!table) throw new Error('Flight history table is missing');
    const header = Array.from(table.querySelectorAll('tr')).find(r =>
        Array.from(r.querySelectorAll(':scope > th')).some(c => c.textContent.trim() === 'STD'));
    if (!header) throw new Error('Flight history column headers are missing');
    const labels = Array.from(header.children).map(c => c.textContent.trim());
    for (const name of ['DATE', 'FROM', 'TO', 'AIRCRAFT', 'STD', 'ATD', 'STA', 'STATUS'])
        if (!labels.includes(name)) throw new Error('Missing column: ' + name);
    return Array.from(table.querySelectorAll('tbody tr.data-row')).map(row => {
        const cells = Array.from(row.children);
        const cell = name => cells[labels.indexOf(name)];
        const text = name => (cell(name)?.textContent || '').replace(/\s+/g, ' ').trim();
        const attr = (name, key) => cell(name)?.getAttribute(key) || '';
        const airport = name => {
            const href = cell(name)?.querySelector('a[href*="/data/airports/"]')?.getAttribute('href') || '';
            return (href.match(/\/data\/airports\/([a-z0-9]{3})(?:[/?#]|$)/i)?.[1] || '').toUpperCase();
        };
        return {
            date_epoch: attr('DATE', 'data-timestamp'),
            origin_iata: airport('FROM'), destination_iata: airport('TO'),
            aircraft_display: text('AIRCRAFT'),
            registration: (cell('AIRCRAFT')?.querySelector('a')?.textContent || '').replace(/[()]/g, '').trim(),
            scheduled_departure_epoch: attr('STD', 'data-timestamp'),
            actual_departure_epoch: attr('ATD', 'data-timestamp'),
            scheduled_arrival_epoch: attr('STA', 'data-timestamp'),
            status_epoch: attr('STATUS', 'data-timestamp'),
            departure_utc_offset_seconds: attr('STD', 'data-offset'),
            arrival_utc_offset_seconds: attr('STA', 'data-offset'),
            scheduled_departure_display: text('STD'),
            actual_departure_display: text('ATD'),
            scheduled_arrival_display: text('STA'),
            status_display: text('STATUS'),
            flight_hex: row.querySelector('[data-flight-hex]')?.getAttribute('data-flight-hex') || '',
            schedule_id: row.querySelector('[data-schedule-id]')?.getAttribute('data-schedule-id') || ''
        };
    });
}"""


class AccessRestricted(RuntimeError):
    """Authentication, rate limiting, or access restrictions require user action."""


def read_session_cookies(path: Path) -> MozillaCookieJar:
    if not path.is_file():
        raise ValueError("Cookie export file does not exist; supply a Netscape-format file")
    try:
        jar = load_cookie_jar(path)
    except (LoadError, ValueError):
        # CookieJar errors can quote entire cookie lines, including session secrets.
        raise ValueError("Invalid Netscape cookie export; cookie contents withheld") from None
    if jar is None:
        raise ValueError("Cookie export was not loaded")
    for cookie in list(jar):
        domain = cookie.domain.lstrip(".").lower()
        if domain != "flightradar24.com" and not domain.endswith(".flightradar24.com"):
            jar.clear(cookie.domain, cookie.path, cookie.name)
    if not len(jar):
        raise ValueError("Cookie export contains no unexpired Flightradar24 cookies")
    return jar


def import_session_cookies(context: BrowserContext, jar: MozillaCookieJar) -> None:
    from playwright.sync_api import Error as BrowserError

    try:
        context.add_cookies([
            {
                "name": cookie.name,
                "value": cookie.value or "",
                "domain": cookie.domain,
                "path": cookie.path or "/",
                "secure": cookie.secure,
                "httpOnly": cookie.has_nonstandard_attr("HTTPOnly"),
                "expires": float(cookie.expires) if cookie.expires is not None else -1.0,
            }
            for cookie in jar
        ])
    except BrowserError:
        raise ValueError("Could not import cookie export into Edge; cookie contents withheld") from None


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def validated_rows(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("Expected a list of flight rows")
    rows = []
    for row in value:
        if not isinstance(row, dict) or not all(
            isinstance(key, str) and isinstance(item, str) for key, item in row.items()
        ):
            raise ValueError("Flight rows must contain only string keys and values")
        rows.append(dict(row))
    return rows


def epoch(value: str) -> datetime | None:
    if not value:
        return None
    if not re.fullmatch(r"[0-9]{9,10}", value):
        raise ValueError(f"Invalid source Unix timestamp: {value!r}")
    return datetime.fromtimestamp(int(value), timezone.utc)


def utc_text(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z") if value else ""


def history_record(
    raw: dict[str, str], number: str, airline: str, start: date, end: date,
    retrieved_at: str,
) -> dict[str, str] | None:
    origin, destination = raw.get("origin_iata", ""), raw.get("destination_iata", "")
    if not all(re.fullmatch(r"[A-Z]{3}", code) for code in (origin, destination)):
        raise ValueError("History row has missing or unrecognized airports")
    if "SHA" not in (origin, destination):
        return None
    direction = "departure" if origin == "SHA" else "arrival"
    departure = epoch(raw.get("scheduled_departure_epoch", ""))
    arrival = epoch(raw.get("scheduled_arrival_epoch", ""))
    scheduled = departure if direction == "departure" else arrival
    if scheduled is None:
        raise ValueError("Cannot date an SHA event without its scheduled timestamp")
    local = scheduled.astimezone(SHA_ZONE)
    if not start <= local.date() <= end:
        return None
    actual_departure = epoch(raw.get("actual_departure_epoch", ""))
    status_time = epoch(raw.get("status_epoch", ""))
    landed = status_time if raw.get("status_display", "").casefold().startswith("landed") else None
    actual = actual_departure if direction == "departure" else landed
    source_url = f"{BASE}/{number.lower()}"
    record = {
        key: value for key, value in raw.items()
        if not key.endswith("_epoch") and value not in {"-", "\u2014", "N/A"}
    }
    record.update({
        "direction": direction,
        "flight_number": number, "flight_numbers": number,
        "route": f"{origin}-{destination}",
        "airline_display": airline,
        "scheduled_utc": utc_text(scheduled),
        "scheduled_sha_local": local.isoformat(timespec="seconds"),
        "local_date": local.date().isoformat(),
        "local_hour": str(local.hour), "weekday": local.strftime("%A"),
        "scheduled_departure_utc": utc_text(departure),
        "scheduled_arrival_utc": utc_text(arrival),
        "actual_departure_utc": utc_text(actual_departure),
        "landed_status_utc": utc_text(landed),
        "status_event_utc": utc_text(status_time),
        "actual_event_utc": utc_text(actual),
        "timing_difference_minutes": str((actual - scheduled).total_seconds() / 60) if actual else "",
        "timing_semantics_verified": "false",
        "operating_carrier_verified": "false",
        "completed_for_timing_readiness": "true" if actual else "false",
        "source_url": source_url, "source_urls": source_url,
        "retrieved_at_utc": retrieved_at, "observation_count": "1",
        "identity_review": "false", "identity_review_required": "false",
        "conflict_fields": "",
    })
    # A source flight ID can join codeshares. The fallback cannot safely do that.
    physical_id = raw.get("flight_hex", "")
    identity = f"fr24:{physical_id}" if physical_id else (
        f"fallback:{number}:{origin}:{destination}:{utc_text(departure or scheduled)}"
    )
    record["canonical_id"] = "sha_" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    record["event_id"] = f"{record['canonical_id']}:{direction}"
    if not physical_id:
        record["identity_review"] = record["identity_review_required"] = "true"
    return record


def deduplicate(records: list[dict[str, str]]) -> list[dict[str, str]]:
    combined: dict[str, dict[str, str]] = {}
    aggregate = {"flight_numbers", "source_urls", "airline_display", "conflict_fields"}
    ignored = aggregate | {
        "flight_number", "source_url", "retrieved_at_utc", "observation_count",
        "identity_review", "identity_review_required",
    }
    for observation in records:
        identifier = observation["event_id"]
        if identifier not in combined:
            combined[identifier] = observation.copy()
            continue
        record = combined[identifier]
        conflicts = set(filter(None, record.get("conflict_fields", "").split(";")))
        for field, value in observation.items():
            if field in aggregate:
                record[field] = ";".join(sorted(
                    set(filter(None, record.get(field, "").split(";")))
                    | set(filter(None, value.split(";")))
                ))
            elif field not in ignored:
                if record.get(field) and value and record[field] != value:
                    conflicts.add(field)
                elif value:
                    record[field] = value
        record["conflict_fields"] = ";".join(sorted(conflicts))
        record["observation_count"] = str(int(record["observation_count"]) + 1)
        record["retrieved_at_utc"] = max(record["retrieved_at_utc"], observation["retrieved_at_utc"])
        if conflicts or observation["identity_review_required"] == "true":
            record["identity_review"] = record["identity_review_required"] = "true"
    return sorted(combined.values(), key=lambda row: (row["scheduled_utc"], row["event_id"]))


def seed_candidates(path: Path) -> tuple[dict[str, list[str]], set[tuple[str, str]]]:
    candidates: dict[str, list[str]] = {}
    routes: set[tuple[str, str]] = set()
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "flight_number" not in reader.fieldnames:
            raise ValueError("Seed CSV must contain flight_number (master or flight-number CSV)")
        for row in reader:
            origin, destination = row.get("origin_iata", ""), row.get("destination_iata", "")
            if origin and destination:
                if "SHA" not in (origin, destination):
                    continue
                if not all(re.fullmatch(r"[A-Z]{3}", code) for code in (origin, destination)):
                    raise ValueError("Invalid airport code in seed CSV")
                routes.update({(origin, destination), (destination, origin)})
            numbers = set(filter(None, (
                row.get("flight_number", "") + ";" + row.get("flight_numbers", "")
            ).split(";")))
            for number in numbers:
                number = number.strip().upper()
                if not FLIGHT_NUMBER.fullmatch(number):
                    raise ValueError(f"Invalid seed flight number: {number!r}")
                candidates[number] = [f"seed:{path.name}"]
    return candidates, routes


def read_routes(path: Path) -> set[tuple[str, str]]:
    routes = set()
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not {"origin_iata", "destination_iata"}.issubset(reader.fieldnames or []):
            raise ValueError("Routes CSV requires origin_iata,destination_iata")
        for row in reader:
            origin, destination = row["origin_iata"].strip().upper(), row["destination_iata"].strip().upper()
            if origin == destination or "SHA" not in (origin, destination) or not all(
                re.fullmatch(r"[A-Z]{3}", code) for code in (origin, destination)
            ):
                raise ValueError(f"Invalid SHA route: {origin}-{destination}")
            routes.update({(origin, destination), (destination, origin)})
    return routes


def checked_navigation(page: Page, url: str, delay: float) -> None:
    time.sleep(delay)
    response = page.goto(url, wait_until="domcontentloaded")
    if response and response.status >= 400:
        if response.status in {401, 403, 429}:
            raise AccessRestricted(f"HTTP {response.status}; collection stopped, no bypass attempted")
        raise ValueError(f"HTTP {response.status} loading flight page")
    assert_access(page)


def assert_access(page: Page) -> None:
    parts = urlsplit(page.url)
    if parts.hostname not in {"www.flightradar24.com", "flightradar24.com"} or "/auth/" in parts.path:
        raise AccessRestricted("Sign-in redirect; sign in manually using --login")
    title = page.title().casefold()
    if any(term in title for term in ("just a moment", "access denied", "captcha", "security check")):
        raise AccessRestricted("Access/security challenge; collection stopped")


def require_paid_session(page: Page, timeout_ms: int = 20000) -> None:
    from playwright.sync_api import TimeoutError as BrowserTimeoutError

    assert_access(page)
    try:
        page.get_by_role("button", name=re.compile(r"^(Gold|Business)$")).wait_for(
            state="visible", timeout=timeout_ms,
        )
    except BrowserTimeoutError:
        assert_access(page)
        raise AccessRestricted(
            "Gold/Business session not found after waiting for the page; cookie import alone "
            "does not confirm authentication. Refresh the cookie export or use --login."
        ) from None


def discover_route(page: Page, origin: str, destination: str, delay: float) -> tuple[list[str], int]:
    checked_navigation(page, BASE, delay)
    for selector, airport in (("#searchAirportFrom", origin), ("#searchAirportTo", destination)):
        page.locator(selector).fill(airport)
        suggestion = page.locator(".tt-suggestion").filter(
            has_text=re.compile(rf"\b{airport}\s*/")
        ).first
        suggestion.wait_for(state="visible")
        suggestion.click()
    results = page.locator(".tt-suggestion").filter(has_text=re.compile(r"\d{4}-\d{2}-\d{2}"))
    results.first.wait_for(state="visible")
    names = results.locator("strong").all_text_contents()
    numbers = sorted(set(name.strip().upper() for name in names))
    if not numbers or not all(FLIGHT_NUMBER.fullmatch(number) for number in numbers):
        raise ValueError("Route search returned unrecognized flight numbers")
    return numbers, results.count()


def collect_history(
    page: Page, number: str, start: date, end: date, delay: float, max_pages: int,
) -> tuple[list[dict[str, str]], str]:
    checked_navigation(page, f"{BASE}/{number.lower()}", delay)
    page.locator("#tbl-datatable tbody tr.data-row").first.wait_for()
    heading = page.get_by_role(
        "heading", name=re.compile(rf"^Flight history for .+ flight {re.escape(number)}\s*$", re.IGNORECASE)
    ).inner_text()
    match = re.fullmatch(
        rf"Flight history for (.+) flight {re.escape(number)}", heading.strip(), re.IGNORECASE
    )
    if not match:
        raise ValueError("Flight heading changed; refusing to guess the airline")
    airline = match.group(1)
    status = "page_limit"
    raw_rows = validated_rows(page.evaluate(EXTRACT_HISTORY))
    for attempt in range(max_pages + 1):
        assert_access(page)
        # Scan the entire table: the source is not assumed to be perfectly sorted.
        dates = [epoch(row.get("date_epoch", "")) for row in raw_rows]
        if not dates or any(value is None for value in dates):
            raise ValueError("Missing history dates; cannot assess pagination")
        # Departure dates earlier than start-1 cover timezone/overnight arrivals.
        cutoff = datetime.combine(start - timedelta(days=1), datetime.min.time(), timezone.utc)
        if min(value for value in dates if value is not None) < cutoff:
            status = "reached_start"
            break
        earlier = page.locator("#btn-load-earlier-flights")
        if not earlier.count() or not earlier.is_visible() or not earlier.is_enabled():
            status = "history_exhausted_unverified"
            break
        if attempt == max_pages:
            break
        previous_count = len(raw_rows)
        time.sleep(delay)
        earlier.click()
        page.wait_for_function(
            "n => document.querySelectorAll('#tbl-datatable tbody tr.data-row').length > n",
            arg=previous_count,
        )
        raw_rows = validated_rows(page.evaluate(EXTRACT_HISTORY))
    retrieved = datetime.now(timezone.utc).isoformat()
    records = []
    for raw in raw_rows:
        record = history_record(raw, number, airline, start, end, retrieved)
        if record:
            records.append(record)
    return records, status


def coverage_report(
    records: list[dict[str, str]], start: date, end: date, discovery: dict,
    flights: dict, selected: list[str],
) -> dict:
    dates = [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]
    daily = Counter(f"{row['local_date']}:{row['direction']}" for row in records)
    return {
        "airport": "SHA", "start": start.isoformat(), "end": end.isoformat(),
        "date_basis": "Scheduled SHA event date in UTC+08:00; arrivals use scheduled arrival",
        "complete_airport_census": False,
        "limitations": [
            "Candidate routes and flight numbers may omit historical/discontinued services.",
            "Route autocomplete is not a historical census and may truncate results.",
            "Reaching the start date does not prove every intervening flight was listed.",
            "Airline display is not verified operating-carrier identity; timings remain unverified.",
            "No independent historical airport movement reference has been reconciled.",
        ],
        "candidate_numbers": len(discovery["candidates"]),
        "pending_numbers": sorted(set(discovery["candidates"]) - set(flights)),
        "collection_mode": discovery.get("collection_mode", "local_browser"),
        "selected_numbers": selected, "flights": flights,
        "discovery_routes": discovery["routes"],
        "collection_error": discovery.get("last_error", ""),
        "records": len(records),
        "identity_review_records": sum(row["identity_review_required"] == "true" for row in records),
        "daily_counts": {
            day: {direction: daily[f"{day}:{direction}"] for direction in ("arrival", "departure")}
            for day in dates
        },
        "missing_dates": [day for day in dates if not any(daily[f"{day}:{d}"] for d in ("arrival", "departure"))],
        "route_counts": dict(sorted(Counter(row["route"] for row in records).items())),
        "airline_display_counts": dict(sorted(Counter(row["airline_display"] for row in records).items())),
    }


def export_results(output: Path, template: Path, run_dir: Path, state: dict, start: date, end: date, selected: list[str]) -> int:
    with template.open(newline="", encoding="utf-8-sig") as source:
        fields = next(csv.reader(source), [])
    required = {"event_id", "flight_number", "direction", "scheduled_utc", "local_date", "source_urls"}
    if not required.issubset(fields):
        raise ValueError("Template does not contain required master dataset fields")
    observations = []
    for result in state["flights"].values():
        if "cache" in result:
            observations.extend(validated_rows(json.loads((run_dir / result["cache"]).read_text(encoding="utf-8"))))
    records = deduplicate(observations)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    temporary.replace(output)
    report = coverage_report(records, start, end, state, state["flights"], selected)
    atomic_json(output.with_suffix(".coverage.json"), report)
    atomic_json(output.with_suffix(".candidates.json"), state["candidates"])
    return len(records)


def parse_shared_export(
    payload: object, start: date, end: date,
    quarantine: list[dict] | None = None,
) -> tuple[str, list[dict[str, str]], str, str]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Expected a version 1 shared-browser flight export")
    required = ("flight_number", "airline_display", "source_url", "retrieved_at_utc", "history_status")
    if any(not isinstance(payload.get(key), str) or not payload[key].strip() for key in required):
        raise ValueError("Shared-browser export is missing required flight metadata")
    number = payload["flight_number"]
    if not FLIGHT_NUMBER.fullmatch(number) or flight_number_from_url(payload["source_url"]) != number:
        raise ValueError("Shared-browser export flight number and source URL must agree")
    retrieved = datetime.fromisoformat(payload["retrieved_at_utc"].replace("Z", "+00:00"))
    if retrieved.tzinfo is None:
        raise ValueError("Shared-browser retrieval timestamp requires a timezone")
    retrieved = retrieved.astimezone(timezone.utc)
    status = payload["history_status"]
    if status not in {"reached_start", "history_exhausted_unverified", "page_limit"}:
        raise ValueError("Unrecognized shared-browser history status")
    raw_rows = validated_rows(payload.get("rows"))
    if not raw_rows:
        raise ValueError("Shared-browser export contains no history rows")
    dates = []
    dated_rows = []
    for index, raw in enumerate(raw_rows):
        try:
            value = epoch(raw.get("date_epoch", ""))
            if value is None:
                raise ValueError("Shared-browser export contains missing history dates")
        except ValueError as error:
            if quarantine is None:
                raise
            quarantine.append({
                "flight_number": number, "row_index": index, "reason": str(error), "raw": raw,
            })
            continue
        dates.append(value)
        dated_rows.append((index, raw))
    cutoff = datetime.combine(start - timedelta(days=1), datetime.min.time(), timezone.utc)
    if status == "reached_start" and (not dates or min(dates) >= cutoff):
        raise ValueError("Shared-browser export does not substantiate its claimed start-date coverage")
    records = []
    for index, raw in dated_rows:
        try:
            record = history_record(raw, number, payload["airline_display"], start, end, retrieved.isoformat())
        except ValueError as error:
            if quarantine is None:
                raise
            quarantine.append({
                "flight_number": number, "row_index": index, "reason": str(error), "raw": raw,
            })
            continue
        if record:
            records.append(record)
    return number, records, status, retrieved.isoformat()


def import_shared_exports(
    directory: Path, run_dir: Path, state: dict, start: date, end: date,
) -> list[str]:
    files = sorted(directory.glob("*.json"))
    if not files:
        raise ValueError("No shared-browser JSON batches found in the export directory")
    latest: dict[str, tuple[list[dict[str, str]], str, str, str]] = {}
    errors = []
    # Validate all batches before changing caches or the output dataset.
    for path in files:
        batch = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(batch, dict) or not isinstance(batch.get("exports"), list):
            raise ValueError(f"Expected a shared-browser batch containing exports: {path.name}")
        if not isinstance(batch.get("stopped", ""), str):
            raise ValueError("Shared-browser batch stopped reason must be text")
        if batch.get("stopped"):
            errors.append(f"{path.name}: {batch['stopped']}")
        for payload in batch["exports"]:
            number, records, status, retrieved = parse_shared_export(payload, start, end)
            rank = (status == "reached_start", datetime.fromisoformat(retrieved))
            if number not in latest or rank > (
                latest[number][1] == "reached_start", datetime.fromisoformat(latest[number][2])
            ):
                latest[number] = records, status, retrieved, path.name
    if not latest and not errors:
        raise ValueError("Shared-browser batches contain no flight exports")
    for number, (_, status, _, _) in latest.items():
        if status != "reached_start" and state["flights"].get(number, {}).get("status") == "reached_start":
            raise ValueError("Cannot replace completed history with a partial export; retain the full original batch")
    for number, (records, status, _, source) in latest.items():
        cache = f"flights\\{number}.json"
        atomic_json(run_dir / cache, records)
        state["flights"][number] = {
            "status": status, "records": len(records), "cache": cache,
            "collection_mode": "shared_browser_import", "export_file": source,
        }
        sources = state["candidates"].setdefault(number, [])
        provenance = f"shared-browser:{source}"
        if provenance not in sources:
            sources.append(provenance)
    state["collection_mode"] = "shared_browser_import"
    if errors:
        state["last_error"] = "\n".join(errors)
    return sorted(latest)


def shared_browser_code(
    numbers: list[str], start: date, max_pages: int = 30, delay: float = 5,
    intervals: dict[str, list[list[str]]] | None = None,
) -> str:
    """Generate a bounded browser-tool job; it reads only public flight-table data."""
    if not numbers or not all(FLIGHT_NUMBER.fullmatch(number) for number in numbers):
        raise ValueError("Supply valid flight numbers for the shared-browser job")
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    if not math.isfinite(delay) or delay < 2:
        raise ValueError("Shared-browser delay must be finite and at least two seconds")
    if intervals is not None:
        if set(intervals) != set(numbers):
            raise ValueError("Intervals must describe every selected flight number")
        for ranges in intervals.values():
            if not ranges:
                raise ValueError("Supply at least one requested interval")
            for first, last in ranges:
                if date.fromisoformat(first) < start or date.fromisoformat(last) < date.fromisoformat(first):
                    raise ValueError("Invalid shared-browser interval")
    settings = json.dumps({
        "numbers": numbers, "start": start.isoformat(), "maxPages": max_pages, "base": BASE,
        "delayMs": delay * 1000, "intervals": intervals,
    })
    return "return await (async (page) => {\nconst settings = " + settings + ";\nconst extract = " + EXTRACT_HISTORY + r""";
const exports = [];
let stopped = '';
for (const number of settings.numbers) {
    let rows = [], match = null;
    let status = 'page_limit';
    const url = settings.base + '/' + number.toLowerCase();
    const requested = settings.intervals ? settings.intervals[number] : null;
    const firstDate = requested ? requested.map(span => span[0]).sort()[0] : settings.start;
    const cutoff = Date.parse(firstDate + 'T00:00:00Z') / 1000 - 86400;
    const snapshot = () => ({
        schema_version:1, flight_number:number, airline_display:match[1], source_url:url,
        retrieved_at_utc:new Date().toISOString(), history_status:status, rows,
        ...(requested ? {requested_intervals:requested} : {})
    });
    try {
        if (page.url().split(/[?#]/)[0] !== url) {
            await page.waitForTimeout(settings.delayMs);
            const response = await page.goto(url, {waitUntil:'domcontentloaded', timeout:60000});
            if (response && response.status() >= 400)
                throw new Error('HTTP ' + response.status() + '; stopped, no bypass attempted');
        }
        const title = await page.title();
        if (/just a moment|access denied|captcha|security check|security verification/i.test(title))
            throw new Error('Access/security challenge; stopped');
        if (!page.url().startsWith(url))
            throw new Error('Unexpected redirect; stopped');
        await page.locator('#tbl-datatable tbody tr.data-row').first().waitFor({timeout:20000});
        const heading = await page.getByRole('heading', {
            name:new RegExp('^Flight history for .+ flight ' + number + '\\s*$', 'i')
        }).innerText();
        match = heading.trim().match(/^Flight history for (.+) flight ([A-Z0-9]+)$/i);
        if (!match || match[2].toUpperCase() !== number)
            throw new Error('Unexpected flight heading');
        rows = await page.evaluate(extract);
        for (let attempt = 0; attempt <= settings.maxPages; attempt++) {
            if (!rows.length || rows.some(r => !/^\d{9,10}$/.test(r.date_epoch)))
                throw new Error('Missing/invalid history dates');
            if (Math.min(...rows.map(r => Number(r.date_epoch))) < cutoff) {
                status = 'reached_start';
                break;
            }
            const earlier = page.locator('#btn-load-earlier-flights');
            if (!(await earlier.count()) || !(await earlier.isVisible()) || !(await earlier.isEnabled())) {
                status = 'history_exhausted_unverified';
                break;
            }
            if (attempt === settings.maxPages) break;
            const count = rows.length;
            await page.waitForTimeout(settings.delayMs);
            await earlier.click();
            await page.waitForFunction(
                n => document.querySelectorAll('#tbl-datatable tbody tr.data-row').length > n,
                count, {timeout:20000}
            );
            rows = await page.evaluate(extract);
        }
        exports.push(snapshot());
        if (status !== 'reached_start') {
            stopped = number + ': requested history boundary not reached; stopped';
            break;
        }
    } catch (error) {
        if (match && rows.length) exports.push(snapshot());
        stopped = number + ': ' + String(error.message || error);
        break;
    }
}
return {exports, stopped};
})(page);"""


def scheduled_instant(record: dict[str, str]) -> str:
    value = datetime.fromisoformat(record["scheduled_utc"].replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Scheduled UTC timestamps must include a timezone")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def event_key(record: dict[str, str]) -> tuple[str, ...]:
    return (
        record["flight_number"].upper(), record["origin_iata"], record["destination_iata"],
        record["direction"], scheduled_instant(record),
    )


def merge_master(
    master: list[dict[str, str]], observations: list[dict[str, str]],
) -> tuple[list[dict[str, str]], dict]:
    """Keep baseline values; ambiguous identity matches remain outside the CSV."""
    records = [row.copy() for row in master]
    source_index: dict[tuple[str, str], list[int]] = {}
    fallback_index: dict[tuple[str, ...], list[int]] = {}
    fallback_sources: dict[tuple[str, ...], set[str]] = {}
    report: dict = {"matched_observations": 0, "added_events": 0, "conflicts": [], "identity_review": [], "provenance": []}

    def index_row(row: dict[str, str], index: int) -> None:
        if row.get("flight_hex"):
            source_index.setdefault((row["flight_hex"].lower(), row["direction"]), []).append(index)
        fallback_index.setdefault(event_key(row), []).append(index)

    for row in master + observations:
        fallback_sources.setdefault(event_key(row), set()).add(row.get("flight_hex", "").lower())
    for index, row in enumerate(records):
        index_row(row, index)
    identifiers = {row["event_id"] for row in records}
    seen = set()
    ignored = {
        "event_id", "canonical_id", "retrieved_at_utc", "observation_count",
        "source_url", "source_urls", "flight_number", "flight_numbers",
        "identity_review", "identity_review_required", "conflict_fields",
    }
    for observation in observations:
        signature = tuple(sorted((key, value) for key, value in observation.items() if key != "retrieved_at_utc"))
        if signature in seen:
            continue
        seen.add(signature)
        key = event_key(observation)
        physical = observation.get("flight_hex", "").lower()
        matches = source_index.get((physical, observation["direction"]), []) if physical else []
        reason = ""
        if len(matches) > 1:
            reason = "Multiple events have the same source ID and direction"
        elif matches:
            original = records[matches[0]]
            if (original["origin_iata"], original["destination_iata"]) != key[1:3]:
                reason = "Source ID contradicts the route"
        else:
            candidates = fallback_index.get(key, [])
            matches = [
                index for index in candidates
                if not physical or not records[index].get("flight_hex")
                or records[index]["flight_hex"].lower() == physical
            ]
            known_sources = fallback_sources[key] - {""}
            unknown_match = any(not records[index].get("flight_hex") for index in matches)
            if len(matches) > 1 or (len(known_sources) > 1 and (not physical or unknown_match)):
                reason = "Ambiguous fallback identity"
        if reason:
            report["identity_review"].append({"reason": reason, "observation": observation})
            continue
        if matches:
            original = records[matches[0]]
            if physical and not original.get("flight_hex"):
                aliases = source_index.setdefault((physical, observation["direction"]), [])
                if matches[0] not in aliases:
                    aliases.append(matches[0])
            conflicts = {}
            for field, value in observation.items():
                previous = original.get(field, "")
                if field in ignored or not value or not previous or value == previous:
                    continue
                if field.endswith("_utc") or field == "scheduled_sha_local":
                    if datetime.fromisoformat(value.replace("Z", "+00:00")) == datetime.fromisoformat(previous.replace("Z", "+00:00")):
                        continue
                conflicts[field] = {"retained": previous, "observed": value}
            if conflicts:
                report["conflicts"].append({"event_id": original["event_id"], "fields": conflicts})
            report["matched_observations"] += 1
            report["provenance"].append({
                "event_id": original["event_id"], "source_url": observation.get("source_url", ""),
                "retrieved_at_utc": observation.get("retrieved_at_utc", ""),
                "flight_number": observation["flight_number"],
            })
        else:
            row = observation.copy()
            # Baseline IDs come from a different producer; new IDs must not collide.
            identity = ("fr24", physical, row["direction"]) if physical else ("fallback",) + key
            row["canonical_id"] = "sha_" + hashlib.sha256(repr(identity).encode()).hexdigest()[:24]
            row["event_id"] = row["canonical_id"] + ":" + row["direction"]
            if row["event_id"] in identifiers:
                raise ValueError("New event ID collides with an existing master ID")
            identifiers.add(row["event_id"])
            index_row(row, len(records))
            records.append(row)
            report["added_events"] += 1
    return records, report


def missing_intervals(start: date, end: date, covered: list[tuple[date, date]]) -> list[list[str]]:
    missing = []
    current = start
    for first, last in sorted(covered):
        if last < current or first > end:
            continue
        if first > current:
            missing.append([current.isoformat(), min(end, first - timedelta(days=1)).isoformat()])
        current = max(current, last + timedelta(days=1))
    if current <= end:
        missing.append([current.isoformat(), end.isoformat()])
    return missing


def combined_results(args: argparse.Namespace) -> int:
    """Rebuild from immutable inputs, producing an explicit resumable browser work queue."""
    if not args.start or not args.end or not args.output or not args.browser_export_dir:
        raise ValueError("Combined mode requires dates, output and --browser-export-dir")
    if not args.trusted_start or not args.trusted_end or args.trusted_end < args.trusted_start:
        raise ValueError("Combined mode requires an explicit valid --trusted-start/--trusted-end")
    if args.delay < 2:
        raise ValueError("Combined collection requires at least two seconds between actions")
    protected = {args.combine_master.resolve(), args.seed.resolve(), args.template.resolve(), (ROOT / "sha_master.csv").resolve()}
    if args.output.resolve() in protected:
        raise ValueError("Combined output must not overwrite an input or master")
    if args.output.suffix.lower() != ".csv":
        raise ValueError("Combined output must have a .csv extension")
    if args.profile or args.cookies or args.login or args.headless or args.discover or args.flight or args.limit:
        raise ValueError("Combined mode imports shared-browser data, not a local browser session")
    discovery = {
        "status": "unverified", "reason": "No historical airport enumeration/reference has been supplied",
    }
    if args.discovery_report:
        discovery = json.loads(args.discovery_report.read_text(encoding="utf-8"))
        if (not isinstance(discovery, dict) or discovery.get("airport") != "SHA"
                or discovery.get("start") != args.start.isoformat() or discovery.get("end") != args.end.isoformat()
                or discovery.get("status") not in {"blocked", "unverified"}
                or not isinstance(discovery.get("reason"), str) or not discovery["reason"].strip()):
            raise ValueError("Discovery report must describe blocked/unverified SHA discovery for these dates")
    with args.combine_master.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        fields = reader.fieldnames or []
        required = {"event_id", "scheduled_utc", "local_date", "direction", "flight_number", "origin_iata", "destination_iata"}
        if not required.issubset(fields):
            raise ValueError("Master lacks required event fields")
        master = []
        for row in reader:
            local = datetime.fromisoformat(scheduled_instant(row)).astimezone(SHA_ZONE).date()
            if row["local_date"] != local.isoformat():
                raise ValueError("Master local date disagrees with scheduled SHA event time")
            if args.start <= local <= args.end:
                master.append(row)
    if not master:
        raise ValueError("Master contains no records in the requested interval")
    baseline_days = {row["local_date"] for row in master}
    if any((args.trusted_start + timedelta(days=index)).isoformat() not in baseline_days
           for index in range((args.trusted_end - args.trusted_start).days + 1)):
        raise ValueError("Trusted baseline includes dates absent from master")
    candidates, routes = seed_candidates(args.combine_master)
    baseline_numbers = set(candidates)
    if args.candidate_file:
        extra, extra_routes = seed_candidates(args.candidate_file)
        for number, sources in extra.items():
            candidates.setdefault(number, []).extend(sources)
        routes |= extra_routes
    files = sorted(args.browser_export_dir.glob("*.json"))
    if args.review_export_dir:
        files += sorted(args.review_export_dir.glob("*.json"))
    observations: list[dict[str, str]] = []
    quarantine: list[dict] = []
    histories: dict[str, list[tuple[date, date]]] = {}
    extraction: dict[str, list[dict]] = {}
    errors = []
    inputs = {str(args.combine_master.resolve()): hashlib.sha256(args.combine_master.read_bytes()).hexdigest()}
    if args.candidate_file:
        inputs[str(args.candidate_file.resolve())] = hashlib.sha256(args.candidate_file.read_bytes()).hexdigest()
    if not args.browser_export_dir.is_dir() or (args.review_export_dir and not args.review_export_dir.is_dir()):
        raise ValueError("Shared-browser export directories must exist")
    for path in files:
        inputs[str(path.resolve())] = hashlib.sha256(path.read_bytes()).hexdigest()
        batch = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(batch, dict) or not isinstance(batch.get("exports"), list) or not isinstance(batch.get("stopped", ""), str):
            raise ValueError(f"Malformed shared-browser batch: {path.name}")
        if batch.get("stopped"):
            errors.append({"batch": str(path), "reason": batch["stopped"]})
        for payload in batch["exports"]:
            requested = payload.get("requested_intervals", [[args.start.isoformat(), args.end.isoformat()]]) if isinstance(payload, dict) else []
            if not isinstance(requested, list) or not requested:
                raise ValueError("Invalid requested intervals")
            spans = []
            for span in requested:
                if not isinstance(span, list) or len(span) != 2 or not all(isinstance(value, str) for value in span):
                    raise ValueError("Invalid requested interval")
                first, last = map(date.fromisoformat, span)
                if first < args.start or last > args.end or first > last:
                    raise ValueError("Requested interval lies outside collection dates")
                spans.append((first, last))
            rejected: list[dict] = []
            number, rows, status, retrieved = parse_shared_export(payload, min(first for first, _ in spans), args.end, rejected)
            observations.extend(row for row in rows if any(first.isoformat() <= row["local_date"] <= last.isoformat() for first, last in spans))
            quarantine.extend(dict(item, batch=str(path)) for item in rejected)
            candidates.setdefault(number, []).append(f"shared-browser:{path.name}")
            extraction.setdefault(number, []).append({
                "batch": str(path), "history_status": status, "requested_intervals": requested,
                "retrieved_at_utc": retrieved, "rejected_rows": len(rejected),
                "usable_coverage": "unresolved" if rejected else "extracted_not_census_verified",
                "oldest_history_epoch": min((
                    int(row.get("date_epoch", "")) for row in payload["rows"]
                    if re.fullmatch(r"[0-9]{9,10}", row.get("date_epoch", ""))
                ), default=None),
            })
            # A quarantined row cannot certify usable coverage of an undatable event.
            if status == "reached_start":
                histories.setdefault(number, []).extend(spans)
    records, merge = merge_master(master, observations)
    blocked = {}
    for error in errors:
        number = error["reason"].split(":", 1)[0].strip()
        if number in candidates:
            blocked[number] = error["reason"]
    queue = []
    for number in sorted(candidates):
        covered = list(histories.get(number, []))
        if number in baseline_numbers:
            covered.append((args.trusted_start, args.trusted_end))
        gaps = missing_intervals(args.start, args.end, covered)
        if gaps:
            queue.append({
                "flight_number": number, "intervals": gaps, "sources": sorted(set(candidates[number])),
                "status": "blocked" if number in blocked else "pending", "error": blocked.get(number, ""),
            })
    config = {
        "version": 1, "start": args.start.isoformat(), "end": args.end.isoformat(),
        "master": str(args.combine_master.resolve()), "master_sha256": inputs[str(args.combine_master.resolve())],
        "trusted_start": args.trusted_start.isoformat(), "trusted_end": args.trusted_end.isoformat(),
        "output": str(args.output.resolve()), "delay": args.delay,
    }
    checkpoint = args.run_dir / "checkpoint.json"
    if checkpoint.exists():
        old = json.loads(checkpoint.read_text(encoding="utf-8"))
        previous_config = {key: value for key, value in old["config"].items() if key != "delay"}
        current_config = {key: value for key, value in config.items() if key != "delay"}
        if not args.resume or previous_config != current_config:
            raise ValueError("Use --resume with the same combined configuration")
        for path, digest in old["input_hashes"].items():
            if path not in inputs:
                raise ValueError("Previously imported input is missing; retain all original batches")
            if Path(path).suffix.lower() == ".json" and inputs[path] != digest:
                raise ValueError("Previously imported raw batch changed; save new observations as a new batch")
    elif args.resume or any(path.exists() for path in (args.output, args.output.with_suffix(".coverage.json"), args.output.with_suffix(".review.json"))):
        raise ValueError("Missing combined checkpoint or output already exists")
    report = coverage_report(records, args.start, args.end, {"candidates": candidates, "routes": {}}, {}, [])
    report.update({
        "collection_mode": "shared_browser_combined", "master_rows_reused": len(master),
        "added_unique_events": merge["added_events"], "matched_observations": merge["matched_observations"],
        "trusted_baseline": {"start": args.trusted_start.isoformat(), "end": args.trusted_end.isoformat(), "independently_verified": False},
        "pending_numbers": [job["flight_number"] for job in queue], "pending_intervals": queue,
        "extraction_histories": extraction, "quarantined_rows": len(quarantine),
        "identity_review_observations": len(merge["identity_review"]),
        "conflicting_observations": len(merge["conflicts"]), "access_errors": errors,
        "historical_discovery_verified": False, "movement_reference_reconciled": False,
        "historical_discovery": discovery,
        "completed_candidate_numbers": sorted(set(candidates) - {job["flight_number"] for job in queue}),
        "usable_coverage_unresolved_numbers": sorted({row["flight_number"] for row in quarantine} | {item["observation"]["flight_number"] for item in merge["identity_review"]}),
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(records, key=lambda row: (scheduled_instant(row), row["event_id"])))
    temporary.replace(args.output)
    atomic_json(args.output.with_suffix(".review.json"), dict(merge, quarantine=quarantine))
    atomic_json(args.output.with_suffix(".coverage.json"), report)
    atomic_json(args.output.with_suffix(".candidates.json"), candidates)
    atomic_json(args.run_dir / "jobs.json", {"delay_seconds": args.delay, "jobs": queue})
    atomic_json(checkpoint, {"config": config, "input_hashes": inputs, "extraction": extraction, "access_errors": errors})
    print(f"Combined {len(master)} master rows with {merge['added_events']} new events: {len(records)} rows.")
    print(f"{len(queue)} flight numbers pending; {len(quarantine)} quarantined rows. Airport completeness remains unverified.")
    return 2 if queue or quarantine or merge["identity_review"] or errors or discovery["status"] == "blocked" else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--seed", type=Path, default=ROOT / "sha_master.csv")
    parser.add_argument("--routes", type=Path, help="Additional historical routes CSV")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--template", type=Path, default=ROOT / "sha_master.csv")
    parser.add_argument("--run-dir", type=Path, default=ROOT / ".flight-collection")
    parser.add_argument("--profile", type=Path, help="Dedicated Edge profile (not used with --cookies)")
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument("--login", action="store_true", help="Sign in manually, then press Enter in this terminal")
    auth.add_argument("--cookies", type=Path, help="Local Netscape cookie export; uses a temporary Edge session")
    auth.add_argument("--browser-export-dir", type=Path, help="Import shared-tab JSON batches without launching a browser")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--discover", action="store_true", help="Search seed/additional routes in both directions")
    parser.add_argument("--limit", type=int, help="Collect only the first N sorted candidates for a pilot")
    parser.add_argument("--flight", action="append", default=[], help="Select specific candidate flight number(s)")
    parser.add_argument("--delay", type=float, default=3, help="Minimum pause between page loads/history requests")
    parser.add_argument("--max-pages", type=int, default=30)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--combine-master", type=Path, help="Reuse a master CSV and import shared histories into a new combined output")
    parser.add_argument("--trusted-start", type=date.fromisoformat, help="Explicit start of the trusted master baseline")
    parser.add_argument("--trusted-end", type=date.fromisoformat, help="Explicit end of the trusted master baseline")
    parser.add_argument("--review-export-dir", type=Path, help="Additional raw shared-browser batches requiring row-level review")
    parser.add_argument("--candidate-file", type=Path, help="Additional historically discovered flight-number/route CSV")
    parser.add_argument("--discovery-report", type=Path, help="Explicit historical discovery/access limitations for the combined report")
    args = parser.parse_args(argv)
    if not math.isfinite(args.delay) or args.delay < 1:
        parser.error("--delay must be finite and at least 1 second")
    if args.max_pages < 1 or (args.limit is not None and args.limit < 1):
        parser.error("--max-pages and --limit must be positive")
    if args.login and args.headless:
        parser.error("--login requires a visible browser")
    if not args.login and (not args.start or not args.end or not args.output):
        parser.error("--start, --end and --output are required for collection")
    if args.start and args.end and args.end < args.start:
        parser.error("--end must not precede --start")
    if args.combine_master:
        return combined_results(args)
    if args.trusted_start or args.trusted_end or args.review_export_dir or args.candidate_file or args.discovery_report:
        parser.error("Trusted baseline/review/candidate options require --combine-master")
    if args.browser_export_dir and (args.profile or args.headless or args.discover or args.flight or args.limit):
        parser.error("--browser-export-dir imports existing batches; do not combine it with browser/selection options")
    if args.cookies and args.profile:
        parser.error("--cookies cannot be combined with --profile")
    args.profile = args.profile or Path.home() / ".sha-flight-edge-browser"
    if args.profile.resolve() == ROOT or ROOT in args.profile.resolve().parents:
        parser.error("--profile must be outside the repository to protect login credentials")
    if args.output and args.output.resolve() in {args.seed.resolve(), args.template.resolve(), (ROOT / "sha_master.csv").resolve()}:
        parser.error("Output must be a new dataset, not the seed, template or master")
    if args.output and args.output.suffix.lower() != ".csv":
        parser.error("--output must have a .csv extension")
    cookie_jar = read_session_cookies(args.cookies) if args.cookies else None
    if args.login:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            with playwright.chromium.launch_persistent_context(
                str(args.profile), channel="msedge", headless=False, chromium_sandbox=True,
            ) as context:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(BASE)
                input("Sign in manually in the browser, then press Enter here to close and save the profile: ")
                require_paid_session(page)
        print("Browser profile saved locally. Never share or commit this profile.")
        return 0

    config = {
        "version": 1, "airport": "SHA", "start": args.start.isoformat(), "end": args.end.isoformat(),
        "output": str(args.output.resolve()), "template": str(args.template.resolve()),
    }
    state_path = args.run_dir / "checkpoint.json"
    if args.resume:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["config"] != config:
            raise ValueError("Checkpoint belongs to another date range/output/template")
    else:
        if state_path.exists() or any(
            path.exists() for path in (
                args.output, args.output.with_suffix(".coverage.json"), args.output.with_suffix(".candidates.json")
            )
        ):
            raise ValueError("Output/checkpoint already exists. Use --resume or new output and run directory.")
        state = {"config": config, "candidates": {}, "routes": {}, "flights": {}}
    candidates, routes = seed_candidates(args.seed)
    for number in args.flight:
        number = number.upper()
        if not FLIGHT_NUMBER.fullmatch(number):
            raise ValueError(f"Invalid --flight: {number}")
        candidates.setdefault(number, []).append("explicit")
    for number, sources in candidates.items():
        state["candidates"][number] = sorted(set(state["candidates"].get(number, [])) | set(sources))
    if args.routes:
        routes |= read_routes(args.routes)
    state.pop("last_error", None)
    atomic_json(state_path, state)
    selected: list[str] = []
    exit_code = 0
    if args.browser_export_dir:
        selected = import_shared_exports(args.browser_export_dir, args.run_dir, state, args.start, args.end)
        atomic_json(state_path, state)
        count = export_results(args.output, args.template, args.run_dir, state, args.start, args.end, selected)
        print(f"Imported shared-browser tables: {count} events to {args.output}. No browser was launched.")
        return 2 if state.get("last_error") or any(
            item.get("status") != "reached_start" for item in state["flights"].values()
        ) else 0
    from playwright.sync_api import Error as BrowserError, sync_playwright

    try:
        with sync_playwright() as playwright:
            with ExitStack() as resources:
                if cookie_jar is not None:
                    browser = resources.enter_context(
                        playwright.chromium.launch(
                            channel="msedge", headless=args.headless, chromium_sandbox=True,
                        )
                    )
                    context = resources.enter_context(browser.new_context(viewport={"width": 1440, "height": 1000}))
                    import_session_cookies(context, cookie_jar)
                    print(f"Imported {len(cookie_jar)} Flightradar24 cookies into a temporary Edge session.")
                else:
                    context = resources.enter_context(playwright.chromium.launch_persistent_context(
                        str(args.profile), channel="msedge", headless=args.headless, chromium_sandbox=True,
                        viewport={"width": 1440, "height": 1000},
                    ))
                page = context.pages[0] if context.pages else context.new_page()
                page.set_default_timeout(20000)
                checked_navigation(page, BASE, args.delay)
                require_paid_session(page)
                if args.discover:
                    if not routes:
                        raise ValueError("No routes available; use the master as seed or supply --routes")
                    for origin, destination in sorted(routes):
                        key = f"{origin}-{destination}"
                        if state["routes"].get(key, {}).get("status") == "searched":
                            continue
                        try:
                            numbers, count = discover_route(page, origin, destination, args.delay)
                            for number in numbers:
                                sources = state["candidates"].setdefault(number, [])
                                if f"route:{key}" not in sources:
                                    sources.append(f"route:{key}")
                            state["routes"][key] = {
                                "status": "searched", "suggestion_rows": count,
                                "potentially_truncated": True, "flight_numbers": numbers,
                            }
                            print(f"Discovered {key}: {len(numbers)} numbers ({count} suggestions; may be capped)", flush=True)
                        except AccessRestricted as error:
                            state["routes"][key] = {"status": "blocked", "error": str(error)}
                            raise
                        except ValueError as error:
                            assert_access(page)
                            state["routes"][key] = {"status": "failed", "error": str(error)}
                            print(f"Discovery failed {key}: {error}", file=sys.stderr, flush=True)
                            exit_code = 2
                        except BrowserError as error:
                            state["routes"][key] = {"status": "failed", "error": str(error)}
                            raise AccessRestricted(
                                f"Route search failed for {key}; stopped to avoid retrying access limits. {error}"
                            ) from error
                        atomic_json(state_path, state)
                selected = sorted(set(n.upper() for n in args.flight) if args.flight else state["candidates"])
                if args.limit:
                    selected = selected[:args.limit]
                for number in selected:
                    if state["flights"].get(number, {}).get("status") == "reached_start":
                        continue
                    try:
                        records, status = collect_history(
                            page, number, args.start, args.end, args.delay, args.max_pages
                        )
                        cache = f"flights\\{number}.json"
                        atomic_json(args.run_dir / cache, records)
                        state["flights"][number] = {"status": status, "records": len(records), "cache": cache}
                        print(f"{number}: {len(records)} observations; {status}", flush=True)
                        if status != "reached_start":
                            exit_code = 2
                    except AccessRestricted as error:
                        state["flights"].setdefault(number, {}).update({"status": "blocked", "error": str(error)})
                        raise
                    except ValueError as error:
                        assert_access(page)
                        state["flights"].setdefault(number, {}).update({"status": "failed", "error": str(error)})
                        print(f"History failed {number}: {error}", file=sys.stderr, flush=True)
                        exit_code = 2
                    except BrowserError as error:
                        state["flights"].setdefault(number, {}).update({"status": "failed", "error": str(error)})
                        raise AccessRestricted(
                            f"History request failed for {number}; stopped to avoid retrying access limits. {error}"
                        ) from error
                    atomic_json(state_path, state)
    except (AccessRestricted, BrowserError) as error:
        state["last_error"] = str(error)
        print(f"Collection stopped: {error}", file=sys.stderr)
        exit_code = 2
    except KeyboardInterrupt:
        state["last_error"] = "Interrupted by user; checkpoint saved"
        print(state["last_error"], file=sys.stderr)
        exit_code = 130
    finally:
        atomic_json(state_path, state)
        count = export_results(args.output, args.template, args.run_dir, state, args.start, args.end, selected)
        print(f"Exported {count} events to {args.output}. Coverage is not a complete airport census.")
    if exit_code == 0 and (
        any(item.get("status") != "searched" for item in state["routes"].values())
        or any(item.get("status") != "reached_start" for item in state["flights"].values())
    ):
        exit_code = 2
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, csv.Error, AccessRestricted) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
