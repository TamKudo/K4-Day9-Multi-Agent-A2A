import unittest

from src.data_repository import DataRepository
from src.io import load_cases
from src.order_product_agent import OlistOrderProductAgent
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class OrderProductAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = DataRepository(ROOT / "data")
        cls.agent = OlistOrderProductAgent(cls.repository)

    def test_real_case_preserves_source_order_and_totals(self):
        case = load_cases(ROOT / "input")[0]

        result = self.agent.investigate(case)

        self.assertEqual(case.customer_request.claimed_order_id, result.order_id)
        self.assertEqual("delivered", result.order_status)
        self.assertEqual(2, len(result.item_ids))
        self.assertEqual(220.64, result.item_total_brl)
        self.assertEqual(16.70, result.freight_total_brl)
        self.assertEqual(["beleza_saude"], result.category_names)


if __name__ == "__main__":
    unittest.main()
