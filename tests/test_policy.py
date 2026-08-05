import unittest

from src.agents.policy import PolicyEngine
from src.schemas import (
    CaseInput, CaseStatus, ContractError, CustomerRequest, CustomerResult,
    DeliveryResult, InvestigationScope, OrderProductResult, PartyType,
    PaymentResult, PrimaryIssue, RootCauseCode, SecondaryIssue, SellerHandoff,
)


CASE = CaseInput(
    case_id="EC_001",
    customer_request=CustomerRequest("vi", "test", "order-1"),
    investigation_scope=InvestigationScope(True, True),
    policy_version="EC_POLICY_V2",
)

NO_HISTORY = CustomerResult("customer-1", [])


def order(status="delivered", items=("order-1:1",), sellers=("seller-1",),
          categories=("cat-1",), item_total=194.0, freight=18.27):
    return OrderProductResult(
        "order-1", status, list(items), list(sellers), ["product-1"],
        list(categories), item_total, freight,
    )


def payment(ids=("order-1:1",), total=212.27, expected=212.27, difference=0.0,
            reconciled=True, types=("credit_card",)):
    return PaymentResult(list(ids), total, expected, difference, reconciled, list(types))


def delivery(variance=None, late_sellers=(), handoff_at="2018-03-15 21:33:51"):
    late = list(late_sellers)
    return DeliveryResult(
        "2018-03-31 15:23:33", "2018-03-28 00:00:00", handoff_at, variance,
        [SellerHandoff(seller, "2018-03-15 20:31:15", 1.04, True) for seller in late],
        late,
    )


class PrimaryIssueTests(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()

    def test_canceled_order_with_payment_outranks_late_delivery(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(status="canceled"), payment(),
            delivery(variance=87.39, late_sellers=["seller-1"]),
        )

        self.assertIs(PrimaryIssue.CANCELED_ORDER_PAID, result.primary_issue)
        self.assertEqual(212.27, result.recommended_refund_brl)
        self.assertEqual(["issue_full_refund", "verify_refund_completion"],
                         result.resolution_actions)
        self.assertEqual(PartyType.PLATFORM, result.responsible_parties[0].party_type)
        self.assertEqual("OLIST_PLATFORM", result.responsible_parties[0].party_id)

    def test_unavailable_order_with_payment(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(status="unavailable"), payment(), delivery(),
        )

        self.assertIs(PrimaryIssue.UNAVAILABLE_ORDER_PAID, result.primary_issue)
        self.assertIs(RootCauseCode.ORDER_UNAVAILABLE_AFTER_PAYMENT,
                      result.ranked_causes[0].cause_code)

    def test_canceled_order_without_payment_is_not_refundable(self):
        with self.assertRaisesRegex(ContractError, "does not match any"):
            self.engine.evaluate(
                CASE, NO_HISTORY, order(status="canceled"),
                payment(ids=[], total=0.0, expected=212.27, difference=-212.27,
                        reconciled=False, types=[]),
                delivery(),
            )

    def test_late_delivery_blames_seller_when_handoff_is_late(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(), payment(),
            delivery(variance=87.39, late_sellers=["seller-1"]),
        )

        self.assertIs(PrimaryIssue.LATE_DELIVERY_SELLER, result.primary_issue)
        self.assertEqual(18.27, result.recommended_refund_brl)
        self.assertIs(RootCauseCode.SELLER_HANDOFF_AFTER_LIMIT,
                      result.ranked_causes[0].cause_code)
        self.assertEqual(0.92, result.confidence)
        self.assertEqual([(PartyType.SELLER, "seller-1")],
                         [(p.party_type, p.party_id) for p in result.responsible_parties])
        self.assertEqual(["refund_freight", "review_seller_handoff"],
                         result.resolution_actions)

    def test_late_delivery_blames_logistics_when_no_seller_is_late(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(), payment(), delivery(variance=12.0),
        )

        self.assertIs(PrimaryIssue.LATE_DELIVERY_LOGISTICS, result.primary_issue)
        self.assertIs(RootCauseCode.CARRIER_DELIVERED_AFTER_ESTIMATE,
                      result.ranked_causes[0].cause_code)
        self.assertEqual([(PartyType.LOGISTICS_PROVIDER, "LOGISTICS_PROVIDER")],
                         [(p.party_type, p.party_id) for p in result.responsible_parties])
        self.assertIn("review_carrier_delay", result.resolution_actions)

    def test_valid_split_payment_when_delivered_on_time(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(),
            payment(ids=["order-1:1", "order-1:2"]),
            delivery(variance=-24.0),
        )

        self.assertIs(PrimaryIssue.VALID_SPLIT_PAYMENT, result.primary_issue)
        self.assertEqual(0.0, result.recommended_refund_brl)
        self.assertIs(CaseStatus.NO_ACTION, result.case_status)
        # The primary action already explains the split; no allocation follow-up.
        self.assertEqual(["explain_valid_split_payment"], result.resolution_actions)

    def test_split_payment_that_does_not_reconcile_falls_through(self):
        with self.assertRaisesRegex(ContractError, "does not match any"):
            self.engine.evaluate(
                CASE, NO_HISTORY, order(),
                payment(ids=["order-1:1", "order-1:2"], difference=5.0,
                        reconciled=False),
                delivery(variance=-24.0),
            )

    def test_unsupported_late_claim_when_delivered_within_estimate(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(), payment(), delivery(variance=-48.0),
        )

        self.assertIs(PrimaryIssue.UNSUPPORTED_LATE_CLAIM, result.primary_issue)
        self.assertIs(CaseStatus.NO_ACTION, result.case_status)
        self.assertIs(RootCauseCode.DELIVERY_WITHIN_ESTIMATE,
                      result.ranked_causes[0].cause_code)
        self.assertEqual([], result.responsible_parties)
        self.assertEqual(["reject_late_refund"], result.resolution_actions)

    def test_zero_variance_is_not_late(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(), payment(), delivery(variance=0.0),
        )

        self.assertIs(PrimaryIssue.UNSUPPORTED_LATE_CLAIM, result.primary_issue)


class SecondaryIssueTests(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()

    def test_secondary_issues_follow_readme_order(self):
        result = self.engine.evaluate(
            CASE, CustomerResult("customer-1", ["old-order"]),
            order(items=["order-1:1", "order-1:2"], sellers=["seller-1", "seller-2"],
                  categories=["cat-1", "cat-2"]),
            payment(ids=["order-1:1", "order-1:2"]),
            delivery(variance=-24.0),
        )

        self.assertEqual(
            [SecondaryIssue.MULTI_ITEM_ORDER, SecondaryIssue.MULTI_SELLER_ORDER,
             SecondaryIssue.SPLIT_PAYMENT, SecondaryIssue.REPEAT_CUSTOMER,
             SecondaryIssue.MULTIPLE_CATEGORIES],
            result.secondary_issues,
        )

    def test_repeated_seller_id_is_not_multi_seller(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY,
            order(items=["order-1:1", "order-1:2"], sellers=["seller-1", "seller-1"],
                  categories=["cat-1", "cat-1"]),
            payment(), delivery(variance=-24.0),
        )

        self.assertEqual([SecondaryIssue.MULTI_ITEM_ORDER], result.secondary_issues)

    def test_no_secondary_issues_on_simple_order(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(), payment(), delivery(variance=-24.0),
        )

        self.assertEqual([], result.secondary_issues)


class EdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()

    def test_order_without_items_uses_null_reconciliation(self):
        with self.assertRaisesRegex(ContractError, "does not match any"):
            self.engine.evaluate(
                CASE, NO_HISTORY,
                order(items=[], sellers=[], categories=[], item_total=None, freight=None),
                payment(ids=[], total=0.0, expected=None, difference=None,
                        reconciled=None, types=[]),
                delivery(variance=None, handoff_at=None),
            )

    def test_late_delivery_without_freight_refunds_zero(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(freight=None), payment(),
            delivery(variance=10.0, late_sellers=["seller-1"]),
        )

        self.assertIs(PrimaryIssue.LATE_DELIVERY_SELLER, result.primary_issue)
        self.assertEqual(0.0, result.recommended_refund_brl)
        self.assertIs(CaseStatus.NO_ACTION, result.case_status)

    def test_responsible_parties_capped_at_three(self):
        sellers = ["seller-1", "seller-2", "seller-3", "seller-4"]
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(sellers=sellers), payment(),
            delivery(variance=10.0, late_sellers=sellers),
        )

        self.assertEqual(3, len(result.responsible_parties))

    def test_actions_capped_at_five(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(sellers=["seller-1", "seller-2"]),
            payment(ids=["order-1:1", "order-1:2"]),
            delivery(variance=10.0, late_sellers=["seller-1"]),
        )

        self.assertEqual(
            ["refund_freight", "review_seller_handoff",
             "coordinate_multi_seller_case", "verify_payment_allocation"],
            result.resolution_actions,
        )

    def test_confidence_stays_within_range(self):
        result = self.engine.evaluate(
            CASE, NO_HISTORY, order(), payment(reconciled=False),
            delivery(variance=10.0),
        )

        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_rejects_policy_handoff_for_another_order(self):
        with self.assertRaisesRegex(ContractError, "does not match claimed order"):
            self.engine.evaluate(
                CASE, NO_HISTORY,
                OrderProductResult("other-order", "delivered"),
                payment(), delivery(variance=-24.0),
            )

    def test_rejects_unknown_late_seller(self):
        with self.assertRaisesRegex(ContractError, "outside the order"):
            self.engine.evaluate(
                CASE, NO_HISTORY, order(), payment(),
                delivery(variance=10.0, late_sellers=["other-seller"]),
            )

    def test_rejects_unknown_policy_version(self):
        case = CaseInput(
            case_id="EC_001",
            customer_request=CustomerRequest("vi", "test", "order-1"),
            investigation_scope=InvestigationScope(True, True),
            policy_version="EC_POLICY_V1",
        )
        # CaseInput.validate() also rejects this, so build it without validation.
        object.__setattr__(case, "policy_version", "EC_POLICY_V1")

        with self.assertRaises(ContractError):
            self.engine.evaluate(case, NO_HISTORY, order(), payment(), delivery())


if __name__ == "__main__":
    unittest.main()
