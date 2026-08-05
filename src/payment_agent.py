"""Payment-domain investigation for Olist dispute cases."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Protocol, Sequence

from .schemas import CaseInput, OrderProductResult, PaymentResult


class PaymentRepository(Protocol):
    """Minimum repository surface required by :class:`OlistPaymentAgent`."""

    def get_payments_by_order(self, order_id: str) -> Sequence[Mapping[str, object]]: ...


class OlistPaymentAgent:
    """Reconcile payment rows against the item totals supplied by Order/Product."""

    def __init__(self, repository: PaymentRepository) -> None:
        self._repository = repository

    def investigate(self, case: CaseInput, order: OrderProductResult) -> PaymentResult:
        payments = self._repository.get_payments_by_order(order.order_id)
        payment_ids = [f"{order.order_id}:{row['payment_sequential']}" for row in payments]
        # Describe methods used, not one entry per payment row. Preserve the
        # first-seen CSV order while removing repeated methods.
        payment_types = list(dict.fromkeys(str(row["payment_type"]) for row in payments))
        payment_total = _round_brl(sum((_decimal(row["payment_value"]) for row in payments), Decimal()))

        # The policy explicitly defines reconciliation as unavailable when no
        # item rows exist; OrderProductAgent represents that with None totals.
        if order.item_total_brl is None or order.freight_total_brl is None:
            return PaymentResult(
                payment_ids=payment_ids,
                payment_total_brl=payment_total,
                expected_total_brl=None,
                difference_brl=None,
                reconciled=None,
                payment_types=payment_types,
            )

        expected = _decimal(order.item_total_brl) + _decimal(order.freight_total_brl)
        difference = _decimal(payment_total) - expected
        return PaymentResult(
            payment_ids=payment_ids,
            payment_total_brl=payment_total,
            expected_total_brl=_round_brl(expected),
            difference_brl=_round_brl(difference),
            reconciled=abs(difference) <= Decimal("0.10"),
            payment_types=payment_types,
        )


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _round_brl(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
