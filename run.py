"""Batch runner for the LLM-and-tool multi-agent pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.agents.coordinator import LLMCoordinatorAgent
from src.agents.llm_agents import (
    LLMCustomerAgent, LLMDeliveryAgent, LLMOrderProductAgent, LLMPaymentAgent,
    LLMOutputWriterAgent, LLMPolicyAgent, LLMVerifierAgent,
)
from src.agents.policy import PolicyEngine
from src.agents.verifier import OutputVerifier
from src.coordinator import Coordinator
from src.customer_agent import CustomerAgent as CustomerTool
from src.data_repository import DataRepository
from src.delivery_agent import OlistDeliveryAgent
from src.io import load_cases, write_output
from src.llm_runtime import FakeToolCallingLLM, LLMClient, OpenAIResponsesLLM
from src.order_product_agent import OlistOrderProductAgent
from src.payment_agent import OlistPaymentAgent
from src.schemas import CaseInput, CaseOutput
from src.trace import JsonlTrace

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
TRACE_PATH = ROOT / "logging" / "trace.jsonl"
METADATA_PATH = ROOT / "logging" / "metadata.json"

# Declared in source, never in .env, per the submission rules.
MODEL_NAME = "Qwen/Qwen3-8B"
MODEL_PARAMETER_SIZE = "8B"
FRAMEWORK = "OpenAI Responses API + Python tools"


@dataclass
class AgentBundle:
    """Deterministic tools plus the shared LLM used by every agent wrapper."""

    customer: Any
    order_product: Any
    payment: Any
    delivery: Any
    policy: Any
    verifier: Any
    llm: Any = None

    def into(self, trace: Any):
        # Kept for focused legacy unit tests. Production/stub CLI bundles always
        # have an LLM and therefore always use the agentic path below.
        if self.llm is None:
            return Coordinator(
                self.customer, self.order_product, self.payment, self.delivery,
                self.policy, self.verifier, trace,
            )
        core = Coordinator(
            LLMCustomerAgent(self.llm, self.customer, trace),
            LLMOrderProductAgent(self.llm, self.order_product, trace),
            LLMPaymentAgent(self.llm, self.payment, trace),
            LLMDeliveryAgent(self.llm, self.delivery, trace),
            LLMPolicyAgent(self.llm, self.policy, trace),
            LLMVerifierAgent(self.llm, self.verifier, trace),
            trace,
        )
        return LLMCoordinatorAgent(self.llm, core, trace)


def build_agents(use_stubs: bool, fake_llm: bool = False) -> AgentBundle:
    """Wire the tested tools under LLM agents.

    ``fake_llm`` exercises the complete agent/tool/handoff path without network
    access; it is an integration mode, never submission metadata.
    """
    policy, verifier = PolicyEngine(), OutputVerifier()
    if use_stubs:
        from tests.stubs import (
            CustomerStub, DeliveryStub, OrderStub, PaymentStub,
        )
        return AgentBundle(
            CustomerStub(), OrderStub(), PaymentStub(), DeliveryStub(), policy,
            verifier, FakeToolCallingLLM(),
        )

    repository = DataRepository(ROOT / "data")
    llm: LLMClient = FakeToolCallingLLM() if fake_llm else OpenAIResponsesLLM.from_env()
    return AgentBundle(
        CustomerTool(repository), OlistOrderProductAgent(repository),
        OlistPaymentAgent(repository), OlistDeliveryAgent(repository), policy,
        verifier, llm,
    )


def run(agents: AgentBundle, cases: List[CaseInput], output_dir: Path,
        trace_path: Path) -> Tuple[List[CaseOutput], List[Tuple[str, Exception]]]:
    """Process every case; a failing case never aborts the remaining ones."""
    outputs: List[CaseOutput] = []
    failures: List[Tuple[str, Exception]] = []
    with JsonlTrace(trace_path) as trace:
        coordinator = agents.into(trace)
        output_writer = (
            LLMOutputWriterAgent(agents.llm, write_output, trace)
            if agents.llm is not None else None
        )
        for case in cases:
            try:
                output = coordinator.process(case)
                if output_writer is None:  # focused deterministic unit-test path
                    write_output(output_dir, output)
                else:
                    output_writer.write(output_dir, output)
            except Exception as exc:
                trace.record(
                    case.case_id, "coordinator", "case_failed",
                    error_type=type(exc).__name__, error=str(exc),
                )
                failures.append((case.case_id, exc))
                continue
            outputs.append(output)
    return outputs, failures


def write_metadata(
    path: Path, case_count: int, runtime: str, model: str = MODEL_NAME,
) -> None:
    payload: Dict[str, Any] = {
        "model": model,
        "parameter_size": MODEL_PARAMETER_SIZE,
        "framework": FRAMEWORK,
        "runtime": runtime,
        "cases": case_count,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stubs", action="store_true",
                        help="use fixture tools plus a fake tool-calling LLM")
    parser.add_argument(
        "--fake-llm", action="store_true",
        help="use real Olist tools with a network-free LLM test double",
    )
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--trace", type=Path, default=TRACE_PATH)
    args = parser.parse_args(argv)

    cases = load_cases(args.input_dir)
    agents = build_agents(args.stubs, args.fake_llm)
    outputs, failures = run(agents, cases, args.output_dir, args.trace)

    model = agents.llm.model if agents.llm is not None else MODEL_NAME
    write_metadata(
        METADATA_PATH, len(outputs),
        f"python {sys.version_info.major}.{sys.version_info.minor}", model,
    )

    print(f"cases={len(cases)} written={len(outputs)} failed={len(failures)}")
    for case_id, exc in failures:
        print(f"  {case_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
