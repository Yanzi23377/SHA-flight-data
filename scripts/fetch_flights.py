"""Import saved or HTTP-fetched flight-page tables into the sha_master schema."""

from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = ROOT / "sha_master.csv"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

ALIASES = {
    "flight_number": {"flight number", "flight no", "flight"},
    "status_display": {"status", "flight status"},
    "origin_iata": {"origin", "from", "origin airport"},
    "destination_iata": {"destination", "to", "destination airport"},
    "route": {"route"},
    "airline_display": {"airline", "airline name"},
    "aircraft_display": {"aircraft", "aircraft type"},
    "registration": {"registration", "aircraft registration"},
    "scheduled_departure_display": {
        "scheduled departure",
        "scheduled departure time",
        "std",
    },
    "actual_departure_display": {
        "actual departure",
        "actual departure time",
        "atd",
    },
    "scheduled_arrival_display": {
        "scheduled arrival",
        "scheduled arrival time",
        "sta",
    },
    "scheduled_departure_utc": {"scheduled departure utc"},
    "actual_departure_utc": {"actual departure utc"},
    "scheduled_arrival_utc": {"scheduled arrival utc"},
    "actual_event_utc": {"actual event utc", "actual arrival utc"},
    "scheduled_utc": {"scheduled utc", "scheduled event utc"},
    "scheduled_sha_local": {"scheduled sha local"},
    "landed_status_utc": {"landed status utc"},
    "status_event_utc": {"status event utc"},
    "flight_hex": {"flight hex"},
    "schedule_id": {"schedule id"},
    "departure_utc_offset_seconds": {"departure utc offset seconds"},
    "arrival_utc_offset_seconds": {"arrival utc offset seconds"},
}

ALIASES_TO_FIELD = {
    re.sub(r"[^a-z0-9]+", " ", alias.casefold()).strip(): field
    for field, aliases in ALIASES.items()
    for alias in aliases
}


class TableParser(HTMLParser):
    """Read visible text from HTML table rows without loading remote resources."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._table_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table_depth += 1
        elif self._table_depth and tag == "tr":
            self._row = []
        elif self._row is not None and tag in {"td", "th"}:
            self._cell = []
        elif self._cell is not None and tag == "br":
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            self._table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def mapped_fields(rows: Iterable[list[str]], source: Path) -> dict[str, str]:
    rows = list(rows)
    result: dict[str, str] = {}
    for index, row in enumerate(rows):
        if len(row) < 2:
            continue

        headers = [ALIASES_TO_FIELD.get(normalize_label(cell)) for cell in row]
        if sum(header is not None for header in headers) >= 2 and index + 1 < len(rows):
            data_row = rows[index + 1]
            for field, value in zip(headers, data_row):
                if field and value.strip():
                    result[field] = value.strip()
            continue

        label = normalize_label(row[0])
        field = ALIASES_TO_FIELD.get(label)
        if field and row[1].strip():
            result[field] = row[1].strip()

    if not result:
        raise ValueError(f"No recognized flight fields found in HTML tables: {source}")
    return result


def read_manifest(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or not {"file", "source_url"}.issubset(reader.fieldnames):
            raise ValueError("Manifest CSV must have columns named 'file' and 'source_url'.")
        entries = {}
        for row in reader:
            filename = (row.get("file") or "").strip()
            url = (row.get("source_url") or "").strip()
            if not filename or not url:
                raise ValueError("Every manifest row must include a file and source_url.")
            if filename in entries:
                raise ValueError(f"Duplicate filename in manifest: {filename}")
            entries[filename] = url
        return entries


def flight_number_from_url(url: str) -> str:
    parts = urlsplit(url)
    match = re.fullmatch(r"/data/flights/([a-zA-Z0-9]+)(?:/)?", parts.path)
    if (
        parts.scheme != "https"
        or parts.netloc.lower() not in {"www.flightradar24.com", "flightradar24.com"}
        or not match
    ):
        raise ValueError(
            "Use an HTTPS Flightradar24 flight URL such as "
            "https://www.flightradar24.com/data/flights/mu5101, not the flight search page."
        )
    return match.group(1).upper()


def fetch_page(url: str, timeout: float) -> tuple[str, str]:
    """Perform one ordinary GET; do not retry or bypass access restrictions."""
    flight_number_from_url(url)
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                raise ValueError(f"Expected an HTML response from {url}")
            html = response.read().decode(
                response.headers.get_content_charset() or "utf-8", errors="replace"
            )
    except HTTPError as error:
        raise ValueError(
            f"HTTP {error.code} fetching {url}; access may be restricted. "
            "No access-control bypass is attempted."
        ) from error
    except (URLError, TimeoutError) as error:
        raise ValueError(f"Could not fetch {url}: {error}") from error
    return html, datetime.now(timezone.utc).isoformat()


def parse_flight_history(html: str, url: str) -> list[dict[str, str]]:
    """Parse each visible history row, without interpreting local times as UTC."""
    flight_number = flight_number_from_url(url)
    table = TableParser()
    table.feed(html)
    table.close()
    headers: list[str | None] = []
    records: list[dict[str, str]] = []
    for row in table.rows:
        labels = [normalize_label(cell) for cell in row]
        if {"from", "to", "std", "sta", "status"}.issubset(labels):
            headers = [ALIASES_TO_FIELD.get(label) for label in labels]
            continue
        if not headers or len(row) != len(headers):
            continue
        values = {
            field: value.strip()
            for field, value in zip(headers, row)
            if field and value.strip() not in {"", "-", "N/A"}
        }
        for field in ("origin_iata", "destination_iata"):
            airport = values.get(field, "")
            match = re.search(r"\(([A-Z]{3})\)", airport)
            values[field] = (
                match.group(1) if match
                else airport if re.fullmatch(r"[A-Z]{3}", airport)
                else ""
            )
        if not values["origin_iata"] or not values["destination_iata"]:
            continue
        values["flight_number"] = flight_number
        records.append(values)
    if not records:
        raise ValueError(
            f"No usable flight-history rows found at {url}. The page may require "
            "JavaScript, authentication, or have a different layout. "
            "No CSV was written."
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import saved HTML or fetch Flightradar24 flight-history pages into CSV."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--html-dir", type=Path, help="Directory of saved .html/.htm files")
    mode.add_argument("--url", action="append", help="Flight-history URL to fetch; repeat for multiple flights")
    parser.add_argument("--manifest", type=Path, help="CSV containing file,source_url columns (saved-page mode)")
    parser.add_argument("--timeout", type=float, default=30, help="HTTP timeout in seconds (default: 30)")
    parser.add_argument("--output", type=Path, default=Path("sha_imported.csv"))
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="CSV used for output column order")
    args = parser.parse_args()

    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a finite positive number")
    if args.html_dir and not args.manifest:
        parser.error("--manifest is required with --html-dir")
    if args.url and args.manifest:
        parser.error("--manifest is only used with --html-dir")
    if args.html_dir and not args.html_dir.is_dir():
        parser.error(f"HTML directory does not exist: {args.html_dir}")
    if not args.template.is_file():
        parser.error(f"CSV template does not exist: {args.template}")

    with args.template.open(newline="", encoding="utf-8-sig") as template:
        fieldnames = next(csv.reader(template), None)
    if not fieldnames:
        parser.error(f"CSV template has no header row: {args.template}")
    inputs: list[tuple[dict[str, str], str, str, str]] = []
    if args.url:
        for url in args.url:
            flight_number_from_url(url)
        for url in args.url:
            html, retrieved_at = fetch_page(url, args.timeout)
            for index, values in enumerate(parse_flight_history(html, url), start=1):
                inputs.append((values, url, f"remote:{values['flight_number']}:{index}", retrieved_at))
    else:
        manifest = read_manifest(args.manifest)
        files = sorted(
            path for path in args.html_dir.iterdir()
            if path.is_file() and path.suffix.casefold() in {".html", ".htm"}
        )
        if not files:
            parser.error(f"No .html or .htm files found in {args.html_dir}")
        missing_urls = [path.name for path in files if path.name not in manifest]
        if missing_urls:
            parser.error("Missing source_url manifest entries for: " + ", ".join(missing_urls))
        for path in files:
            parser_instance = TableParser()
            parser_instance.feed(path.read_text(encoding="utf-8", errors="replace"))
            values = mapped_fields(parser_instance.rows, path)
            inputs.append((values, manifest[path.name], f"local:{path.stem}", ""))

    records: list[dict[str, str]] = []
    for values, source_url, identifier, retrieved_at in inputs:
        record = dict.fromkeys(fieldnames, "")
        record.update(values)
        flight_number = values.get("flight_number", "")
        route = values.get("route", "")
        if not route and values.get("origin_iata") and values.get("destination_iata"):
            route = f"{values['origin_iata']}-{values['destination_iata']}"
        record["route"] = route
        if "direction" in record:
            record["direction"] = (
                "arrival" if values.get("destination_iata", "").upper() == "SHA"
                else "departure" if values.get("origin_iata", "").upper() == "SHA"
                else ""
            )
        if "source_url" in record:
            record["source_url"] = source_url
        if "source_urls" in record:
            record["source_urls"] = source_url
        if "retrieved_at_utc" in record:
            record["retrieved_at_utc"] = retrieved_at
        if "timing_semantics_verified" in record:
            record["timing_semantics_verified"] = "false"
        if "operating_carrier_verified" in record:
            record["operating_carrier_verified"] = "false"
        if "observation_count" in record:
            record["observation_count"] = "1"
        if "event_id" in record:
            record["event_id"] = f"{identifier}:{flight_number}"
        if "canonical_id" in record:
            record["canonical_id"] = f"{identifier}:{flight_number}"
        records.append(record)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    print(f"Wrote {len(records)} parsed record(s) to {args.output}")
    print("Unrecognized or absent fields remain blank; timing semantics are unverified.")
    if not args.url:
        print("No network requests were made. retrieved_at_utc is left blank for local files.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError, csv.Error) as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
