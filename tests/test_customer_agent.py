from pathlib import Path
import unittest

from src.customer_agent import CustomerAgent
from src.data_repository import DataRepository
from src.schemas import CaseInput, ContractError, CustomerRequest, InvestigationScope


ROOT = Path(__file__).resolve().parents[1]
CASE = CaseInput(
    case_id="EC_001",
    customer_request=CustomerRequest("vi", "test", "9b75cdaf2d85857ef023980e15d01546"),
    investigation_scope=InvestigationScope(True, True),
    policy_version="EC_POLICY_V2",
)


class CustomerAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = DataRepository(ROOT / "data")
        cls.agent = CustomerAgent(cls.repository)

    def test_resolves_real_case_and_excludes_claimed_order(self) -> None:
        result = self.agent.investigate(CASE)  # This order has a repeat in Olist data.

        self.assertIsNotNone(result.customer_unique_id)
        self.assertNotIn(CASE.customer_request.claimed_order_id, result.related_order_ids)
        self.assertEqual(1, len(result.related_order_ids))

    def test_respects_history_scope_without_losing_identity(self) -> None:
        case = CaseInput(
            case_id=CASE.case_id,
            customer_request=CASE.customer_request,
            investigation_scope=InvestigationScope(False, True),
            policy_version=CASE.policy_version,
        )
        result = self.agent.investigate(case)

        self.assertIsNotNone(result.customer_unique_id)
        self.assertEqual([], result.related_order_ids)

    def test_limits_history_to_five_in_source_order(self) -> None:
        class RepositoryWithLongHistory:
            def get_order(self, order_id):
                return {"order_id": order_id, "customer_id": "customer-1"}

            def get_customer(self, customer_id):
                return {"customer_id": customer_id, "customer_unique_id": "unique-1"}

            def get_orders_by_customer_unique_id(self, customer_unique_id):
                return [{"order_id": value} for value in ["old-1", "claimed", "old-2", "old-3", "old-4", "old-5", "old-6"]]

        case = CaseInput(
            case_id="EC_999",
            customer_request=CustomerRequest("vi", "test", "claimed"),
            investigation_scope=InvestigationScope(True, True),
            policy_version="EC_POLICY_V2",
        )
        result = CustomerAgent(RepositoryWithLongHistory()).investigate(case)

        self.assertEqual(["old-1", "old-2", "old-3", "old-4", "old-5"], result.related_order_ids)

    def test_rejects_missing_order_or_customer(self) -> None:
        case = CaseInput(
            case_id=CASE.case_id,
            customer_request=CustomerRequest("vi", "test", "does-not-exist"),
            investigation_scope=CASE.investigation_scope,
            policy_version=CASE.policy_version,
        )
        with self.assertRaises(ContractError):
            self.agent.investigate(case)


if __name__ == "__main__":
    unittest.main()
