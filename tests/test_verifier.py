import unittest
from dataclasses import replace

from src.agents.verifier import OutputVerifier, VerificationError
from src.coordinator import assemble_output
from src.schemas import (
    CaseInput, CaseStatus, CustomerRequest, CustomerResult, DeliveryResult,
    InvestigationScope, OrderProductResult, PartyType, PaymentResult,
    PolicyResult, PrimaryIssue, RankedCause, ResponsibleParty, RootCauseCode,
    SecondaryIssue, SellerHandoff,
)

ORDER_ID = "order-1"

CASE = CaseInput(
    case_id="EC_001",
    customer_request=CustomerRequest("vi", "test", ORDER_ID),
    investigation_scope=InvestigationScope(True, True),
    policy_version="EC_POLICY_V2",
)

CUSTOMER = CustomerResult("customer-1", ["old-order"])

ORDER = OrderProductResult(
    ORDER_ID, "delivered", [f"{ORDER_ID}:1"], ["seller-1"],
    ["product-1"], ["category-1"], 194.0, 18.27,
)

PAYMENT = PaymentResult([f"{ORDER_ID}:1"], 212.27, 212.27, 0.0, True, ["credit_card"])

DELIVERY = DeliveryResult(
    "2018-03-31 15:23:33", "2018-03-28 00:00:00", "2018-03-15 21:33:51", 87.39,
    [SellerHandoff("seller-1", "2018-03-15 20:31:15", 1.04, True)], ["seller-1"],
)

POLICY = PolicyResult(
    PrimaryIssue.LATE_DELIVERY_SELLER, [SecondaryIssue.REPEAT_CUSTOMER],
    CaseStatus.ACTION_REQUIRED, 0.92,
    [RankedCause(RootCauseCode.SELLER_HANDOFF_AFTER_LIMIT, 1)],
    [ResponsibleParty(PartyType.SELLER, "seller-1")],
    18.27, ["refund_freight", "review_seller_handoff"],
)


def build(customer=CUSTOMER, order=ORDER, payment=PAYMENT, delivery=DELIVERY,
          policy=POLICY):
    return assemble_output(CASE, customer, order, payment, delivery, policy)


def violations(**kwargs):
    return OutputVerifier().collect(CASE, build(**kwargs))


class HappyPathTests(unittest.TestCase):
    def test_accepts_a_well_formed_output(self):
        OutputVerifier().verify(CASE, build())

    def test_accepts_order_without_items(self):
        order = OrderProductResult(ORDER_ID, "canceled", [], [], [], [], None, None)
        payment = PaymentResult([], 0.0, None, None, None, [])
        delivery = DeliveryResult(None, "2018-03-28 00:00:00", None, None, [], [])
        policy = replace(
            POLICY, primary_issue=PrimaryIssue.UNSUPPORTED_LATE_CLAIM,
            secondary_issues=[], case_status=CaseStatus.NO_ACTION,
            ranked_causes=[RankedCause(RootCauseCode.DELIVERY_WITHIN_ESTIMATE, 1)],
            responsible_parties=[], recommended_refund_brl=0.0,
            resolution_actions=["reject_late_refund"],
        )

        OutputVerifier().verify(CASE, build(order=order, payment=payment,
                                            delivery=delivery, policy=policy))


class EvidenceTests(unittest.TestCase):
    def test_rejects_malformed_evidence_prefix(self):
        output = build()
        output.evidence_ids.append("invoice:order-1")

        found = OutputVerifier().collect(CASE, output)

        self.assertTrue(any("does not match any allowed form" in item for item in found))

    def test_rejects_item_evidence_that_does_not_exist(self):
        output = build()
        output.evidence_ids.append(f"item:{ORDER_ID}:99")

        found = OutputVerifier().collect(CASE, output)

        self.assertTrue(any("outside item_ids" in item for item in found))

    def test_rejects_payment_evidence_that_does_not_exist(self):
        output = build()
        output.evidence_ids.append(f"payment:{ORDER_ID}:7")

        found = OutputVerifier().collect(CASE, output)

        self.assertTrue(any("outside payment_ids" in item for item in found))

    def test_rejects_seller_evidence_outside_seller_ids(self):
        output = build()
        output.evidence_ids.append("seller:seller-unknown")

        found = OutputVerifier().collect(CASE, output)

        self.assertTrue(any("outside seller_ids" in item for item in found))

    def test_rejects_policy_evidence_outside_ranked_causes(self):
        output = build()
        output.evidence_ids.append("policy:DELIVERY_WITHIN_ESTIMATE")

        found = OutputVerifier().collect(CASE, output)

        self.assertTrue(any("outside ranked_causes" in item for item in found))

    def test_rejects_order_evidence_for_a_different_order(self):
        output = build()
        output.evidence_ids.append("order:some-other-order")

        found = OutputVerifier().collect(CASE, output)

        self.assertTrue(any("unknown order" in item for item in found))

    def test_rejects_duplicate_evidence(self):
        output = build()
        output.evidence_ids.append(f"order:{ORDER_ID}")

        found = OutputVerifier().collect(CASE, output)

        self.assertTrue(any("duplicates" in item for item in found))


class NullHandlingTests(unittest.TestCase):
    def test_rejects_zero_instead_of_null_when_order_has_no_items(self):
        order = OrderProductResult(ORDER_ID, "canceled", [], [], [], [], None, None)
        payment = PaymentResult([], 0.0, 0.0, 0.0, False, [])

        found = violations(order=order, payment=payment,
                           delivery=DeliveryResult(None, None, None, None, [], []))

        self.assertTrue(any("expected_total_brl must be null" in item for item in found))
        self.assertTrue(any("difference_brl must be null" in item for item in found))
        self.assertTrue(any("reconciled must be null" in item for item in found))

    def test_rejects_non_boolean_reconciled_when_items_exist(self):
        payment = PaymentResult([f"{ORDER_ID}:1"], 212.27, 212.27, 0.0, "true",
                                ["credit_card"])

        found = violations(payment=payment)

        self.assertTrue(any("reconciled must be a boolean" in item for item in found))


class RoundingTests(unittest.TestCase):
    def test_rejects_unrounded_money(self):
        payment = PaymentResult([f"{ORDER_ID}:1"], 212.2712, 212.27, 0.0, True,
                                ["credit_card"])

        found = violations(payment=payment)

        self.assertTrue(any("payment_total_brl must be rounded" in item for item in found))

    def test_rejects_unrounded_hours(self):
        delivery = replace(DELIVERY, delivery_variance_hours=87.3912)

        found = violations(delivery=delivery)

        self.assertTrue(
            any("delivery_variance_hours must be rounded" in item for item in found)
        )

    def test_rejects_unrounded_refund(self):
        policy = replace(POLICY, recommended_refund_brl=18.2749)

        found = violations(policy=policy)

        self.assertTrue(
            any("recommended_refund_brl must be rounded" in item for item in found)
        )


class TimestampTests(unittest.TestCase):
    def test_rejects_iso_timestamp_with_t_separator(self):
        delivery = replace(DELIVERY, delivered_at="2018-03-31T15:23:33")

        found = violations(delivery=delivery)

        self.assertTrue(any("delivered_at must be" in item for item in found))

    def test_rejects_date_without_time(self):
        delivery = replace(DELIVERY, estimated_delivery_at="2018-03-28")

        found = violations(delivery=delivery)

        self.assertTrue(any("estimated_delivery_at must be" in item for item in found))

    def test_rejects_bad_shipping_limit_timestamp(self):
        delivery = replace(
            DELIVERY,
            seller_handoff_analysis=[
                SellerHandoff("seller-1", "2018/03/15 20:31:15", 1.04, True)
            ],
        )

        found = violations(delivery=delivery)

        self.assertTrue(any("shipping_limit_at must be" in item for item in found))


class AffectedEntityTests(unittest.TestCase):
    def test_rejects_order_id_other_than_the_claimed_one(self):
        order = replace(ORDER, order_id="another-order")

        found = violations(order=order)

        self.assertTrue(any("order_ids must be exactly" in item for item in found))

    def test_rejects_historical_order_inside_affected_entities(self):
        customer = CustomerResult("customer-1", [ORDER_ID])

        found = violations(customer=customer)

        self.assertTrue(any("historical orders leaked" in item for item in found))

    def test_rejects_item_id_belonging_to_another_order(self):
        order = replace(ORDER, item_ids=["other-order:1"])

        found = violations(order=order)

        self.assertTrue(any("is not <claimed_order_id>" in item for item in found))

    def test_rejects_duplicate_seller_ids(self):
        order = replace(ORDER, seller_ids=["seller-1", "seller-1"])

        found = violations(order=order)

        self.assertTrue(any("seller_ids contains duplicates" in item for item in found))


class ConsistencyTests(unittest.TestCase):
    def test_rejects_confidence_outside_range(self):
        output = build()
        output.case_assessment["confidence"] = 1.5

        found = OutputVerifier().collect(CASE, output)

        self.assertTrue(any("outside [0, 1]" in item for item in found))

    def test_rejects_status_that_contradicts_refund(self):
        policy = replace(POLICY, case_status=CaseStatus.NO_ACTION)

        found = violations(policy=policy)

        self.assertTrue(any("contradicts refund" in item for item in found))

    def test_rejects_responsible_seller_missing_from_seller_ids(self):
        policy = replace(
            POLICY, responsible_parties=[ResponsibleParty(PartyType.SELLER, "seller-9")]
        )

        found = violations(policy=policy)

        self.assertTrue(any("missing from seller_ids" in item for item in found))

    def test_rejects_non_dense_cause_ranks(self):
        policy = replace(
            POLICY,
            ranked_causes=[RankedCause(RootCauseCode.SELLER_HANDOFF_AFTER_LIMIT, 2)],
        )

        found = violations(policy=policy)

        self.assertTrue(any("ranks must start at 1" in item for item in found))

    def test_rejects_late_seller_not_marked_late_in_analysis(self):
        delivery = replace(
            DELIVERY,
            seller_handoff_analysis=[
                SellerHandoff("seller-1", "2018-03-15 20:31:15", -1.04, False)
            ],
        )

        found = violations(delivery=delivery)

        self.assertTrue(any("is not marked late" in item for item in found))

    def test_rejects_mismatched_case_id(self):
        other_case = replace(CASE, case_id="EC_002")

        found = OutputVerifier().collect(other_case, build())

        self.assertTrue(any("does not match input" in item for item in found))


class RaiseBehaviourTests(unittest.TestCase):
    def test_verify_raises_and_keeps_the_output_untouched(self):
        policy = replace(POLICY, recommended_refund_brl=18.2749)
        output = build(policy=policy)

        with self.assertRaises(VerificationError) as caught:
            OutputVerifier().verify(CASE, output)

        self.assertEqual("EC_001", caught.exception.case_id)
        self.assertTrue(caught.exception.violations)
        # The verifier must never repair what it rejects.
        self.assertEqual(18.2749,
                         output.financial_resolution["recommended_refund_brl"])

    def test_reports_every_violation_at_once(self):
        order = replace(ORDER, order_id="another-order")
        policy = replace(POLICY, recommended_refund_brl=18.2749)

        found = violations(order=order, policy=policy)

        self.assertGreater(len(found), 1)


if __name__ == "__main__":
    unittest.main()
