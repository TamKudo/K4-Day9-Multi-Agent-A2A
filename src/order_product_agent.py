"""Deterministic Order/Product tool used by the LLM OrderProduct Agent."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol

from .schemas import CaseInput, ContractError, OrderProductResult


class OrderProductRepository(Protocol):
    def get_order(self, order_id: str): ...
    def get_items_by_order(self, order_id: str): ...
    def get_product(self, product_id: str): ...


class OlistOrderProductAgent:
    """Look up order, items and product context without making policy decisions."""

    def __init__(self, repository: OrderProductRepository) -> None:
        self._repository = repository

    def investigate(self, case: CaseInput) -> OrderProductResult:
        order_id = case.customer_request.claimed_order_id
        order = self._repository.get_order(order_id)
        if order is None:
            raise ContractError(f"case {case.case_id}: order not found: {order_id}")

        items = self._repository.get_items_by_order(order_id)
        if not items:
            return OrderProductResult(order_id, str(order["order_status"]))

        item_ids = [f"{order_id}:{item['order_item_id']}" for item in items]
        seller_ids = _stable_unique(str(item["seller_id"]) for item in items)
        product_ids = _stable_unique(str(item["product_id"]) for item in items)
        categories = []
        if case.investigation_scope.include_product_context:
            for product_id in product_ids:
                product = self._repository.get_product(product_id)
                if product and product.get("product_category_name"):
                    categories.append(str(product["product_category_name"]))
            categories = _stable_unique(categories)
        else:
            product_ids = []

        item_total = sum((Decimal(str(item["price"])) for item in items), Decimal())
        freight_total = sum(
            (Decimal(str(item["freight_value"])) for item in items), Decimal()
        )
        return OrderProductResult(
            order_id=order_id,
            order_status=str(order["order_status"]),
            item_ids=item_ids,
            seller_ids=seller_ids,
            product_ids=product_ids,
            category_names=categories,
            item_total_brl=_brl(item_total),
            freight_total_brl=_brl(freight_total),
        )


def _stable_unique(values):
    return list(dict.fromkeys(values))


def _brl(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

