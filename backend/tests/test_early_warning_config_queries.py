from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from config.early_warning import EarlyWarningConfig, load_early_warning_config
from services.early_warning.query_generator import build_query_catalog, generate_queries
from settings import BackendSettings


class EarlyWarningConfigTests(unittest.TestCase):
    def test_brave_secret_is_read_from_environment(self) -> None:
        with patch.dict(os.environ, {"BRAVE_API_KEY": "environment-secret"}, clear=False):
            settings = BackendSettings(_env_file=None)

        self.assertEqual(settings.brave_api_key, "environment-secret")

    def test_default_disabled_config_loads_without_secret(self) -> None:
        config = load_early_warning_config()

        self.assertFalse(config.enabled)
        config.validate_runtime(brave_api_key=None)
        self.assertLessEqual(config.budgets.results_per_query, 20)

    def test_enabled_config_requires_brave_key(self) -> None:
        config = load_early_warning_config().model_copy(update={"enabled": True})

        with self.assertRaisesRegex(ValueError, "BRAVE_API_KEY"):
            config.validate_runtime(brave_api_key=None)
        config.validate_runtime(brave_api_key="secret")

    def test_rejects_unknown_language_and_overlapping_thresholds(self) -> None:
        payload = load_early_warning_config().model_dump()
        payload["countries"][0]["languages"] = ["zz"]
        with self.assertRaises(ValidationError):
            EarlyWarningConfig.model_validate(payload)

        payload = load_early_warning_config().model_dump()
        payload["thresholds"] = {"accept": 0.5, "reject": 0.5}
        with self.assertRaises(ValidationError):
            EarlyWarningConfig.model_validate(payload)

    def test_rejects_url_in_domain_field(self) -> None:
        payload = load_early_warning_config().model_dump()
        payload["domains"]["trusted"] = ["https://example.com/path"]

        with self.assertRaises(ValidationError):
            EarlyWarningConfig.model_validate(payload)

    def test_rejects_api_key_in_yaml_model(self) -> None:
        payload = load_early_warning_config().model_dump()
        payload["brave"]["api_key"] = "must-not-live-in-yaml"

        with self.assertRaises(ValidationError):
            EarlyWarningConfig.model_validate(payload)


class QueryGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_early_warning_config()

    def test_query_catalog_is_stable_and_multilingual(self) -> None:
        first = build_query_catalog(self.config)
        second = build_query_catalog(self.config)

        self.assertEqual(first, second)
        self.assertEqual(len({query.query_id for query in first}), len(first))
        self.assertIn("en", {query.language for query in first})
        self.assertIn("fr", {query.language for query in first})
        self.assertIn("de", {query.language for query in first})
        self.assertTrue(any("site:" in query.text for query in first))
        self.assertTrue(
            any(
                "food recall United Kingdom" == query.text
                or query.text.startswith("food recall ")
                for query in first
            )
        )
        self.assertFalse(any(' "food" ' in f" {query.text} " for query in first))

    def test_rotation_is_deterministic_and_budgeted(self) -> None:
        first = generate_queries(self.config, rotation=0, budget=5)
        second = generate_queries(self.config, rotation=1, budget=5)

        self.assertEqual(first, generate_queries(self.config, rotation=0, budget=5))
        self.assertEqual(len(first), 5)
        self.assertEqual(len(second), 5)
        self.assertEqual(second[0], build_query_catalog(self.config)[5])

    def test_zero_budget_returns_no_queries(self) -> None:
        self.assertEqual(generate_queries(self.config, budget=0), [])

    def test_disabled_countries_are_excluded_from_catalog(self) -> None:
        countries = [
            country.model_copy(update={"enabled": country.code == "GB"})
            for country in self.config.countries
        ]
        config = self.config.model_copy(update={"countries": countries})

        catalog = build_query_catalog(config)

        self.assertTrue(catalog)
        self.assertEqual({query.country for query in catalog}, {"GB"})


if __name__ == "__main__":
    unittest.main()
