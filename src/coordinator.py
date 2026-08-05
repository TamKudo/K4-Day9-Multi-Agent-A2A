"""Coordinator orchestration and final output assembly."""

from dataclasses import dataclass
from typing import List

from .contracts import (
    CustomerAgent, DeliveryAgent, OrderProductAgent, PaymentAgent, PolicyAgent,
    TraceSink, VerifierAgent,
)
from .schemas import (
    CaseInput, CaseOutput, CustomerResult, DeliveryResult, OrderProductResult,
    PaymentResult, PolicyResult,
)


@dataclass
class Coordinator:
    customer_agent: CustomerAgent
    order_product_agent: OrderProductAgent
    payment_agent: PaymentAgent
    delivery_agent: DeliveryAgent
    policy_agent: PolicyAgent
    verifier_agent: VerifierAgent
    trace: TraceSink

    def process(self, case: CaseInput) -> CaseOutput:
        """Run one case, perform explicit handoffs, verify, and return output."""
        self.trace.record(case.case_id, "coordinator", "case_started")
        try:
            customer = self._call(case, "customer", self.customer_agent.investigate)
            order = self._call(case, "order_product", self.order_product_agent.investigate)
            payment = self._call(case, "payment", self.payment_agent.investigate, order)
            delivery = self._call(case, "delivery", self.delivery_agent.investigate, order)
            self.trace.record(case.case_id, "coordinator", "handoff", to="policy")
            policy = self.policy_agent.evaluate(case, customer, order, payment, delivery)
            self.trace.record(case.case_id, "policy", "completed")
            output = assemble_output(case, customer, order, payment, delivery, policy)
            output.validate_limits()
            self.verifier_agent.verify(case, output)
            self.trace.record(case.case_id, "verifier", "validation_passed")
            self.trace.record(case.case_id, "coordinator", "case_completed")
            return output
        except Exception as exc:
            self.trace.record(
                case.case_id, "coordinator", "case_failed",
                error_type=type(exc).__name__, error=str(exc),
            )
            raise

    def _call(self, case: CaseInput, name: str, function, *args):
        self.trace.record(case.case_id, "coordinator", "handoff", to=name)
        result = function(case, *args)
        self.trace.record(case.case_id, name, "completed")
        return result


def assemble_output(
    case: CaseInput,
    customer: CustomerResult,
    order: OrderProductResult,
    payment: PaymentResult,
    delivery: DeliveryResult,
    policy: PolicyResult,
) -> CaseOutput:
    """Map typed agent results to the exact submission schema."""
    causes = [
        {"cause_code": item.cause_code.value, "rank": item.rank}
        for item in policy.ranked_causes
    ]
    parties = [
        {"party_type": item.party_type.value, "party_id": item.party_id}
        for item in policy.responsible_parties
    ]
    handoffs = [
        {
            "seller_id": item.seller_id,
            "shipping_limit_at": item.shipping_limit_at,
            "handoff_variance_hours": item.handoff_variance_hours,
            "late_handoff": item.late_handoff,
        }
        for item in delivery.seller_handoff_analysis
    ]
    evidence = _evidence_ids(order, payment, policy)
    return CaseOutput(
        case_id=case.case_id,
        case_assessment={
            "primary_issue": policy.primary_issue.value,
            "secondary_issues": [item.value for item in policy.secondary_issues],
            "case_status": policy.case_status.value,
            "confidence": policy.confidence,
        },
        affected_entities={
            "order_ids": [order.order_id], "item_ids": order.item_ids[:5],
            "seller_ids": order.seller_ids[:3], "payment_ids": payment.payment_ids[:5],
        },
        customer_context={
            "customer_unique_id": customer.customer_unique_id,
            "related_order_ids": customer.related_order_ids[:5],
        },
        product_context={
            "product_ids": order.product_ids[:5],
            "category_names": order.category_names[:5],
        },
        delivery_analysis={
            "delivered_at": delivery.delivered_at,
            "estimated_delivery_at": delivery.estimated_delivery_at,
            "carrier_handoff_at": delivery.carrier_handoff_at,
            "delivery_variance_hours": delivery.delivery_variance_hours,
            "seller_handoff_analysis": handoffs,
            "late_handoff_seller_ids": delivery.late_handoff_seller_ids[:3],
        },
        payment_reconciliation={
            "currency": "BRL", "item_total_brl": order.item_total_brl,
            "freight_total_brl": order.freight_total_brl,
            "expected_total_brl": payment.expected_total_brl,
            "payment_total_brl": payment.payment_total_brl,
            "difference_brl": payment.difference_brl,
            "reconciled": payment.reconciled,
            "payment_types": payment.payment_types,
        },
        root_cause_analysis={"ranked_causes": causes, "responsible_parties": parties},
        evidence_ids=evidence[:20],
        financial_resolution={
            "currency": "BRL",
            "recommended_refund_brl": policy.recommended_refund_brl,
        },
        resolution_actions=policy.resolution_actions[:5],
    )


def _evidence_ids(
    order: OrderProductResult, payment: PaymentResult, policy: PolicyResult
) -> List[str]:
    evidence = [f"order:{order.order_id}"]
    # Mirror affected-entity limits before the global 20-evidence cap so a
    # large order can never crowd out responsible seller or policy evidence.
    evidence.extend(f"item:{item_id}" for item_id in order.item_ids[:5])
    evidence.extend(f"payment:{payment_id}" for payment_id in payment.payment_ids[:5])
    # Every seller on the order is case evidence, not just the responsible one:
    # a logistics or platform verdict still rests on who shipped the order.
    # Responsible sellers lead so they survive the affected-entity limit.
    responsible = [
        party.party_id for party in policy.responsible_parties[:3]
        if party.party_type.value == "seller"
    ]
    seller_ids = responsible + [
        seller_id for seller_id in order.seller_ids if seller_id not in responsible
    ]
    evidence.extend(f"seller:{seller_id}" for seller_id in seller_ids[:3])
    evidence.extend(
        f"policy:{cause.cause_code.value}" for cause in policy.ranked_causes[:3]
    )
    return evidence
