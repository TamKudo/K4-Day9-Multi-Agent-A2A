"""EC_POLICY_V2 evaluation. Owns taxonomy, responsibility, refund and actions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..schemas import (
    CaseInput, CaseStatus, ContractError, CustomerResult, DeliveryResult,
    OrderProductResult, PartyType, PaymentResult, PolicyResult, PrimaryIssue,
    RankedCause, ResponsibleParty, RootCauseCode, SecondaryIssue,
)

PLATFORM_PARTY_ID = "OLIST_PLATFORM"
LOGISTICS_PARTY_ID = "LOGISTICS_PROVIDER"

# Action appended after the primary action, in README order.
FOLLOW_UP_SELLER = "review_seller_handoff"
FOLLOW_UP_CARRIER = "review_carrier_delay"
FOLLOW_UP_REFUND = "verify_refund_completion"
FOLLOW_UP_MULTI_SELLER = "coordinate_multi_seller_case"
FOLLOW_UP_PAYMENT = "verify_payment_allocation"

PRIMARY_ACTIONS = {
    PrimaryIssue.CANCELED_ORDER_PAID: "issue_full_refund",
    PrimaryIssue.UNAVAILABLE_ORDER_PAID: "issue_full_refund",
    PrimaryIssue.LATE_DELIVERY_SELLER: "refund_freight",
    PrimaryIssue.LATE_DELIVERY_LOGISTICS: "refund_freight",
    PrimaryIssue.VALID_SPLIT_PAYMENT: "explain_valid_split_payment",
    PrimaryIssue.UNSUPPORTED_LATE_CLAIM: "reject_late_refund",
}

PRIMARY_CAUSES = {
    PrimaryIssue.CANCELED_ORDER_PAID: RootCauseCode.ORDER_CANCELED_AFTER_PAYMENT,
    PrimaryIssue.UNAVAILABLE_ORDER_PAID: RootCauseCode.ORDER_UNAVAILABLE_AFTER_PAYMENT,
    PrimaryIssue.LATE_DELIVERY_SELLER: RootCauseCode.SELLER_HANDOFF_AFTER_LIMIT,
    PrimaryIssue.LATE_DELIVERY_LOGISTICS: RootCauseCode.CARRIER_DELIVERED_AFTER_ESTIMATE,
    PrimaryIssue.VALID_SPLIT_PAYMENT: RootCauseCode.MULTIPLE_PAYMENTS_RECONCILED,
    PrimaryIssue.UNSUPPORTED_LATE_CLAIM: RootCauseCode.DELIVERY_WITHIN_ESTIMATE,
}

MAX_RESPONSIBLE_PARTIES = 3
MAX_ACTIONS = 5


@dataclass
class PolicyEngine:
    """Deterministic EC_POLICY_V2 engine.

    Reads typed results from the domain agents only; never touches the CSV
    repository and never writes output.
    """

    def evaluate(
        self,
        case: CaseInput,
        customer: CustomerResult,
        order: OrderProductResult,
        payment: PaymentResult,
        delivery: DeliveryResult,
    ) -> PolicyResult:
        if case.policy_version != "EC_POLICY_V2":
            raise ContractError(f"unsupported policy version: {case.policy_version}")

        primary = self._primary_issue(order, payment, delivery)
        parties = self._responsible_parties(primary, delivery)
        refund = self._refund(primary, order, payment)
        secondary = self._secondary_issues(customer, order, payment)
        actions = self._actions(primary, order, refund)
        status = (
            CaseStatus.ACTION_REQUIRED if refund > 0 else CaseStatus.NO_ACTION
        )
        return PolicyResult(
            primary_issue=primary,
            secondary_issues=secondary,
            case_status=status,
            confidence=self._confidence(primary, payment, delivery),
            ranked_causes=[RankedCause(PRIMARY_CAUSES[primary], 1)],
            responsible_parties=parties,
            recommended_refund_brl=refund,
            resolution_actions=actions,
        )

    # -- taxonomy ---------------------------------------------------------
    def _primary_issue(
        self,
        order: OrderProductResult,
        payment: PaymentResult,
        delivery: DeliveryResult,
    ) -> PrimaryIssue:
        """First matching branch wins, in README priority order."""
        paid = payment.payment_total_brl > 0
        if order.order_status == "canceled" and paid:
            return PrimaryIssue.CANCELED_ORDER_PAID
        if order.order_status == "unavailable" and paid:
            return PrimaryIssue.UNAVAILABLE_ORDER_PAID

        if self._delivered_late(delivery):
            if delivery.late_handoff_seller_ids:
                return PrimaryIssue.LATE_DELIVERY_SELLER
            return PrimaryIssue.LATE_DELIVERY_LOGISTICS

        if len(payment.payment_ids) >= 2 and payment.reconciled:
            return PrimaryIssue.VALID_SPLIT_PAYMENT
        return PrimaryIssue.UNSUPPORTED_LATE_CLAIM

    @staticmethod
    def _delivered_late(delivery: DeliveryResult) -> bool:
        variance = delivery.delivery_variance_hours
        return variance is not None and variance > 0

    def _secondary_issues(
        self,
        customer: CustomerResult,
        order: OrderProductResult,
        payment: PaymentResult,
    ) -> List[SecondaryIssue]:
        """Appended in README order, not in detection order."""
        issues: List[SecondaryIssue] = []
        if len(order.item_ids) >= 2:
            issues.append(SecondaryIssue.MULTI_ITEM_ORDER)
        if len(set(order.seller_ids)) >= 2:
            issues.append(SecondaryIssue.MULTI_SELLER_ORDER)
        if len(payment.payment_ids) >= 2:
            issues.append(SecondaryIssue.SPLIT_PAYMENT)
        if customer.related_order_ids:
            issues.append(SecondaryIssue.REPEAT_CUSTOMER)
        if len(set(order.category_names)) >= 2:
            issues.append(SecondaryIssue.MULTIPLE_CATEGORIES)
        return issues

    # -- responsibility ---------------------------------------------------
    def _responsible_parties(
        self, primary: PrimaryIssue, delivery: DeliveryResult
    ) -> List[ResponsibleParty]:
        if primary in (
            PrimaryIssue.CANCELED_ORDER_PAID,
            PrimaryIssue.UNAVAILABLE_ORDER_PAID,
        ):
            return [ResponsibleParty(PartyType.PLATFORM, PLATFORM_PARTY_ID)]
        if primary is PrimaryIssue.LATE_DELIVERY_SELLER:
            return [
                ResponsibleParty(PartyType.SELLER, seller_id)
                for seller_id in delivery.late_handoff_seller_ids[:MAX_RESPONSIBLE_PARTIES]
            ]
        if primary is PrimaryIssue.LATE_DELIVERY_LOGISTICS:
            return [
                ResponsibleParty(PartyType.LOGISTICS_PROVIDER, LOGISTICS_PARTY_ID)
            ]
        return []

    # -- money ------------------------------------------------------------
    def _refund(
        self,
        primary: PrimaryIssue,
        order: OrderProductResult,
        payment: PaymentResult,
    ) -> float:
        if primary in (
            PrimaryIssue.CANCELED_ORDER_PAID,
            PrimaryIssue.UNAVAILABLE_ORDER_PAID,
        ):
            return round(payment.payment_total_brl, 2)
        if primary in (
            PrimaryIssue.LATE_DELIVERY_SELLER,
            PrimaryIssue.LATE_DELIVERY_LOGISTICS,
        ):
            return round(order.freight_total_brl or 0.0, 2)
        return 0.0

    # -- actions ----------------------------------------------------------
    def _actions(
        self, primary: PrimaryIssue, order: OrderProductResult, refund: float
    ) -> List[str]:
        actions = [PRIMARY_ACTIONS[primary]]
        if primary is PrimaryIssue.LATE_DELIVERY_SELLER:
            actions.append(FOLLOW_UP_SELLER)
        elif primary is PrimaryIssue.LATE_DELIVERY_LOGISTICS:
            actions.append(FOLLOW_UP_CARRIER)
        if refund > 0:
            actions.append(FOLLOW_UP_REFUND)
        if len(set(order.seller_ids)) >= 2:
            actions.append(FOLLOW_UP_MULTI_SELLER)
        # The primary action already explains a valid split payment.
        if primary is not PrimaryIssue.VALID_SPLIT_PAYMENT:
            actions.append(FOLLOW_UP_PAYMENT)
        return actions[:MAX_ACTIONS]

    # -- confidence -------------------------------------------------------
    @staticmethod
    def _confidence(
        primary: PrimaryIssue, payment: PaymentResult, delivery: DeliveryResult
    ) -> float:
        """Lower the score when the supporting evidence is incomplete."""
        score = 0.95
        if payment.reconciled is None:
            score -= 0.10
        elif not payment.reconciled:
            score -= 0.05
        if primary in (
            PrimaryIssue.LATE_DELIVERY_SELLER,
            PrimaryIssue.LATE_DELIVERY_LOGISTICS,
        ) and delivery.carrier_handoff_at is None:
            score -= 0.05
        return round(max(0.0, min(1.0, score)), 2)
