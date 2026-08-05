import unittest

from src.payment_agent import OlistPaymentAgent
from src.schemas import (
    CaseInput, CustomerRequest, InvestigationScope, OrderProductResult,
)


CASE = CaseInput(
    "EC_001", CustomerRequest("vi", "test", "order-1"),
    InvestigationScope(True, True), "EC_POLICY_V2",
)


class PaymentRepositoryFake:
    def __init__(self, payments):
        self.payments = payments

    def get_payments_by_order(self, order_id):
        self.last_order_id = order_id
        return self.payments


class PaymentAgentTests(unittest.TestCase):
    def test_reconciles_split_payment_in_source_order(self):
        repository = PaymentRepositoryFake([
            {"payment_sequential": "1", "payment_type": "credit_card", "payment_value": "100.00"},
            {"payment_sequential": "2", "payment_type": "voucher", "payment_value": "112.27"},
        ])
        order = OrderProductResult("order-1", "delivered", item_total_brl=194.0, freight_total_brl=18.27)

        result = OlistPaymentAgent(repository).investigate(CASE, order)

        self.assertEqual(["order-1:1", "order-1:2"], result.payment_ids)
        self.assertEqual(["credit_card", "voucher"], result.payment_types)
        self.assertEqual(212.27, result.payment_total_brl)
        self.assertEqual(212.27, result.expected_total_brl)
        self.assertEqual(0.0, result.difference_brl)
        self.assertTrue(result.reconciled)

    def test_marks_difference_over_tolerance_as_unreconciled(self):
        repository = PaymentRepositoryFake([
            {"payment_sequential": 1, "payment_type": "boleto", "payment_value": "212.38"},
        ])
        order = OrderProductResult("order-1", "delivered", item_total_brl=194.0, freight_total_brl=18.27)

        result = OlistPaymentAgent(repository).investigate(CASE, order)

        self.assertEqual(0.11, result.difference_brl)
        self.assertFalse(result.reconciled)

    def test_returns_null_reconciliation_when_order_has_no_items(self):
        repository = PaymentRepositoryFake([
            {"payment_sequential": 1, "payment_type": "credit_card", "payment_value": "10.00"},
        ])
        order = OrderProductResult("order-1", "canceled")

        result = OlistPaymentAgent(repository).investigate(CASE, order)

        self.assertEqual(10.0, result.payment_total_brl)
        self.assertIsNone(result.expected_total_brl)
        self.assertIsNone(result.difference_brl)
        self.assertIsNone(result.reconciled)


if __name__ == "__main__":
    unittest.main()
