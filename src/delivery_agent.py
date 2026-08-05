"""Delivery-domain investigation for Olist dispute cases."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Optional, Protocol, Sequence, Tuple

from .schemas import CaseInput, DeliveryResult, OrderProductResult, SellerHandoff


Timestamp = Tuple[str, datetime]
_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class DeliveryRepository(Protocol):
    """Minimum repository surface required by :class:`OlistDeliveryAgent`."""

    def get_order(self, order_id: str) -> Optional[Mapping[str, object]]: ...

    def get_items_by_order(self, order_id: str) -> Sequence[Mapping[str, object]]: ...


class OlistDeliveryAgent:
    """Calculate delivery and seller-handoff variances without applying policy."""

    def __init__(self, repository: DeliveryRepository) -> None:
        self._repository = repository

    def investigate(self, case: CaseInput, order: OrderProductResult) -> DeliveryResult:
        order_row = self._repository.get_order(order.order_id)
        if order_row is None:
            raise ValueError(f"order not found: {order.order_id}")

        delivered = _timestamp(order_row.get("order_delivered_customer_date"))
        estimated = _timestamp(order_row.get("order_estimated_delivery_date"))
        carrier = _timestamp(order_row.get("order_delivered_carrier_date"))
        delivery_variance = _hours_between(delivered, estimated)

        seller_limits: dict[str, Optional[Timestamp]] = {}
        for item in self._repository.get_items_by_order(order.order_id):
            seller_id = str(item["seller_id"])
            limit = _timestamp(item.get("shipping_limit_date"))
            current_limit = seller_limits.get(seller_id)
            if limit is not None and (current_limit is None or limit[1] < current_limit[1]):
                seller_limits[seller_id] = limit
            elif seller_id not in seller_limits:
                # Preserve a seller with no usable deadline so the result
                # accurately represents missing source data.
                seller_limits[seller_id] = None

        analyses = []
        for seller_id, limit in seller_limits.items():
            handoff_variance = _hours_between(carrier, limit)
            analyses.append(
                SellerHandoff(
                    seller_id=seller_id,
                    shipping_limit_at=None if limit is None else limit[0],
                    handoff_variance_hours=handoff_variance,
                    late_handoff=handoff_variance is not None and handoff_variance > 0,
                )
            )

        return DeliveryResult(
            delivered_at=None if delivered is None else delivered[0],
            estimated_delivery_at=None if estimated is None else estimated[0],
            carrier_handoff_at=None if carrier is None else carrier[0],
            delivery_variance_hours=delivery_variance,
            seller_handoff_analysis=analyses,
            late_handoff_seller_ids=[item.seller_id for item in analyses if item.late_handoff],
        )


def _timestamp(value: object) -> Optional[Timestamp]:
    if value is None or not str(value).strip():
        return None
    raw = str(value)
    return raw, datetime.strptime(raw, _TIMESTAMP_FORMAT)


def _hours_between(later: Optional[Timestamp], earlier: Optional[Timestamp]) -> Optional[float]:
    if later is None or earlier is None:
        return None
    hours = Decimal(str((later[1] - earlier[1]).total_seconds() / 3600))
    return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
