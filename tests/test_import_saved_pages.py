import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from scripts import fetch_flights as importer


URL = "https://www.flightradar24.com/data/flights/mu5101"
HISTORY = """
<table>
<tr><th>DATE</th><th>FROM</th><th>TO</th><th>AIRCRAFT</th>
<th>FLIGHT TIME</th><th>STD</th><th>ATD</th><th>STA</th><th>STATUS</th></tr>
<tr><td>26 Oct 2026</td><td>Shanghai (SHA)</td><td>Beijing (PEK)</td>
<td>A320 (B-1234)</td><td>2:00</td><td>08:00</td><td>08:10</td>
<td>10:00</td><td>Landed 10:10</td></tr>
<tr><td>25 Oct 2026</td><td>Shanghai (SHA)</td><td>Beijing (PEK)</td>
<td>A320</td><td>-</td><td>08:00</td><td>-</td>
<td>10:00</td><td>Cancelled</td></tr>
</table>
"""


class ImportFlightPagesTests(unittest.TestCase):
    def test_history_preserves_rows_and_display_times(self):
        records = importer.parse_flight_history(HISTORY, URL)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["flight_number"], "MU5101")
        self.assertEqual(records[0]["origin_iata"], "SHA")
        self.assertEqual(records[0]["destination_iata"], "PEK")
        self.assertEqual(records[0]["scheduled_departure_display"], "08:00")
        self.assertEqual(records[0]["status_display"], "Landed 10:10")
        self.assertNotIn("scheduled_departure_utc", records[0])
        self.assertNotIn("actual_departure_display", records[1])

    def test_rejects_search_page_and_other_hosts(self):
        for url in (
            "https://www.flightradar24.com/data/flights",
            "https://example.com/data/flights/mu5101",
            "http://www.flightradar24.com/data/flights/mu5101",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                importer.flight_number_from_url(url)

    def test_no_history_reports_error(self):
        with self.assertRaisesRegex(ValueError, "No usable flight-history rows"):
            importer.parse_flight_history("<html>Authentication required</html>", URL)

    @patch.object(importer, "urlopen")
    def test_fetch_sends_headers_and_decodes_response(self, urlopen):
        headers = Message()
        headers["Content-Type"] = "text/html; charset=utf-8"
        response = MagicMock()
        response.headers = headers
        response.read.return_value = HISTORY.encode("utf-8")
        urlopen.return_value.__enter__.return_value = response
        html, retrieved_at = importer.fetch_page(URL, 12)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("Mozilla", request.get_header("User-agent"))
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 12)
        self.assertEqual(html, HISTORY)
        self.assertTrue(retrieved_at.endswith("+00:00"))

    @patch.object(importer, "urlopen")
    def test_fetch_errors_are_explicit(self, urlopen):
        for error, message in (
            (HTTPError(URL, 403, "Forbidden", Message(), None), "HTTP 403"),
            (URLError("connection failed"), "Could not fetch"),
            (TimeoutError("timed out"), "Could not fetch"),
        ):
            with self.subTest(error=error):
                urlopen.side_effect = error
                with self.assertRaisesRegex(ValueError, message):
                    importer.fetch_page(URL, 1)

    @patch.object(importer, "fetch_page", return_value=(HISTORY, "2026-10-26T10:00:00+00:00"))
    def test_remote_cli_writes_schema_and_provenance(self, fetch_page):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "flights.csv"
            with patch("sys.argv", ["importer", "--url", URL, "--output", str(output)]):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(importer.main(), 0)
            with output.open(newline="", encoding="utf-8") as source:
                reader = csv.DictReader(source)
                records = list(reader)
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["source_url"], URL)
            self.assertEqual(records[0]["retrieved_at_utc"], "2026-10-26T10:00:00+00:00")
            self.assertEqual(records[0]["direction"], "departure")
            self.assertEqual(records[0]["route"], "SHA-PEK")
            self.assertEqual(records[0]["timing_semantics_verified"], "false")
            self.assertNotEqual(records[0]["event_id"], records[1]["event_id"])
            fetch_page.assert_called_once_with(URL, 30)

    @patch.object(importer, "urlopen")
    def test_saved_page_cli_remains_offline(self, urlopen):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "flight.html").write_text(
                "<table><tr><td>Flight</td><td>MU5101</td></tr>"
                "<tr><td>From</td><td>SHA</td></tr>"
                "<tr><td>To</td><td>PEK</td></tr></table>", encoding="utf-8"
            )
            manifest = root / "manifest.csv"
            manifest.write_text(f"file,source_url\nflight.html,{URL}\n", encoding="utf-8")
            output = root / "out.csv"
            with patch("sys.argv", [
                "importer", "--html-dir", str(root), "--manifest", str(manifest),
                "--output", str(output),
            ]), redirect_stdout(io.StringIO()):
                self.assertEqual(importer.main(), 0)
            with output.open(newline="", encoding="utf-8") as source:
                record = next(csv.DictReader(source))
            self.assertEqual(record["event_id"], "local:flight:MU5101")
            self.assertEqual(record["route"], "SHA-PEK")
            self.assertEqual(record["retrieved_at_utc"], "")
            urlopen.assert_not_called()

    @patch.object(importer, "fetch_page", return_value=("<html>No history</html>", "now"))
    def test_failed_parse_does_not_overwrite_output(self, fetch_page):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.csv"
            output.write_text("existing output", encoding="utf-8")
            with patch("sys.argv", ["importer", "--url", URL, "--output", str(output)]):
                with self.assertRaisesRegex(ValueError, "No usable flight-history rows"):
                    importer.main()
            self.assertEqual(output.read_text(encoding="utf-8"), "existing output")

    @patch.object(importer, "fetch_page", return_value=(HISTORY, "2026-10-26T10:00:00+00:00"))
    def test_merge_creates_header_once_and_rejects_mismatched_schema(self, fetch_page):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "out.csv"
            arguments = ["importer", "--url", URL, "--output", str(output), "--merge"]
            for _ in range(2):
                with patch("sys.argv", arguments), redirect_stdout(io.StringIO()):
                    self.assertEqual(importer.main(), 0)
            with output.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(row["flight_number"] == "MU5101" for row in rows))
            output.write_text("wrong,header\nexisting,data\n", encoding="utf-8")
            with patch("sys.argv", arguments), self.assertRaisesRegex(ValueError, "header"):
                importer.main()
            self.assertEqual(output.read_text(encoding="utf-8"), "wrong,header\nexisting,data\n")


if __name__ == "__main__":
    unittest.main()
