"""Fixture agents used by tests and by ``run.py --stubs``.

They derive everything from the case's claimed order id so the assembled output
stays self-consistent, letting integration bugs surface before the real agents
land.
"""

from __future__ import annotations

from src.schemas import (
    CaseInput, CustomerResult, DeliveryResult, OrderProductResult,
    PaymentResult, SellerHandoff,
)


class CustomerStub:
    def investigate(self, case: CaseInput) -> CustomerResult:
        return CustomerResult(f"customer-{case.case_id}", [f"history-{case.case_id}"])


class OrderStub:
    def investigate(self, case: CaseInput) -> OrderProductResult:
        order_id = case.customer_request.claimed_order_id
        return OrderProductResult(
            order_id, "delivered", [f"{order_id}:1"], ["seller-1"],
            ["product-1"], ["category-1"], 194.0, 18.27,
        )


class PaymentStub:
    def investigate(self, case: CaseInput, order: OrderProductResult) -> PaymentResult:
        return PaymentResult(
            [f"{order.order_id}:1"], 212.27, 212.27, 0.0, True, ["credit_card"],
        )


class DeliveryStub:
    def investigate(self, case: CaseInput, order: OrderProductResult) -> DeliveryResult:
        return DeliveryResult(
            "2018-03-31 15:23:33", "2018-03-28 00:00:00", "2018-03-15 21:33:51", 87.39,
            [SellerHandoff("seller-1", "2018-03-15 20:31:15", 1.04, True)],
            ["seller-1"],
        )


class EmptyOrderStub:
    """An order with no item rows: the null-handling path."""

    def investigate(self, case: CaseInput) -> OrderProductResult:
        order_id = case.customer_request.claimed_order_id
        return OrderProductResult(order_id, "canceled", [], [], [], [], None, None)


class EmptyPaymentStub:
    def investigate(self, case: CaseInput, order: OrderProductResult) -> PaymentResult:
        return PaymentResult([], 0.0, None, None, None, [])


class EmptyDeliveryStub:
    def investigate(self, case: CaseInput, order: OrderProductResult) -> DeliveryResult:
        return DeliveryResult(None, "2018-03-28 00:00:00", None, None, [], [])
