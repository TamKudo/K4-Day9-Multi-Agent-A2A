"""Shared contracts for every agent in the dispute-resolution pipeline.

Domain agents should return the intermediate result dataclasses below.  Only the
coordinator assembles :class:`CaseOutput`; policy decisions belong to PolicyAgent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ContractError(ValueError):
    """Raised when an input or agent result violates the shared contract."""


class PrimaryIssue(str, Enum):
    CANCELED_ORDER_PAID = "canceled_order_paid"
    UNAVAILABLE_ORDER_PAID = "unavailable_order_paid"
    LATE_DELIVERY_SELLER = "late_delivery_seller"
    LATE_DELIVERY_LOGISTICS = "late_delivery_logistics"
    VALID_SPLIT_PAYMENT = "valid_split_payment"
    UNSUPPORTED_LATE_CLAIM = "unsupported_late_claim"


class SecondaryIssue(str, Enum):
    MULTI_ITEM_ORDER = "multi_item_order"
    MULTI_SELLER_ORDER = "multi_seller_order"
    SPLIT_PAYMENT = "split_payment"
    REPEAT_CUSTOMER = "repeat_customer"
    MULTIPLE_CATEGORIES = "multiple_categories"


class CaseStatus(str, Enum):
    ACTION_REQUIRED = "action_required"
    NO_ACTION = "no_action"


class RootCauseCode(str, Enum):
    SELLER_HANDOFF_AFTER_LIMIT = "SELLER_HANDOFF_AFTER_LIMIT"
    CARRIER_DELIVERED_AFTER_ESTIMATE = "CARRIER_DELIVERED_AFTER_ESTIMATE"
    ORDER_CANCELED_AFTER_PAYMENT = "ORDER_CANCELED_AFTER_PAYMENT"
    ORDER_UNAVAILABLE_AFTER_PAYMENT = "ORDER_UNAVAILABLE_AFTER_PAYMENT"
    MULTIPLE_PAYMENTS_RECONCILED = "MULTIPLE_PAYMENTS_RECONCILED"
    DELIVERY_WITHIN_ESTIMATE = "DELIVERY_WITHIN_ESTIMATE"


class PartyType(str, Enum):
    SELLER = "seller"
    LOGISTICS_PROVIDER = "logistics_provider"
    PLATFORM = "platform"


@dataclass(frozen=True)
class CustomerRequest:
    language: str
    message: str
    claimed_order_id: str


@dataclass(frozen=True)
class InvestigationScope:
    include_customer_history: bool
    include_product_context: bool


@dataclass(frozen=True)
class CaseInput:
    case_id: str
    customer_request: CustomerRequest
    investigation_scope: InvestigationScope
    policy_version: str

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "CaseInput":
        try:
            request = raw["customer_request"]
            scope = raw["investigation_scope"]
            result = cls(
                case_id=raw["case_id"],
                customer_request=CustomerRequest(
                    language=request["language"],
                    message=request["message"],
                    claimed_order_id=request["claimed_order_id"],
                ),
                investigation_scope=InvestigationScope(
                    include_customer_history=scope["include_customer_history"],
                    include_product_context=scope["include_product_context"],
                ),
                policy_version=raw["policy_version"],
            )
        except (KeyError, TypeError) as exc:
            raise ContractError(f"invalid case input: missing/invalid {exc}") from exc
        result.validate()
        return result

    def validate(self) -> None:
        if not self.case_id.startswith("EC_"):
            raise ContractError("case_id must use EC_ prefix")
        if not self.customer_request.claimed_order_id:
            raise ContractError("claimed_order_id must not be empty")
        if self.policy_version != "EC_POLICY_V2":
            raise ContractError("only EC_POLICY_V2 is supported")
        if not isinstance(self.investigation_scope.include_customer_history, bool):
            raise ContractError("include_customer_history must be boolean")
        if not isinstance(self.investigation_scope.include_product_context, bool):
            raise ContractError("include_product_context must be boolean")


# Results owned by domain agents.
@dataclass(frozen=True)
class CustomerResult:
    customer_unique_id: Optional[str]
    related_order_ids: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class OrderProductResult:
    order_id: str
    order_status: str
    item_ids: List[str] = field(default_factory=list)
    seller_ids: List[str] = field(default_factory=list)
    product_ids: List[str] = field(default_factory=list)
    category_names: List[str] = field(default_factory=list)
    item_total_brl: Optional[float] = None
    freight_total_brl: Optional[float] = None


@dataclass(frozen=True)
class PaymentResult:
    payment_ids: List[str] = field(default_factory=list)
    payment_total_brl: float = 0.0
    expected_total_brl: Optional[float] = None
    difference_brl: Optional[float] = None
    reconciled: Optional[bool] = None
    payment_types: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SellerHandoff:
    seller_id: str
    shipping_limit_at: Optional[str]
    handoff_variance_hours: Optional[float]
    late_handoff: bool


@dataclass(frozen=True)
class DeliveryResult:
    delivered_at: Optional[str]
    estimated_delivery_at: Optional[str]
    carrier_handoff_at: Optional[str]
    delivery_variance_hours: Optional[float]
    seller_handoff_analysis: List[SellerHandoff] = field(default_factory=list)
    late_handoff_seller_ids: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class RankedCause:
    cause_code: RootCauseCode
    rank: int


@dataclass(frozen=True)
class ResponsibleParty:
    party_type: PartyType
    party_id: str


@dataclass(frozen=True)
class PolicyResult:
    primary_issue: PrimaryIssue
    secondary_issues: List[SecondaryIssue]
    case_status: CaseStatus
    confidence: float
    ranked_causes: List[RankedCause]
    responsible_parties: List[ResponsibleParty]
    recommended_refund_brl: float
    resolution_actions: List[str]

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ContractError("confidence must be between 0 and 1")
        if self.recommended_refund_brl < 0:
            raise ContractError("recommended_refund_brl must not be negative")
        if len(self.ranked_causes) > 3 or len(self.responsible_parties) > 3:
            raise ContractError("policy result exceeds root cause/party limits")
        if len(self.resolution_actions) > 5:
            raise ContractError("policy result exceeds action limit")


@dataclass(frozen=True)
class CaseOutput:
    """Final wire-format contract. Nested dictionaries mirror README exactly."""

    case_id: str
    case_assessment: Dict[str, Any]
    affected_entities: Dict[str, Any]
    customer_context: Dict[str, Any]
    product_context: Dict[str, Any]
    delivery_analysis: Dict[str, Any]
    payment_reconciliation: Dict[str, Any]
    root_cause_analysis: Dict[str, Any]
    evidence_ids: List[str]
    financial_resolution: Dict[str, Any]
    resolution_actions: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return _enum_values(asdict(self))

    def validate_limits(self) -> None:
        limits = {
            "order_ids": 5, "item_ids": 5, "seller_ids": 3, "payment_ids": 5,
        }
        for name, limit in limits.items():
            if len(self.affected_entities[name]) > limit:
                raise ContractError(f"{name} exceeds limit {limit}")
        if len(self.customer_context["related_order_ids"]) > 5:
            raise ContractError("related_order_ids exceeds limit 5")
        if len(self.product_context["product_ids"]) > 5:
            raise ContractError("product_ids exceeds limit 5")
        if len(self.product_context["category_names"]) > 5:
            raise ContractError("category_names exceeds limit 5")
        if len(self.evidence_ids) > 20 or len(self.resolution_actions) > 5:
            raise ContractError("evidence/actions exceed output limit")


def _enum_values(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _enum_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_enum_values(item) for item in value]
    return value
