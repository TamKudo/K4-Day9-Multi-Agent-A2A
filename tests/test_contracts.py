import json
import unittest
from pathlib import Path

from src.io import load_cases
from src.schemas import CaseInput, ContractError


class InputContractTests(unittest.TestCase):
    def test_all_supplied_inputs_match_contract(self):
        cases = load_cases(Path("input"))
        self.assertEqual(50, len(cases))
        self.assertEqual("EC_001", cases[0].case_id)
        self.assertEqual("EC_050", cases[-1].case_id)

    def test_rejects_wrong_policy(self):
        raw = json.loads(Path("input/EC_001.json").read_text(encoding="utf-8"))
        raw["policy_version"] = "OLD_POLICY"
        with self.assertRaises(ContractError):
            CaseInput.from_dict(raw)

    def test_rejects_missing_order_id(self):
        raw = json.loads(Path("input/EC_001.json").read_text(encoding="utf-8"))
        raw["customer_request"]["claimed_order_id"] = ""
        with self.assertRaises(ContractError):
            CaseInput.from_dict(raw)


if __name__ == "__main__":
    unittest.main()

