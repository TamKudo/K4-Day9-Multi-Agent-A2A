import tempfile
import unittest
from pathlib import Path

from src.prompt_loader import PROMPT_FILES, REQUIRED_SECTIONS, PromptLoader
from src.schemas import ContractError


class PromptContractTests(unittest.TestCase):
    def test_every_agent_has_a_complete_specialized_prompt(self):
        loader = PromptLoader()

        prompts = {name: loader.load(name) for name in PROMPT_FILES}

        self.assertEqual(8, len(prompts))
        self.assertEqual(8, len(set(prompts.values())))
        for agent_name, prompt in prompts.items():
            for section in REQUIRED_SECTIONS:
                self.assertIn(section, prompt, f"{agent_name} missing {section}")

    def test_unknown_agent_fails_closed(self):
        with self.assertRaises(ContractError):
            PromptLoader().load("unknown_agent")

    def test_missing_prompt_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ContractError):
                PromptLoader(Path(tmp)).load("customer")

    def test_incomplete_prompt_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp)
            (prompt_dir / "customer.md").write_text("# Role\nCustomer", encoding="utf-8")
            with self.assertRaises(ContractError):
                PromptLoader(prompt_dir).load("customer")


if __name__ == "__main__":
    unittest.main()

