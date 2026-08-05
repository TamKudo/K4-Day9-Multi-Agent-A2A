"""LLM wrappers around the tested deterministic domain tools."""

from __future__ import annotations

from typing import Any

from ..llm_runtime import AgentToolInvoker, LLMClient
from ..schemas import (
    CaseInput, CaseOutput, CustomerResult, DeliveryResult, OrderProductResult,
    PaymentResult, PolicyResult,
)


class _BaseAgent:
    def __init__(self, llm: LLMClient, tool: Any, trace: Any) -> None:
        self.tool = tool
        self.invoker = AgentToolInvoker(llm, trace)

    def _invoke(self, case: CaseInput, name: str, tool_name: str, handler, **ids):
        return self.invoker.invoke(
            case_id=case.case_id, agent_name=name, recipient="coordinator",
            tool_name=tool_name,
            tool_description=f"Run the verified {name} domain operation for one case.",
            expected_arguments={key: str(value) for key, value in ids.items()},
            handler=handler,
        )


class LLMCustomerAgent(_BaseAgent):
    def investigate(self, case: CaseInput) -> CustomerResult:
        return self._invoke(
            case, "customer", "investigate_customer",
            lambda: self.tool.investigate(case), case_id=case.case_id,
            order_id=case.customer_request.claimed_order_id,
        )


class LLMOrderProductAgent(_BaseAgent):
    def investigate(self, case: CaseInput) -> OrderProductResult:
        return self._invoke(
            case, "order_product", "investigate_order_product",
            lambda: self.tool.investigate(case), case_id=case.case_id,
            order_id=case.customer_request.claimed_order_id,
        )


class LLMPaymentAgent(_BaseAgent):
    def investigate(self, case: CaseInput, order: OrderProductResult) -> PaymentResult:
        return self._invoke(
            case, "payment", "reconcile_payment",
            lambda: self.tool.investigate(case, order), case_id=case.case_id,
            order_id=order.order_id,
        )


class LLMDeliveryAgent(_BaseAgent):
    def investigate(self, case: CaseInput, order: OrderProductResult) -> DeliveryResult:
        return self._invoke(
            case, "delivery", "analyze_delivery",
            lambda: self.tool.investigate(case, order), case_id=case.case_id,
            order_id=order.order_id,
        )


class LLMPolicyAgent(_BaseAgent):
    def evaluate(
        self, case: CaseInput, customer: CustomerResult, order: OrderProductResult,
        payment: PaymentResult, delivery: DeliveryResult,
    ) -> PolicyResult:
        return self._invoke(
            case, "policy", "apply_ec_policy_v2",
            lambda: self.tool.evaluate(case, customer, order, payment, delivery),
            case_id=case.case_id, policy_version=case.policy_version,
        )


class LLMVerifierAgent(_BaseAgent):
    def verify(self, case: CaseInput, output: CaseOutput) -> None:
        self._invoke(
            case, "verifier", "verify_case_output",
            lambda: self.tool.verify(case, output), case_id=case.case_id,
            order_id=case.customer_request.claimed_order_id,
        )

