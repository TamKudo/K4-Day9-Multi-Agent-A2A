import unittest

from src.coordinator import Coordinator
from src.schemas import (
    CaseInput, CaseStatus, CustomerRequest, CustomerResult, DeliveryResult,
    InvestigationScope, OrderProductResult, PartyType, PaymentResult,
    PolicyResult, PrimaryIssue, RankedCause, ResponsibleParty, RootCauseCode,
    SecondaryIssue, SellerHandoff,
)


CASE = CaseInput(
    case_id="EC_001",
    customer_request=CustomerRequest("vi", "test", "order-1"),
    investigation_scope=InvestigationScope(True, True),
    policy_version="EC_POLICY_V2",
)


class CustomerStub:
    def investigate(self, case):
        return CustomerResult("customer-1", ["old-order"])


class OrderStub:
    def investigate(self, case):
        return OrderProductResult(
            "order-1", "delivered", ["order-1:1"], ["seller-1"],
            ["product-1"], ["category-1"], 194.0, 18.27,
        )


class PaymentStub:
    def investigate(self, case, order):
        return PaymentResult(["order-1:1"], 212.27, 212.27, 0.0, True, ["credit_card"])


class DeliveryStub:
    def investigate(self, case, order):
        return DeliveryResult(
            "2018-03-31 15:23:33", "2018-03-28 00:00:00",
            "2018-03-15 21:33:51", 87.39,
            [SellerHandoff("seller-1", "2018-03-15 20:31:15", 1.04, True)],
            ["seller-1"],
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


if __name__ == "__main__":
    unittest.main()
