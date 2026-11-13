import csv
import json
import tempfile
import time
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import collect_flights as collector


START = date(2026, 9, 1)
END = date(2026, 10, 31)


def stamp(text):
    return str(int(datetime.fromisoformat(text).timestamp()))


def raw_row(**changes):
    row = {
        "date_epoch": stamp("2026-09-01T00:00:00+00:00"),
        "origin_iata": "SHA",
        "destination_iata": "PEK",
        "scheduled_departure_epoch": stamp("2026-09-01T00:00:00+00:00"),
        "scheduled_arrival_epoch": stamp("2026-09-01T02:00:00+00:00"),
        "actual_departure_epoch": stamp("2026-09-01T00:10:00+00:00"),
        "status_epoch": stamp("2026-09-01T02:05:00+00:00"),
        "status_display": "Landed 10:05 AM",
        "scheduled_departure_display": "8:00 AM",
        "actual_departure_display": "8:10 AM",
        "scheduled_arrival_display": "10:00 AM",
        "flight_hex": "abcdef12",
        "aircraft_display": "A320 (B-1234)",
        "registration": "B-1234",
        "departure_utc_offset_seconds": "28800",
        "arrival_utc_offset_seconds": "28800",
    }
    row.update(changes)
    return row


def maybe_record(raw=None, number="MU5101"):
    return collector.history_record(
        raw if raw is not None else raw_row(), number, "Test airline", START, END,
        "2026-11-13T00:00:00+00:00",
    )


def record(raw=None, number="MU5101"):
    value = maybe_record(raw, number)
    assert value is not None, "Expected an in-range SHA event"
    return value


class HistoryRecordTests(unittest.TestCase):
    def test_sha_date_boundaries_and_arrival_time_basis(self):
        arrival = raw_row(
            origin_iata="PEK", destination_iata="SHA",
            scheduled_departure_epoch=stamp("2026-08-31T14:00:00+00:00"),
            scheduled_arrival_epoch=stamp("2026-08-31T16:00:00+00:00"),
        )
        result = record(arrival)
        self.assertEqual(result["local_date"], "2026-09-01")
        self.assertEqual(result["direction"], "arrival")
        self.assertEqual(result["scheduled_utc"], "2026-08-31T16:00:00Z")
        self.assertEqual(result["actual_event_utc"], "2026-09-01T02:05:00Z")
        before = raw_row(scheduled_departure_epoch=stamp("2026-08-31T15:59:59+00:00"))
        after = raw_row(scheduled_departure_epoch=stamp("2026-10-31T16:00:00+00:00"))
        last = raw_row(scheduled_departure_epoch=stamp("2026-10-31T15:59:59+00:00"))
        self.assertIsNone(maybe_record(before))
        self.assertIsNone(maybe_record(after))
        self.assertEqual(record(last)["local_date"], "2026-10-31")

    def test_cancelled_and_estimated_arrivals_are_not_actual_arrivals(self):
        for status in ("Cancelled", "Estimated arrival 10:05"):
            result = record(raw_row(
                origin_iata="PEK", destination_iata="SHA", status_display=status,
                actual_departure_epoch="",
            ))
            self.assertEqual(result["actual_event_utc"], "")
            self.assertEqual(result["landed_status_utc"], "")
            self.assertEqual(result["timing_difference_minutes"], "")
            self.assertEqual(result["timing_semantics_verified"], "false")
            self.assertNotIn("operating_carrier", result)

    def test_missing_sha_timestamp_and_malformed_airports_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "scheduled timestamp"):
            record(raw_row(scheduled_departure_epoch=""))
        with self.assertRaisesRegex(ValueError, "airports"):
            record(raw_row(origin_iata=""))
        with self.assertRaisesRegex(ValueError, "Unix timestamp"):
            record(raw_row(scheduled_departure_epoch="8:00 AM"))
        self.assertIsNone(maybe_record(raw_row(origin_iata="PVG")))

    def test_stable_ids_codeshares_and_conflicts(self):
        first = record()
        second = record(number="FM9999")
        second["scheduled_utc"] = "2026-09-01T00:05:00Z"
        merged = collector.deduplicate([first, second])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["flight_numbers"], "FM9999;MU5101")
        self.assertEqual(merged[0]["observation_count"], "2")
        self.assertIn("scheduled_utc", merged[0]["conflict_fields"])
        self.assertEqual(merged[0]["identity_review_required"], "true")
        self.assertEqual(first["event_id"], record()["event_id"])
        self.assertEqual(first["scheduled_utc"], "2026-09-01T00:00:00Z")

    def test_fallback_does_not_merge_codeshares_or_arrivals_on_different_dates(self):
        first = raw_row(
            flight_hex="", origin_iata="PEK", destination_iata="SHA",
            scheduled_departure_epoch="",
        )
        second = dict(first, scheduled_arrival_epoch=stamp("2026-09-02T02:00:00+00:00"))
        records = [record(first), record(first, number="FM9999"), record(second)]
        self.assertEqual(len(collector.deduplicate(records)), 3)
        self.assertTrue(all(row["identity_review_required"] == "true" for row in records))


class PersistenceTests(unittest.TestCase):
    def test_seed_discovers_codeshares_and_both_route_directions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "seed.csv"
            path.write_text(
                "flight_number,flight_numbers,origin_iata,destination_iata\n"
                "MU5101,MU5101;FM9999,SHA,PEK\nCA1234,CA1234,PVG,PEK\n",
                encoding="utf-8",
            )
            candidates, routes = collector.seed_candidates(path)
            self.assertEqual(set(candidates), {"MU5101", "FM9999"})
            self.assertEqual(routes, {("SHA", "PEK"), ("PEK", "SHA")})

    def test_export_resume_is_idempotent_and_reports_missing_days(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "new.csv"
            cached = root / "flights" / "MU5101.json"
            collector.atomic_json(cached, [record(), record()])
            state = {
                "candidates": {"MU5101": ["seed"]}, "routes": {},
                "flights": {"MU5101": {"status": "page_limit", "cache": "flights/MU5101.json"}},
            }
            template = collector.ROOT / "sha_master.csv"
            for _ in range(2):
                self.assertEqual(collector.export_results(output, template, root, state, START, END, ["MU5101"]), 1)
                with output.open(newline="", encoding="utf-8") as source:
                    rows = list(csv.DictReader(source))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["observation_count"], "2")
            coverage = json.loads(output.with_suffix(".coverage.json").read_text(encoding="utf-8"))
            self.assertEqual(len(coverage["daily_counts"]), 61)
            self.assertEqual(len(coverage["missing_dates"]), 60)
            self.assertFalse(coverage["complete_airport_census"])
            self.assertEqual(coverage["flights"]["MU5101"]["status"], "page_limit")

    def test_master_output_and_repository_profile_are_rejected_before_launch(self):
        for arguments in (
            ["--output", str(collector.ROOT / "sha_master.csv")],
            ["--output", "new.csv", "--profile", str(collector.ROOT / "profile")],
        ):
            with self.subTest(arguments=arguments), self.assertRaises(SystemExit) as result:
                collector.main(["--start", "2026-09-01", "--end", "2026-10-31"] + arguments)
            self.assertEqual(result.exception.code, 2)


class CookieFileTests(unittest.TestCase):
    def test_cookie_export_filters_domains_expiration_and_preserves_flags(self):
        future = str(int(time.time()) + 3600)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                f"#HttpOnly_.flightradar24.com\tTRUE\t/\tTRUE\t{future}\tauth\tdummy-session\n"
                "www.flightradar24.com\tFALSE\t/data\tFALSE\t\tpreference\tdummy-setting\n"
                "www.flightradar24.com\tFALSE\t/\tTRUE\t0\tsession-zero\tdummy-zero\n"
                "www.flightradar24.com\tFALSE\t/\tTRUE\t1\texpired\tdummy-expired\n"
                f"accounts.example.com\tFALSE\t/\tTRUE\t{future}\tunrelated\tdummy-unrelated\n"
                f"evilflightradar24.com\tFALSE\t/\tTRUE\t{future}\twrong\tdummy-wrong\n",
                encoding="utf-8",
            )
            jar = collector.read_session_cookies(path)
            cookies = {cookie.name: cookie for cookie in jar}
            self.assertEqual(set(cookies), {"auth", "preference", "session-zero"})
            self.assertTrue(cookies["auth"].has_nonstandard_attr("HTTPOnly"))
            self.assertTrue(cookies["auth"].secure)
            self.assertIsNone(cookies["preference"].expires)
            self.assertIsNone(cookies["session-zero"].expires)

    def test_invalid_export_errors_do_not_echo_cookie_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\ninvalid-line-with-dummy-session-value\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "cookie contents withheld") as result:
                collector.read_session_cookies(path)
            self.assertNotIn("dummy-session-value", str(result.exception))
            self.assertTrue(result.exception.__suppress_context__)
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                "www.flightradar24.com\tFALSE\t/\tTRUE\t1\texpired\tdummy-value\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "no unexpired"):
                collector.read_session_cookies(path)
            with self.assertRaisesRegex(ValueError, "does not exist"):
                collector.read_session_cookies(path.parent / "missing.txt")

    def test_cookie_mode_rejects_profile_and_login(self):
        arguments = [
            "--start", "2026-09-01", "--end", "2026-10-31", "--output", "new.csv",
        ]
        for extra in (
            ["--cookies", "outside.txt", "--profile", str(Path.home() / "profile")],
            ["--cookies", "outside.txt", "--login"],
        ):
            with self.subTest(extra=extra), self.assertRaises(SystemExit) as result:
                collector.main(arguments + extra)
            self.assertEqual(result.exception.code, 2)

    def test_repository_cookie_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cookies = root / "fr24-cookies.txt"
            with patch.object(collector, "ROOT", root), patch.object(
                collector, "read_session_cookies", side_effect=ValueError("Synthetic loader reached")
            ) as loader:
                with self.assertRaisesRegex(ValueError, "Synthetic loader reached"):
                    collector.main([
                        "--start", "2026-09-01", "--end", "2026-10-31",
                        "--cookies", str(cookies), "--output", str(root / "new.csv"),
                    ])
                loader.assert_called_once_with(cookies)


def shared_export(status="reached_start"):
    older = raw_row(
        date_epoch=stamp("2026-08-26T00:00:00+00:00"),
        scheduled_departure_epoch=stamp("2026-08-26T00:00:00+00:00"),
    )
    return {
        "schema_version": 1, "flight_number": "MU5101",
        "source_url": collector.BASE + "/mu5101", "airline_display": "Test airline",
        "retrieved_at_utc": "2026-11-13T03:00:00Z",
        "history_status": status, "rows": [raw_row(), older],
    }


class SharedBrowserImportTests(unittest.TestCase):
    def test_imports_and_resumes_without_launching_a_browser_or_reading_cookies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            collector.atomic_json(exports / "batch.json", {"exports": [shared_export()], "stopped": ""})
            seed = root / "seed.csv"
            seed.write_text("flight_number\nMU5101\nCA1502\n", encoding="utf-8")
            output = root / "new.csv"
            args = [
                "--browser-export-dir", str(exports), "--seed", str(seed),
                "--start", "2026-09-01", "--end", "2026-10-31",
                "--output", str(output), "--run-dir", str(root / "run"),
            ]
            with patch("playwright.sync_api.sync_playwright") as browser, patch.object(
                collector, "read_session_cookies"
            ) as cookies, patch.dict("sys.modules", {"playwright.sync_api": None}):
                for resume in ([], ["--resume"]):
                    self.assertEqual(collector.main(args + resume), 0)
                    with output.open(newline="", encoding="utf-8") as source:
                        rows = list(csv.DictReader(source))
                    self.assertEqual(len(rows), 1)
                    self.assertEqual(rows[0]["observation_count"], "1")
                browser.assert_not_called()
                cookies.assert_not_called()
            report = json.loads(output.with_suffix(".coverage.json").read_text(encoding="utf-8"))
            self.assertEqual(report["collection_mode"], "shared_browser_import")
            self.assertEqual(report["pending_numbers"], ["CA1502"])
            self.assertFalse(report["complete_airport_census"])

    def test_rejects_unsubstantiated_coverage_and_mismatched_flight_url(self):
        payload = shared_export()
        payload["rows"] = [raw_row()]
        with self.assertRaisesRegex(ValueError, "claimed start-date coverage"):
            collector.parse_shared_export(payload, START, END)
        payload = shared_export()
        payload["source_url"] = collector.BASE + "/ca1502"
        with self.assertRaisesRegex(ValueError, "must agree"):
            collector.parse_shared_export(payload, START, END)

    def test_reports_partial_worker_failure_instead_of_claiming_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            collector.atomic_json(exports / "batch.json", {
                "exports": [shared_export("page_limit")], "stopped": "CA1502: HTTP 403; stopped",
            })
            state = {"candidates": {}, "routes": {}, "flights": {}}
            selected = collector.import_shared_exports(exports, root / "run", state, START, END)
            self.assertEqual(selected, ["MU5101"])
            self.assertEqual(state["flights"]["MU5101"]["status"], "page_limit")
            self.assertIn("HTTP 403", state["last_error"])

    def test_malformed_batch_does_not_replace_valid_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            collector.atomic_json(exports / "a.json", {"exports": [shared_export()], "stopped": ""})
            collector.atomic_json(exports / "b.json", {"exports": [{"schema_version": 99}]})
            cache = root / "run" / "flights" / "MU5101.json"
            collector.atomic_json(cache, [record()])
            before = cache.read_bytes()
            state = {"candidates": {}, "routes": {}, "flights": {}}
            with self.assertRaisesRegex(ValueError, "version 1"):
                collector.import_shared_exports(exports, root / "run", state, START, END)
            self.assertEqual(cache.read_bytes(), before)
            self.assertEqual(state["flights"], {})

    def test_new_partial_snapshot_cannot_discard_completed_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            collector.atomic_json(exports / "full.json", {"exports": [shared_export()]})
            state = {"candidates": {}, "routes": {}, "flights": {}}
            collector.import_shared_exports(exports, root / "run", state, START, END)
            partial = shared_export("page_limit")
            partial["retrieved_at_utc"] = "2026-11-14T03:00:00Z"
            partial["rows"] = [raw_row()]
            collector.atomic_json(exports / "partial.json", {"exports": [partial]})
            collector.import_shared_exports(exports, root / "run", state, START, END)
            self.assertEqual(state["flights"]["MU5101"]["status"], "reached_start")
            self.assertEqual(state["flights"]["MU5101"]["export_file"], "full.json")
            (exports / "full.json").unlink()
            with self.assertRaisesRegex(ValueError, "Cannot replace completed history"):
                collector.import_shared_exports(exports, root / "run", state, START, END)


class CombinedCollectionTests(unittest.TestCase):
    def test_merge_matches_producer_ids_and_timestamp_formats_without_changing_master(self):
        baseline = dict(record(), event_id="legacy-id", canonical_id="legacy",
                        scheduled_utc="2026-09-01T00:00:00.000Z", registration="B-OLD")
        observed = record(raw_row(registration="B-NEW"))
        merged, report = collector.merge_master([baseline], [observed, observed])
        self.assertEqual(merged, [baseline])
        self.assertEqual(report["matched_observations"], 1)
        self.assertEqual(report["conflicts"][0]["fields"], {
            "registration": {"retained": "B-OLD", "observed": "B-NEW"},
        })
        self.assertEqual(report["provenance"][0]["event_id"], "legacy-id")

    def test_distinct_source_ids_are_preserved_and_ambiguous_fallback_is_reviewed(self):
        first = record()
        second = record(raw_row(flight_hex="different"))
        unknown = record(raw_row(flight_hex=""))
        merged, report = collector.merge_master([], [first, second, unknown])
        self.assertEqual(len(merged), 2)
        self.assertEqual(len(report["identity_review"]), 1)
        self.assertEqual(report["identity_review"][0]["reason"], "Ambiguous fallback identity")
        self.assertNotEqual(merged[0]["event_id"], merged[1]["event_id"])

    def test_unambiguous_fallback_matches_and_contradictory_route_is_not_merged(self):
        baseline = record(raw_row(flight_hex=""))
        observed = record()
        merged, report = collector.merge_master([baseline], [observed])
        self.assertEqual(merged, [baseline])
        self.assertEqual(report["matched_observations"], 1)
        merged, report = collector.merge_master([record()], [record(raw_row(destination_iata="CAN"))])
        self.assertEqual(len(merged), 1)
        self.assertIn("contradicts", report["identity_review"][0]["reason"])

    def test_source_alias_can_link_codeshares_without_mutating_baseline(self):
        baseline = record(raw_row(flight_hex=""))
        merged, report = collector.merge_master([baseline], [
            record(), record(number="FM9999"), record(number="MU9999"),
        ])
        self.assertEqual(merged, [baseline])
        self.assertEqual(report["matched_observations"], 3)
        self.assertEqual(report["identity_review"], [])

    def test_unknown_baseline_cannot_absorb_two_distinct_source_events(self):
        baseline = record(raw_row(flight_hex=""))
        merged, report = collector.merge_master([baseline], [
            record(), record(raw_row(flight_hex="different")),
        ])
        self.assertEqual(merged, [baseline])
        self.assertEqual(len(report["identity_review"]), 2)
        self.assertEqual(report["matched_observations"], 0)

    def test_gap_schedule_uses_trusted_span_and_saved_intervals(self):
        self.assertEqual(collector.missing_intervals(START, END, [
            (date(2026, 9, 22), date(2026, 10, 22)),
        ]), [["2026-09-01", "2026-09-21"], ["2026-10-23", "2026-10-31"]])
        self.assertEqual(collector.missing_intervals(START, END, [(START, END)]), [])
        self.assertEqual(collector.missing_intervals(START, END, []), [[START.isoformat(), END.isoformat()]])

    def test_quarantine_keeps_valid_rows_and_does_not_weaken_strict_import(self):
        payload = shared_export()
        payload["rows"].append(raw_row(scheduled_departure_epoch=""))
        rejected = []
        number, rows, status, _ = collector.parse_shared_export(payload, START, END, rejected)
        self.assertEqual((number, len(rows), status), ("MU5101", 1, "reached_start"))
        self.assertEqual(rejected[0]["row_index"], 2)
        self.assertIn("scheduled timestamp", rejected[0]["reason"])
        with self.assertRaisesRegex(ValueError, "scheduled timestamp"):
            collector.parse_shared_export(payload, START, END)

    def test_bad_history_dates_are_quarantined_without_fabricating_boundary_evidence(self):
        payload = shared_export()
        payload["rows"].append(raw_row(date_epoch="unknown"))
        rejected = []
        _, rows, _, _ = collector.parse_shared_export(payload, START, END, rejected)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rejected[0]["row_index"], 2)
        self.assertIn("Unix timestamp", rejected[0]["reason"])
        payload["rows"] = [raw_row(date_epoch="unknown")]
        with self.assertRaisesRegex(ValueError, "claimed start-date coverage"):
            collector.parse_shared_export(payload, START, END, [])

    def test_combined_cli_reuses_inputs_preserves_master_and_resumes_idempotently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            master = root / "master.csv"
            baseline = dict(record(), event_id="legacy")
            with master.open("w", newline="", encoding="utf-8") as destination:
                writer = csv.DictWriter(destination, fieldnames=list(baseline))
                writer.writeheader()
                writer.writerow(baseline)
            before = master.read_bytes()
            payload = shared_export()
            payload["rows"].extend([
                raw_row(flight_hex="new-event", date_epoch=stamp("2026-10-31T15:59:59+00:00"),
                        scheduled_departure_epoch=stamp("2026-10-31T15:59:59+00:00")),
                raw_row(scheduled_departure_epoch=""),
            ])
            collector.atomic_json(root / "exports" / "batch.json", {"exports": [payload]})
            candidate_file = root / "discovered.csv"
            candidate_file.write_text("flight_number\nCA1502\n", encoding="utf-8")
            discovery_report = root / "discovery.json"
            collector.atomic_json(discovery_report, {
                "airport": "SHA", "start": START.isoformat(), "end": END.isoformat(),
                "status": "blocked", "reason": "Historical airport calendar dates are disabled",
            })
            output = root / "combined.csv"
            args = [
                "--combine-master", str(master), "--browser-export-dir", str(root / "exports"),
                "--trusted-start", "2026-09-01", "--trusted-end", "2026-09-01",
                "--candidate-file", str(candidate_file),
                "--discovery-report", str(discovery_report),
                "--start", START.isoformat(), "--end", END.isoformat(),
                "--delay", "5", "--output", str(output), "--run-dir", str(root / "run"),
            ]
            for resume in ([], ["--resume", "--delay", "2"]):
                self.assertEqual(collector.main(args + resume), 2)
                with output.open(newline="", encoding="utf-8") as source:
                    rows = list(csv.DictReader(source))
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0], baseline)
                self.assertEqual(rows[1]["local_date"], "2026-10-31")
                report = json.loads(output.with_suffix(".coverage.json").read_text(encoding="utf-8"))
                self.assertEqual(report["pending_numbers"], ["CA1502"])
                self.assertEqual(report["usable_coverage_unresolved_numbers"], ["MU5101"])
                self.assertEqual(report["quarantined_rows"], 1)
                self.assertEqual(report["historical_discovery"]["status"], "blocked")
                self.assertFalse(report["complete_airport_census"])
            self.assertEqual(master.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "two seconds"):
                collector.main(args + ["--delay", "1"])
            output_before = output.read_bytes()
            batch_path = root / "exports" / "batch.json"
            batch_before = batch_path.read_bytes()
            batch_path.unlink()
            with self.assertRaisesRegex(ValueError, "Previously imported input is missing"):
                collector.main(args + ["--resume"])
            batch_path.write_bytes(batch_before)
            payload["retrieved_at_utc"] = "2026-11-14T03:00:00Z"
            collector.atomic_json(batch_path, {"exports": [payload]})
            with self.assertRaisesRegex(ValueError, "raw batch changed"):
                collector.main(args + ["--resume"])
            self.assertEqual(output.read_bytes(), output_before)


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipIf(sync_playwright is None, "Install the collect dependency group for browser integration tests")
class BrowserCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise unittest.SkipTest("Playwright is not installed")
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.set_default_timeout(1000)

    def tearDown(self):
        self.page.close()

    def history_html(self):
        # Match the observed responsive + desktop table: both share one data row.
        return """
        <h1>Flight tracker map</h1>
        <h1>Flight history for Test airline flight MU5101 </h1>
        <table id="tbl-datatable"><thead>
        <tr><th>FLIGHTS HISTORY</th></tr>
        <tr><th></th><th></th><th>DATE</th><th>FROM</th><th>TO</th><th>AIRCRAFT</th>
        <th>FLIGHT TIME</th><th>STD</th><th>ATD</th><th>STA</th><th></th><th>STATUS</th><th></th></tr>
        </thead><tbody><tr class="data-row">
        <td>Mobile duplicate: SHA PEK 08:00</td><td></td>
        <td data-timestamp="1788220800">01 Sep 2026</td>
        <td><a href="/data/airports/sha">(SHA)</a></td>
        <td><a href="/data/airports/pek">(PEK)</a></td>
        <td>A320 <a href="/data/aircraft/b-1234">(B-1234)</a></td><td>2:00</td>
        <td data-timestamp="1788220800" data-offset="28800">8:00 AM</td>
        <td data-timestamp="1788221400" data-offset="28800">8:10 AM</td>
        <td data-timestamp="1788228000" data-offset="28800">10:00 AM</td><td></td>
        <td data-timestamp="1788228300">Landed 10:05 AM</td>
        <td><a data-flight-hex="abcdef12">Play</a></td></tr></tbody></table>
        """

    def test_browser_extracts_responsive_table_without_duplicate_events(self):
        self.page.route("**/data/flights/mu5101", lambda route: route.fulfill(
            body=self.history_html(), content_type="text/html"
        ))
        with patch.object(collector.time, "sleep"):
            records, status = collector.collect_history(self.page, "MU5101", START, END, 1, 1)
        self.assertEqual(status, "history_exhausted_unverified")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["registration"], "B-1234")
        self.assertEqual(records[0]["flight_hex"], "abcdef12")
        self.assertEqual(records[0]["actual_departure_utc"], "2026-09-01T00:10:00Z")

    def test_load_earlier_reaches_cutoff_and_page_limit_is_explicit(self):
        html = self.history_html() + """
        <button id="btn-load-earlier-flights" onclick="
        const row = document.querySelector('tbody tr').cloneNode(true);
        row.children[2].setAttribute('data-timestamp','1787961600');
        row.children[7].setAttribute('data-timestamp','1787961600');
        document.querySelector('tbody').appendChild(row);">Load earlier flights</button>
        """
        self.page.route("**/data/flights/mu5101", lambda route: route.fulfill(body=html, content_type="text/html"))
        with patch.object(collector.time, "sleep"):
            records, status = collector.collect_history(self.page, "MU5101", START, END, 1, 1)
        self.assertEqual(status, "reached_start")
        self.assertEqual(len(records), 1)
        html = html.replace("1787961600", "1788220800")
        with patch.object(collector.time, "sleep"):
            _, status = collector.collect_history(self.page, "MU5101", START, END, 1, 1)
        self.assertEqual(status, "page_limit")

    def test_shared_worker_allows_slow_navigation_paces_actions_and_stops_on_403(self):
        self.page.set_content(self.history_html())
        code = collector.shared_browser_code(["MU5101", "CA1502", "FM9999"], START, delay=2)
        result = self.page.evaluate("""async code => {
            const actions = [];
            let url = 'about:blank';
            const fake = {
                url: () => url, title: async () => 'Flight history',
                waitForTimeout: async ms => actions.push(['wait', ms]),
                goto: async (target, options) => {
                    if ((options.timeout || 10000) < 18000)
                        throw new Error('Slow page exceeds inherited navigation deadline');
                    actions.push(['goto', target]); url = target;
                    return {status: () => target.endsWith('ca1502') ? 403 : 200};
                },
                getByRole: () => ({innerText: async () => 'Flight history for Test airline flight MU5101'}),
                evaluate: async fn => fn(),
                locator: selector => selector.includes('data-row') ?
                    {first: () => ({waitFor: async () => {}})} :
                    {count: async () => 1, isVisible: async () => true, isEnabled: async () => true,
                     click: async () => {
                         actions.push(['earlier']);
                         const row = document.querySelector('tr.data-row').cloneNode(true);
                         row.children[2].setAttribute('data-timestamp', '1787961600');
                         document.querySelector('tbody').appendChild(row);
                     }},
                waitForFunction: async (fn, arg) => {
                    if (!fn(arg)) throw new Error('Rows did not grow');
                }
            };
            const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
            return {batch: await new AsyncFunction('page', code)(fake), actions};
        }""", code)
        self.assertEqual([item["flight_number"] for item in result["batch"]["exports"]], ["MU5101"])
        self.assertIn("HTTP 403", result["batch"]["stopped"])
        self.assertEqual(result["actions"], [
            ["wait", 2000], ["goto", collector.BASE + "/mu5101"],
            ["wait", 2000], ["earlier"],
            ["wait", 2000], ["goto", collector.BASE + "/ca1502"],
        ])

    def test_shared_worker_returns_loaded_rows_when_pagination_fails(self):
        self.page.set_content(self.history_html())
        code = collector.shared_browser_code(["MU5101"], START, intervals={
            "MU5101": [["2026-09-01", "2026-09-21"], ["2026-10-23", "2026-10-31"]],
        })
        result = self.page.evaluate("""async code => {
            const fake = {
                url: () => 'https://www.flightradar24.com/data/flights/mu5101',
                title: async () => 'Flight history',
                getByRole: () => ({innerText: async () => 'Flight history for Test airline flight MU5101'}),
                evaluate: async fn => fn(), waitForTimeout: async () => {},
                locator: selector => selector.includes('data-row') ?
                    {first: () => ({waitFor: async () => {}})} :
                    {count: async () => 1, isVisible: async () => true, isEnabled: async () => true,
                     click: async () => {throw new Error('HTTP 429');}}
            };
            const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
            return await new AsyncFunction('page', code)(fake);
        }""", code)
        self.assertIn("HTTP 429", result["stopped"])
        self.assertEqual(len(result["exports"][0]["rows"]), 1)
        self.assertEqual(result["exports"][0]["history_status"], "page_limit")
        self.assertEqual(result["exports"][0]["requested_intervals"][1][0], "2026-10-23")

    def test_route_discovery_selects_airports_and_returns_multiple_airlines(self):
        html = """
        <input id="searchAirportFrom" oninput="showAirports(this.value)">
        <input id="searchAirportTo" oninput="showAirports(this.value)">
        <div id="suggestions"></div>
        <script>
        function showAirports(code) {
            document.querySelector('#suggestions').innerHTML =
                '<p class="tt-suggestion" onclick="selectAirport()">' + code + ' / CODE - Airport</p>';
        }
        let count = 0;
        function selectAirport() {
            count++;
            document.querySelector('#suggestions').innerHTML = count === 2 ?
                '<p class="tt-suggestion">2026-11-06 11:00 <strong>MU5101</strong></p>' +
                '<p class="tt-suggestion">2026-11-06 12:00 <strong>CA1502</strong></p>' +
                '<p class="tt-suggestion">2026-11-06 13:00 <strong>MU5101</strong></p>' : '';
        }
        </script>
        """
        self.page.route("**/data/flights", lambda route: route.fulfill(body=html, content_type="text/html"))
        with patch.object(collector.time, "sleep"):
            numbers, count = collector.discover_route(self.page, "SHA", "PEK", 1)
        self.assertEqual(numbers, ["CA1502", "MU5101"])
        self.assertEqual(count, 3)

    def test_restrictions_stop_navigation(self):
        self.page.route("**/data/flights", lambda route: route.fulfill(status=429, body="Rate limited"))
        with patch.object(collector.time, "sleep"), self.assertRaises(collector.AccessRestricted):
            collector.checked_navigation(self.page, collector.BASE, 1)

    def test_paid_session_timeout_is_explicit_and_hidden_badge_does_not_pass(self):
        self.page.route("**/data/flights", lambda route: route.fulfill(
            body="<button style='display:none'>Gold</button><button>Log in</button>",
            content_type="text/html",
        ))
        self.page.goto(collector.BASE)
        with self.assertRaisesRegex(collector.AccessRestricted, "after waiting"):
            collector.require_paid_session(self.page, timeout_ms=100)

    def test_cli_checkpoint_resume_skips_completed_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = root / "seed.csv"
            seed.write_text("flight_number\nMU5101\n", encoding="utf-8")
            output = root / "pilot.csv"
            run_dir = root / "run"
            arguments = [
                "--seed", str(seed), "--output", str(output), "--run-dir", str(run_dir),
                "--profile", str(root / "profile"), "--start", "2026-09-01", "--end", "2026-10-31",
            ]
            visits = []
            html = self.history_html()
            older = html.split('<tbody>')[1].split('</tbody>')[0].replace("1788220800", "1787961600")
            html = html.replace("</tbody>", older + "</tbody>")
            for resume in (False, True):
                context = self.browser.new_context()
                context.route("**/data/flights", lambda route: route.fulfill(
                    body="<button>Gold</button>", content_type="text/html"
                ))

                def history(route):
                    visits.append(route.request.url)
                    route.fulfill(body=html, content_type="text/html")

                context.route("**/data/flights/mu5101", history)
                with patch("playwright.sync_api.sync_playwright") as factory, patch.object(collector.time, "sleep"):
                    playwright = factory.return_value.__enter__.return_value
                    playwright.chromium.launch_persistent_context.return_value = context
                    self.assertEqual(collector.main(arguments + (["--resume"] if resume else [])), 0)
                    playwright.chromium.launch_persistent_context.assert_called_once_with(
                        str(root / "profile"), channel="msedge", headless=False, chromium_sandbox=True,
                        viewport={"width": 1440, "height": 1000},
                    )
                with output.open(newline="", encoding="utf-8") as source:
                    self.assertEqual(len(list(csv.DictReader(source))), 1)
            self.assertEqual(len(visits), 1)
            state = json.loads((run_dir / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(state["flights"]["MU5101"]["status"], "reached_start")
            with self.assertRaisesRegex(ValueError, "another date range"):
                collector.main(arguments + ["--start", "2026-09-02", "--resume"])

    def test_login_uses_edge_with_a_dedicated_profile(self):
        context = self.browser.new_context()
        context.route("**/data/flights", lambda route: route.fulfill(
            body="<button>Gold</button>", content_type="text/html"
        ))
        with patch("playwright.sync_api.sync_playwright") as factory, patch("builtins.input", return_value=""):
            playwright = factory.return_value.__enter__.return_value
            playwright.chromium.launch_persistent_context.return_value = context
            self.assertEqual(collector.main(["--login"]), 0)
            playwright.chromium.launch_persistent_context.assert_called_once_with(
                str(Path.home() / ".sha-flight-edge-browser"), channel="msedge", headless=False,
                chromium_sandbox=True,
            )

    def test_cookie_mode_uses_an_ephemeral_edge_session_and_validates_gold(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cookies = root / "cookies.txt"
            cookies.write_text(
                "# Netscape HTTP Cookie File\n"
                "#HttpOnly_.flightradar24.com\tTRUE\t/\tTRUE\t\tauth\tdummy-session\n",
                encoding="utf-8",
            )
            seed = root / "seed.csv"
            seed.write_text("flight_number\nMU5101\n", encoding="utf-8")
            for authenticated in (True, False):
                context = self.browser.new_context()
                context.route("**/data/flights", lambda route: route.fulfill(
                    body=(
                        "<script>setTimeout(() => {document.body.innerHTML = "
                        "'<button>Gold</button>';}, 150);</script>"
                    ) if authenticated else "<button>Log in</button>",
                    content_type="text/html",
                ))
                context.route("**/data/flights/mu5101", lambda route: route.fulfill(
                    body=self.history_html(), content_type="text/html"
                ))
                imported = []
                original_import = collector.import_session_cookies

                def import_cookies(target, jar):
                    original_import(target, jar)
                    imported.extend(target.cookies())

                output = root / f"cookie-pilot-{authenticated}.csv"
                original_check = collector.require_paid_session
                with patch("playwright.sync_api.sync_playwright") as factory, patch.object(
                    collector.time, "sleep"
                ), patch.object(collector, "import_session_cookies", side_effect=import_cookies), patch.object(
                    collector, "require_paid_session", side_effect=lambda page: original_check(page, timeout_ms=1000)
                ):
                    playwright = factory.return_value.__enter__.return_value
                    browser = playwright.chromium.launch.return_value.__enter__.return_value
                    browser.new_context.return_value = context
                    self.assertEqual(collector.main([
                        "--cookies", str(cookies), "--seed", str(seed),
                        "--start", "2026-09-01", "--end", "2026-10-31",
                        "--output", str(output), "--run-dir", str(root / f"run-{authenticated}"),
                    ]), 2)
                    playwright.chromium.launch.assert_called_once_with(
                        channel="msedge", headless=False, chromium_sandbox=True,
                    )
                    playwright.chromium.launch_persistent_context.assert_not_called()
                self.assertEqual(len(imported), 1)
                self.assertEqual(imported[0]["name"], "auth")
                self.assertTrue(imported[0]["httpOnly"])
                self.assertEqual(imported[0]["expires"], -1)
                with output.open(newline="", encoding="utf-8") as source:
                    self.assertEqual(len(list(csv.DictReader(source))), 1 if authenticated else 0)
                checkpoint = (root / f"run-{authenticated}" / "checkpoint.json").read_text(encoding="utf-8")
                report = output.with_suffix(".coverage.json").read_text(encoding="utf-8")
                self.assertNotIn("dummy-session", checkpoint + report)
                if not authenticated:
                    self.assertIn("Gold/Business session not found", report)

    def test_cookie_import_failure_redacts_browser_error_details(self):
        from playwright.sync_api import Error as BrowserError

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookies.txt"
            path.write_text(
                "# Netscape HTTP Cookie File\n"
                ".flightradar24.com\tTRUE\t/\tTRUE\t\tauth\tdummy-session\n",
                encoding="utf-8",
            )
            context = MagicMock()
            context.add_cookies.side_effect = BrowserError("Cookie rejected: dummy-session")
            with self.assertRaisesRegex(ValueError, "contents withheld") as result:
                collector.import_session_cookies(context, collector.read_session_cookies(path))
            self.assertNotIn("dummy-session", str(result.exception))
            self.assertTrue(result.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
