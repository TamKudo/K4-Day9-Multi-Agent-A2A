"""Top-level LLM Coordinator Agent."""

from __future__ import annotations

from typing import Any

from ..llm_runtime import AgentToolInvoker, LLMClient
from ..schemas import CaseInput, CaseOutput


class LLMCoordinatorAgent:
    """Use an LLM-selected pipeline tool to coordinate all specialist agents."""

    def __init__(self, llm: LLMClient, pipeline: Any, trace: Any) -> None:
        self.pipeline = pipeline
        self.invoker = AgentToolInvoker(llm, trace)

    def process(self, case: CaseInput) -> CaseOutput:
        return self.invoker.invoke(
            case_id=case.case_id,
            agent_name="coordinator_agent",
            recipient="output_writer",
            tool_name="run_investigation_pipeline",
            tool_description=(
                "Coordinate Customer, OrderProduct, Payment, Delivery, Policy and "
                "Verifier agents for the supplied dispute case."
            ),
            expected_arguments={
                "case_id": case.case_id,
                "order_id": case.customer_request.claimed_order_id,
            },
            handler=lambda: self.pipeline.process(case),
        )

