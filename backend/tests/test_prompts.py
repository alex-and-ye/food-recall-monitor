import unittest

from agents.prompts import (
    STRUCTURING_SYSTEM_PROMPT,
    SUMMARIZATION_SYSTEM_PROMPT,
    TRANSLATION_SYSTEM_PROMPT,
)


class PromptContractTests(unittest.TestCase):
    def test_translation_prompt_targets_scraped_record_envelope(self) -> None:
        self.assertIn('"record"', TRANSLATION_SYSTEM_PROMPT)
        self.assertIn("cleaned scraped recall webpage payload", TRANSLATION_SYSTEM_PROMPT)

    def test_summarization_prompt_keeps_three_sentence_requirement(self) -> None:
        self.assertIn("exactly three sentences", SUMMARIZATION_SYSTEM_PROMPT)

    def test_structuring_prompt_omits_original_source_json_contract(self) -> None:
        self.assertIn("Translated Source JSON", STRUCTURING_SYSTEM_PROMPT)
        self.assertNotIn("Original Source JSON before translation", STRUCTURING_SYSTEM_PROMPT)
        self.assertIn("Do not add api_source", STRUCTURING_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
