import unittest

from agents.config import DEFAULT_SOURCE_NAMES
from models.pipeline_options import PipelineRunOptions


class PipelineRunOptionsTests(unittest.TestCase):
    def test_default_sources_come_from_config(self) -> None:
        options = PipelineRunOptions()

        self.assertEqual(options.sources, DEFAULT_SOURCE_NAMES)

    def test_sources_must_exist_in_config(self) -> None:
        with self.assertRaises(ValueError):
            PipelineRunOptions(sources=["unknown-source"])


if __name__ == "__main__":
    unittest.main()
