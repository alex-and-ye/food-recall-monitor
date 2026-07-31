import tempfile
import unittest
from pathlib import Path

from config.pipelines import load_pipeline_switches
from config.early_warning import load_early_warning_config

class PipelineSwitchesTests(unittest.TestCase):
    def test_default_switches_file_loads(self) -> None:
        switches = load_pipeline_switches()

        self.assertFalse(switches.official_pipeline.enabled)
        self.assertFalse(switches.official_pipeline.bootstrap_on_empty_db)
        self.assertTrue(switches.early_warning.enabled)
        self.assertTrue(switches.early_warning.bootstrap_on_empty_db)

    def test_early_warning_yaml_rejects_enabled_switch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "early_warning.yaml"
            path.write_text(
                "\n".join(
                    [
                        "enabled: true",
                        "countries:",
                        "  - code: GB",
                        "    name: United Kingdom",
                        "    languages: [en]",
                        "languages:",
                        "  en:",
                        "    recall: [food recall]",
                        "    food: [food]",
                    ]
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "pipelines.yaml"):
                load_early_warning_config(path)

if __name__ == "__main__":
    unittest.main()
