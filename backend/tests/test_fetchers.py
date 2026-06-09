import json
import unittest
from pathlib import Path

from agents.fetchers.france import parse_france_payload
from agents.fetchers.uk import parse_uk_payload
from agents.fetchers.us import parse_us_payload
from models.pipeline_options import RecallSource


REPO_ROOT = Path(__file__).resolve().parents[2]
RECALL_DATA_DIR = REPO_ROOT / "benchmark" / "recall_data"


class FetcherParsingTests(unittest.TestCase):
    def test_france_parser_extracts_protected_fields_and_working_json(self) -> None:
        payload = _load_json("france_recall.json")

        records = parse_france_payload(payload, limit=1)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source, RecallSource.FRANCE)
        self.assertEqual(record.protected_fields.product_name, "pt l eveque aop cru 400g")
        self.assertEqual(record.protected_fields.recall_date.isoformat(), "2026-05-28")
        self.assertEqual(
            record.protected_fields.source_url,
            "https://rappel.conso.gouv.fr/fiche-rappel/22397/interne",
        )
        self.assertEqual(record.working_json["source"], "france")
        self.assertIn("france entière", record.working_json["affected_regions"])

    def test_uk_parser_extracts_protected_fields_and_working_json(self) -> None:
        payload = _load_json("uk_recall.json")

        records = parse_uk_payload(payload, limit=1)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source, RecallSource.UK)
        self.assertEqual(record.protected_fields.product_name, "Morrisons Savers Cashews")
        self.assertEqual(record.protected_fields.recall_date.isoformat(), "2026-05-26")
        self.assertEqual(
            record.protected_fields.source_url,
            "https://www.food.gov.uk/news-alerts/alert/fsa-prin-25-2026",
        )
        self.assertEqual(record.working_json["source"], "uk")
        self.assertEqual(record.working_json["affected_regions"], ["England", "Scotland", "Wales"])

    def test_us_parser_extracts_protected_fields_and_working_json(self) -> None:
        payload = _load_json("us_recall.json")

        records = parse_us_payload(payload, limit=1)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.source, RecallSource.US)
        self.assertIn("Cargill Kitchen Solutions", record.protected_fields.product_name)
        self.assertEqual(record.protected_fields.recall_date.isoformat(), "2025-03-28")
        self.assertEqual(
            record.protected_fields.source_url,
            "http://www.fsis.usda.gov/es/retirada/cargill-kitchen-solutions-retira-productos-de-huevo-liquido-debido-a-una-sustancia-no",
        )
        self.assertEqual(record.working_json["source"], "us")
        self.assertEqual(record.working_json["affected_regions"], ["Nationwide"])


def _load_json(filename: str):
    return json.loads((RECALL_DATA_DIR / filename).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
