import json
import unittest
from pathlib import Path

from config.agents import API_SOURCES
from agents.fetchers import parse_source_payload
from agents.fetchers.base import _headers_for_source


REPO_ROOT = Path(__file__).resolve().parents[2]
RECALL_DATA_DIR = REPO_ROOT / "benchmark" / "recall_data"


class FetcherParsingTests(unittest.TestCase):
    def test_us_source_headers_include_referer_and_origin(self) -> None:
        headers = _headers_for_source("us")
        source_headers = API_SOURCES["us"]["headers"]

        self.assertEqual(headers["Referer"], source_headers["Referer"])
        self.assertEqual(headers["Origin"], source_headers["Origin"])

    def test_france_parser_infers_records_and_preserves_raw_json(self) -> None:
        payload = _load_json("france_recall.json")

        records = parse_source_payload("france", payload, limit=1)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source, "france")
        self.assertEqual(record.raw_record["libelle"], "pt l eveque aop cru 400g")
        self.assertEqual(record.working_json["source"], "france")
        self.assertEqual(record.working_json["record"], record.raw_record)

    def test_uk_parser_infers_records_and_preserves_raw_json(self) -> None:
        payload = _load_json("uk_recall.json")

        records = parse_source_payload("uk", payload, limit=1)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source, "uk")
        self.assertEqual(record.raw_record["productDetails"][0]["productName"], "Morrisons Savers Cashews")
        self.assertEqual(record.working_json["source"], "uk")
        self.assertEqual(record.working_json["record"], record.raw_record)

    def test_us_parser_infers_records_and_preserves_raw_json(self) -> None:
        payload = _load_json("us_recall.json")

        records = parse_source_payload("us", payload, limit=1)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source, "us")
        self.assertIn("Cargill Kitchen Solutions", record.raw_record["field_title"])
        self.assertEqual(record.working_json["source"], "us")
        self.assertEqual(record.working_json["record"], record.raw_record)


def _load_json(filename: str):
    return json.loads((RECALL_DATA_DIR / filename).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
