import unittest

from src.coordinator import Coordinator
from src.schemas import (
    CaseInput, CaseStatus, CustomerRequest, InvestigationScope,
    OrderProductResult, PartyType, PolicyResult, PrimaryIssue, RankedCause,
    ResponsibleParty, RootCauseCode, SecondaryIssue,
)
from tests.stubs import CustomerStub, DeliveryStub, OrderStub, PaymentStub


CASE = CaseInput(
    case_id="EC_001",
    customer_request=CustomerRequest("vi", "test", "order-1"),
    investigation_scope=InvestigationScope(True, True),
    policy_version="EC_POLICY_V2",
)


class PolicyStub:
    def evaluate(self, case, customer, order, payment, delivery):
        return PolicyResult(
            PrimaryIssue.LATE_DELIVERY_SELLER,
            [SecondaryIssue.REPEAT_CUSTOMER], CaseStatus.ACTION_REQUIRED, 0.92,
            [RankedCause(RootCauseCode.SELLER_HANDOFF_AFTER_LIMIT, 1)],
            [ResponsibleParty(PartyType.SELLER, "seller-1")],
            18.27, ["refund_freight", "review_seller_handoff"],
        )


class VerifierStub:
    def __init__(self):
        self.called = False

    def verify(self, case, output):
        self.called = True


class MemoryTrace:
    def __init__(self):
        self.events = []

    def record(self, case_id, agent, event, **details):
        self.events.append((agent, event, details))


class CoordinatorTests(unittest.TestCase):
    def test_orchestrates_and_assembles_wire_schema(self):
        verifier = VerifierStub()
        trace = MemoryTrace()
        coordinator = Coordinator(
            CustomerStub(), OrderStub(), PaymentStub(), DeliveryStub(),
            PolicyStub(), verifier, trace,
        )

        output = coordinator.process(CASE).to_dict()

        self.assertTrue(verifier.called)
        self.assertEqual("late_delivery_seller", output["case_assessment"]["primary_issue"])
        self.assertEqual(18.27, output["financial_resolution"]["recommended_refund_brl"])
        self.assertEqual(
            ["order:order-1", "item:order-1:1", "payment:order-1:1",
             "seller:seller-1", "policy:SELLER_HANDOFF_AFTER_LIMIT"],
            output["evidence_ids"],
        )
        self.assertEqual(("coordinator", "case_started", {}), trace.events[0])
        self.assertEqual(("coordinator", "case_completed", {}), trace.events[-1])

    def test_evidence_covers_every_seller_not_just_the_responsible_one(self):
        """A logistics verdict still rests on who shipped the order."""

        class TwoSellerOrder:
            def investigate(self, case):
                return OrderProductResult(
                    "order-1", "delivered", ["order-1:1", "order-1:2"],
                    ["seller-1", "seller-2"], ["product-1"], ["category-1"],
                    194.0, 18.27,
                )

        class LogisticsPolicy:
            def evaluate(self, case, customer, order, payment, delivery):
                return PolicyResult(
                    PrimaryIssue.LATE_DELIVERY_LOGISTICS, [], CaseStatus.ACTION_REQUIRED,
                    0.95,
                    [RankedCause(RootCauseCode.CARRIER_DELIVERED_AFTER_ESTIMATE, 1)],
                    [ResponsibleParty(PartyType.LOGISTICS_PROVIDER, "LOGISTICS_PROVIDER")],
                    18.27, ["refund_freight"],
                )

        coordinator = Coordinator(
            CustomerStub(), TwoSellerOrder(), PaymentStub(), DeliveryStub(),
            LogisticsPolicy(), VerifierStub(), MemoryTrace(),
        )

        evidence = coordinator.process(CASE).to_dict()["evidence_ids"]

        self.assertIn("seller:seller-1", evidence)
        self.assertIn("seller:seller-2", evidence)

    def test_responsible_seller_leads_the_seller_evidence(self):
        class ManySellerOrder:
            def investigate(self, case):
                return OrderProductResult(
                    "order-1", "delivered", ["order-1:1"],
                    ["seller-a", "seller-b", "seller-c", "seller-late"],
                    ["product-1"], ["category-1"], 194.0, 18.27,
                )

        class LateSellerPolicy:
            def evaluate(self, case, customer, order, payment, delivery):
                return PolicyResult(
                    PrimaryIssue.LATE_DELIVERY_SELLER, [], CaseStatus.ACTION_REQUIRED,
                    0.95, [RankedCause(RootCauseCode.SELLER_HANDOFF_AFTER_LIMIT, 1)],
                    [ResponsibleParty(PartyType.SELLER, "seller-late")],
                    18.27, ["refund_freight"],
                )

        coordinator = Coordinator(
            CustomerStub(), ManySellerOrder(), PaymentStub(), DeliveryStub(),
            LateSellerPolicy(), VerifierStub(), MemoryTrace(),
        )

        sellers = [e for e in coordinator.process(CASE).to_dict()["evidence_ids"]
                   if e.startswith("seller:")]

        self.assertEqual("seller:seller-late", sellers[0])
        self.assertEqual(3, len(sellers))


if __name__ == "__main__":
    unittest.main()
