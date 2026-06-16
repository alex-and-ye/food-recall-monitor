import unittest
from unittest.mock import patch

from pydantic import ValidationError

from models.pipeline_options import PipelineRunOptions

class PipelineRunOptionsTests(unittest.TestCase):
    def test_default_sources_come_from_source_provider(self) -> None:
        with patch("models.pipeline_options._source_names", return_value=["source-a", "source-b"]):
            options = PipelineRunOptions()

        self.assertEqual(options.sources, ["source-a", "source-b"])

    def test_sources_must_exist_in_provider_set(self) -> None:
        with patch("models.pipeline_options._source_names", return_value=["source-a", "source-b"]):
            with self.assertRaises(ValueError) as context:
                PipelineRunOptions(sources=["source-a", "unknown-source"])

        message = str(context.exception)
        self.assertIn("Unknown source(s): unknown-source", message)
        self.assertIn("Configured sources: source-a, source-b", message)

    def test_empty_sources_is_allowed(self) -> None:
        with patch("models.pipeline_options._source_names", return_value=["source-a"]):
            options = PipelineRunOptions(sources=[])

        self.assertEqual(options.sources, [])

    def test_limit_accepts_documented_bounds(self) -> None:
        with patch("models.pipeline_options._source_names", return_value=["source-a"]):
            self.assertEqual(PipelineRunOptions(sources=["source-a"], limit=1).limit, 1)
            self.assertEqual(PipelineRunOptions(sources=["source-a"], limit=100).limit, 100)

    def test_limit_rejects_values_outside_bounds(self) -> None:
        with patch("models.pipeline_options._source_names", return_value=["source-a"]):
            with self.assertRaises(ValidationError):
                PipelineRunOptions(sources=["source-a"], limit=0)
            with self.assertRaises(ValidationError):
                PipelineRunOptions(sources=["source-a"], limit=101)

if __name__ == "__main__":
    unittest.main()
