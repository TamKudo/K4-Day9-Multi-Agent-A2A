"""Agent interfaces. Implementations may be deterministic code or LLM-backed."""

from typing import Protocol

from .schemas import (
    CaseInput, CaseOutput, CustomerResult, DeliveryResult, OrderProductResult,
    PaymentResult, PolicyResult,
)


class CustomerAgent(Protocol):
    def investigate(self, case: CaseInput) -> CustomerResult: ...


class OrderProductAgent(Protocol):
    def investigate(self, case: CaseInput) -> OrderProductResult: ...


class PaymentAgent(Protocol):
    def investigate(self, case: CaseInput, order: OrderProductResult) -> PaymentResult: ...


class DeliveryAgent(Protocol):
    def investigate(self, case: CaseInput, order: OrderProductResult) -> DeliveryResult: ...


class PolicyAgent(Protocol):
    def evaluate(
        self,
        case: CaseInput,
        customer: CustomerResult,
        order: OrderProductResult,
        payment: PaymentResult,
        delivery: DeliveryResult,
    ) -> PolicyResult: ...


class VerifierAgent(Protocol):
    def verify(self, case: CaseInput, output: CaseOutput) -> None: ...


class TraceSink(Protocol):
    def record(self, case_id: str, agent: str, event: str, **details: object) -> None: ...

