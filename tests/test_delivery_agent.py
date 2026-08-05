import unittest

from src.delivery_agent import OlistDeliveryAgent
from src.schemas import (
    CaseInput, CustomerRequest, InvestigationScope, OrderProductResult,
)


CASE = CaseInput(
    "EC_001", CustomerRequest("vi", "test", "order-1"),
    InvestigationScope(True, True), "EC_POLICY_V2",
)


class DeliveryRepositoryFake:
    def __init__(self, order, items):
        self.order = order
        self.items = items

    def get_order(self, order_id):
        return self.order

    def get_items_by_order(self, order_id):
        return self.items


class DeliveryAgentTests(unittest.TestCase):
    def test_calculates_delivery_and_earliest_limit_per_seller(self):
        repository = DeliveryRepositoryFake(
            {
                "order_delivered_customer_date": "2018-03-31 15:23:33",
                "order_estimated_delivery_date": "2018-03-28 00:00:00",
                "order_delivered_carrier_date": "2018-03-15 21:33:51",
            },
            [
                {"seller_id": "seller-1", "shipping_limit_date": "2018-03-15 20:31:15"},
                {"seller_id": "seller-1", "shipping_limit_date": "2018-03-16 20:31:15"},
                {"seller_id": "seller-2", "shipping_limit_date": "2018-03-16 22:00:00"},
            ],
        )
        order = OrderProductResult("order-1", "delivered")

        result = OlistDeliveryAgent(repository).investigate(CASE, order)

        self.assertEqual(87.39, result.delivery_variance_hours)
        self.assertEqual(2, len(result.seller_handoff_analysis))
        self.assertEqual("2018-03-15 20:31:15", result.seller_handoff_analysis[0].shipping_limit_at)
        self.assertEqual(1.04, result.seller_handoff_analysis[0].handoff_variance_hours)
        self.assertTrue(result.seller_handoff_analysis[0].late_handoff)
        self.assertFalse(result.seller_handoff_analysis[1].late_handoff)
        self.assertEqual(["seller-1"], result.late_handoff_seller_ids)

    def test_preserves_missing_timestamps_as_null(self):
        repository = DeliveryRepositoryFake(
            {
                "order_delivered_customer_date": "",
                "order_estimated_delivery_date": "2018-03-28 00:00:00",
                "order_delivered_carrier_date": None,
            },
            [{"seller_id": "seller-1", "shipping_limit_date": "2018-03-15 20:31:15"}],
        )

        result = OlistDeliveryAgent(repository).investigate(CASE, OrderProductResult("order-1", "canceled"))

        self.assertIsNone(result.delivered_at)
        self.assertIsNone(result.delivery_variance_hours)
        self.assertIsNone(result.seller_handoff_analysis[0].handoff_variance_hours)
        self.assertFalse(result.seller_handoff_analysis[0].late_handoff)

    def test_uses_later_valid_limit_when_an_earlier_item_limit_is_missing(self):
        repository = DeliveryRepositoryFake(
            {
                "order_delivered_customer_date": "2018-03-28 00:00:00",
                "order_estimated_delivery_date": "2018-03-28 00:00:00",
                "order_delivered_carrier_date": "2018-03-15 21:33:51",
            },
            [
                {"seller_id": "seller-1", "shipping_limit_date": None},
                {"seller_id": "seller-1", "shipping_limit_date": "2018-03-15 20:31:15"},
            ],
        )

        result = OlistDeliveryAgent(repository).investigate(CASE, OrderProductResult("order-1", "delivered"))

        self.assertEqual("2018-03-15 20:31:15", result.seller_handoff_analysis[0].shipping_limit_at)
        self.assertTrue(result.seller_handoff_analysis[0].late_handoff)


if __name__ == "__main__":
    unittest.main()
