import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from agents.fetchers import parse_source_payload
from agents.fetchers.base import _headers_for_source, _source_url, fetch_source_records, fetch_sources_sequentially

REPO_ROOT = Path(__file__).resolve().parents[2]
RECALL_DATA_DIR = REPO_ROOT / "benchmark" / "recall_data"

class FetcherParsingTests(unittest.TestCase):
    def test_source_headers_merge_default_and_source_specific_headers(self) -> None:
        with patch(
            "agents.fetchers.base.API_SOURCES",
            {"us": {"url": "https://example.com", "headers": {"Referer": "ref", "Origin": "origin"}}},
        ):
            headers = _headers_for_source("us")

        self.assertEqual(headers["Referer"], "ref")
        self.assertEqual(headers["Origin"], "origin")
        self.assertIn("User-Agent", headers)

    def test_headers_for_string_source_config_uses_defaults_only(self) -> None:
        with patch("agents.fetchers.base.API_SOURCES", {"us": "https://example.com"}):
            headers = _headers_for_source("us")

        self.assertNotIn("Referer", headers)
        self.assertIn("User-Agent", headers)

    def test_headers_raise_when_source_headers_is_not_a_mapping(self) -> None:
        with patch(
            "agents.fetchers.base.API_SOURCES",
            {"us": {"url": "https://example.com", "headers": ["invalid"]}},
        ):
            with self.assertRaises(ValueError):
                _headers_for_source("us")

    def test_source_url_supports_string_and_mapping_configs(self) -> None:
        with patch(
            "agents.fetchers.base.API_SOURCES",
            {
                "string-source": "https://example.com/string",
                "mapping-source": {"url": "https://example.com/mapping"},
            },
        ):
            self.assertEqual(_source_url("string-source"), "https://example.com/string")
            self.assertEqual(_source_url("mapping-source"), "https://example.com/mapping")

    def test_source_url_rejects_invalid_source_config_type(self) -> None:
        with patch("agents.fetchers.base.API_SOURCES", {"broken": 123}):
            with self.assertRaises(ValueError):
                _source_url("broken")

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

    def test_parser_honors_limit_for_direct_record_list(self) -> None:
        payload = [{"id": 1}, {"id": 2}, {"id": 3}]

        records = parse_source_payload("uk", payload, limit=2)

        self.assertEqual(len(records), 2)
        self.assertEqual([record.raw_record["id"] for record in records], [1, 2])

    def test_parser_filters_non_dict_items_from_record_list(self) -> None:
        payload = [{"id": 1}, "bad", 123, {"id": 2}]

        records = parse_source_payload("uk", payload, limit=10)

        self.assertEqual(len(records), 2)
        self.assertEqual([record.raw_record["id"] for record in records], [1, 2])

    def test_parser_extracts_named_record_collection(self) -> None:
        payload = {"results": [{"id": "a"}, {"id": "b"}]}

        records = parse_source_payload("us", payload, limit=10)

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].raw_record["id"], "a")

    def test_parser_falls_back_to_root_dict_when_no_record_list_exists(self) -> None:
        payload = {"product": "Sample", "status": "active"}

        records = parse_source_payload("france", payload, limit=10)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].raw_record, payload)

    def test_parser_uses_largest_nested_record_list(self) -> None:
        payload = {
            "outer": {"items": [{"id": 1}]},
            "nested": {"deep": {"records": [{"id": 2}, {"id": 3}]}},
        }

        records = parse_source_payload("uk", payload, limit=10)

        self.assertEqual(len(records), 2)
        self.assertEqual([record.raw_record["id"] for record in records], [2, 3])

    def test_parser_returns_empty_for_non_dict_non_list_payload(self) -> None:
        records = parse_source_payload("uk", "unexpected-text-payload", limit=10)

        self.assertEqual(records, [])

class FetcherNetworkTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_source_records_requests_source_and_parses_response(self) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": "1"}, {"id": "2"}]
        mock_response.raise_for_status.return_value = None

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        with patch("agents.fetchers.base.API_SOURCES", {"us": "https://example.com/us"}):
            records = await fetch_source_records("us", limit=1, client=mock_client)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source, "us")
        self.assertEqual(records[0].raw_record, {"id": "1"})
        mock_client.get.assert_awaited_once()
        mock_response.raise_for_status.assert_called_once_with()

    async def test_fetch_sources_sequentially_collects_failures_and_continues(self) -> None:
        source_a_records = parse_source_payload("a", [{"id": "a1"}], limit=10)

        with patch(
            "agents.fetchers.base.fetch_source_records",
            new=AsyncMock(side_effect=[source_a_records, ValueError("boom"), KeyError("missing-source")]),
        ):
            result = await fetch_sources_sequentially(["a", "b", "c"], limit=10)

        self.assertEqual([record.raw_record["id"] for record in result.records], ["a1"])
        self.assertIn("b", result.failures)
        self.assertIn("boom", result.failures["b"])
        self.assertIn("c", result.failures)
        self.assertIn("missing-source", result.failures["c"])

    async def test_fetch_sources_sequentially_captures_http_errors(self) -> None:
        with patch(
            "agents.fetchers.base.fetch_source_records",
            new=AsyncMock(side_effect=httpx.HTTPStatusError("403", request=MagicMock(), response=MagicMock())),
        ):
            result = await fetch_sources_sequentially(["us"], limit=5)

        self.assertEqual(result.records, [])
        self.assertIn("us", result.failures)
        self.assertIn("403", result.failures["us"])

def _load_json(filename: str):
    return json.loads((RECALL_DATA_DIR / filename).read_text(encoding="utf-8"))

if __name__ == "__main__":
    unittest.main()
