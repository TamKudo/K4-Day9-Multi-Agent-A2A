"""Customer-domain agent for identity resolution and order history."""

from __future__ import annotations

from dataclasses import dataclass

from .data_repository import DataRepository
from .schemas import CaseInput, ContractError, CustomerResult


@dataclass(frozen=True)
class CustomerAgent:
    """Resolve the claimed order's customer and, when requested, its history.

    This agent owns only ``customer_context`` facts. It does not classify a
    repeat customer, create evidence, or alter affected entities; those are
    responsibilities of the Policy Agent and Coordinator respectively.
    """

    repository: DataRepository

    MAX_RELATED_ORDER_IDS = 5

    def investigate(self, case: CaseInput) -> CustomerResult:
        """Return a schema-safe customer identity and related order IDs.

        ``customer_id`` identifies one Olist order, so history is resolved by
        ``customer_unique_id``. The claimed order is explicitly excluded: the
        README reserves historical order IDs for ``related_order_ids`` and
        requires the investigated order to remain the only affected order.
        """
        claimed_order_id = case.customer_request.claimed_order_id
        order = self.repository.get_order(claimed_order_id)
        if order is None:
            raise ContractError(f"case {case.case_id}: claimed order not found: {claimed_order_id}")

        customer_id = order["customer_id"]
        customer = self.repository.get_customer(customer_id)
        if customer is None:
            raise ContractError(
                f"case {case.case_id}: customer not found for order {claimed_order_id}: {customer_id}"
            )

        customer_unique_id = customer.get("customer_unique_id")
        if not customer_unique_id:
            raise ContractError(f"case {case.case_id}: customer_unique_id is missing for {customer_id}")

        if not case.investigation_scope.include_customer_history:
            return CustomerResult(customer_unique_id=customer_unique_id, related_order_ids=[])

        related_order_ids = [
            related["order_id"]
            for related in self.repository.get_orders_by_customer_unique_id(customer_unique_id)
            if related["order_id"] != claimed_order_id
        ]
        return CustomerResult(
            customer_unique_id=customer_unique_id,
            related_order_ids=related_order_ids[: self.MAX_RELATED_ORDER_IDS],
        )
