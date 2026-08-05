"""Integration tests for the shared Olist data-access boundary."""

from decimal import Decimal
from pathlib import Path
import unittest

from src.data_repository import DataRepository


ROOT = Path(__file__).resolve().parents[1]
KNOWN_ORDER = "9b75cdaf2d85857ef023980e15d01546"  # EC_001


class DataRepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository = DataRepository(ROOT / "data")

    def test_loads_every_required_dataset(self) -> None:
        self.assertEqual(99_441, self.repository.counts.orders)
        self.assertEqual(99_441, self.repository.counts.customers)
        self.assertEqual(112_650, self.repository.counts.order_items)
        self.assertEqual(103_886, self.repository.counts.order_payments)
        self.assertEqual(71, self.repository.counts.category_translations)

    def test_customer_agent_query_path(self) -> None:
        order = self.repository.get_order(KNOWN_ORDER)
        self.assertIsNotNone(order)
        customer = self.repository.get_customer(order["customer_id"])
        self.assertIsNotNone(customer)
        history = self.repository.get_orders_by_customer_unique_id(customer["customer_unique_id"])
        self.assertIn(KNOWN_ORDER, [record["order_id"] for record in history])

    def test_calculation_fields_and_null_contract(self) -> None:
        items = self.repository.get_items_by_order(KNOWN_ORDER)
        payments = self.repository.get_payments_by_order(KNOWN_ORDER)
        self.assertTrue(items)
        self.assertTrue(payments)
        self.assertIsInstance(items[0]["price"], Decimal)
        self.assertIsInstance(items[0]["freight_value"], Decimal)
        self.assertIsInstance(payments[0]["payment_value"], Decimal)
        self.assertEqual([], self.repository.get_items_by_order("missing-order"))
        self.assertIsNone(self.repository.get_order("missing-order"))

    def test_returns_defensive_copies_and_compatible_zip_keys(self) -> None:
        payment = self.repository.get_payments_by_order(KNOWN_ORDER)[0]
        payment["payment_value"] = Decimal("0")
        untouched = self.repository.get_payments_by_order(KNOWN_ORDER)[0]
        self.assertNotEqual(Decimal("0"), untouched["payment_value"])

        order = self.repository.get_order(KNOWN_ORDER)
        customer = self.repository.get_customer(order["customer_id"])
        zip_prefix = customer["customer_zip_code_prefix"]
        self.assertIsInstance(zip_prefix, int)
        self.assertEqual(
            self.repository.get_geolocations_by_zip(zip_prefix),
            self.repository.get_geolocations_by_zip(str(zip_prefix)),
        )


if __name__ == "__main__":
    unittest.main()
