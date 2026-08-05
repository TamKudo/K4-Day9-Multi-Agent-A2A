"""Batch runner: load 50 cases, run the pipeline, write output/ and trace.jsonl."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.agents.policy import PolicyEngine
from src.agents.verifier import OutputVerifier
from src.coordinator import Coordinator
from src.io import load_cases, write_output
from src.schemas import CaseInput, CaseOutput
from src.trace import JsonlTrace

ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "input"
OUTPUT_DIR = ROOT / "output"
TRACE_PATH = ROOT / "logging" / "trace.jsonl"
METADATA_PATH = ROOT / "logging" / "metadata.json"

# Declared in source, never in .env, per the submission rules.
MODEL_NAME = "deterministic-rules"
MODEL_PARAMETER_SIZE = "0B"
FRAMEWORK = "python-stdlib"


@dataclass
class AgentBundle:
    """The five domain agents plus the verifier the coordinator needs."""

    customer: Any
    order_product: Any
    payment: Any
    delivery: Any
    policy: Any
    verifier: Any

    def into(self, trace: Any) -> Coordinator:
        return Coordinator(
            self.customer, self.order_product, self.payment, self.delivery,
            self.policy, self.verifier, trace,
        )


def build_agents(use_stubs: bool) -> AgentBundle:
    """Wire real agents, falling back to stubs while teammates land theirs."""
    policy, verifier = PolicyEngine(), OutputVerifier()
    if use_stubs:
        from tests.stubs import (
            CustomerStub, DeliveryStub, OrderStub, PaymentStub,
        )
        return AgentBundle(CustomerStub(), OrderStub(), PaymentStub(),
                           DeliveryStub(), policy, verifier)

    from src.repository import OlistRepository  # noqa: F401  (owned by Khoi)
    from src.agents.customer import CustomerInvestigator
    from src.agents.delivery import DeliveryInvestigator
    from src.agents.order_product import OrderProductInvestigator
    from src.agents.payment import PaymentInvestigator

    repository = OlistRepository.load(ROOT / "data")
    return AgentBundle(
        CustomerInvestigator(repository), OrderProductInvestigator(repository),
        PaymentInvestigator(repository), DeliveryInvestigator(repository),
        policy, verifier,
    )


def run(agents: AgentBundle, cases: List[CaseInput], output_dir: Path,
        trace_path: Path) -> Tuple[List[CaseOutput], List[Tuple[str, Exception]]]:
    """Process every case; a failing case never aborts the remaining ones."""
    outputs: List[CaseOutput] = []
    failures: List[Tuple[str, Exception]] = []
    with JsonlTrace(trace_path) as trace:
        coordinator = agents.into(trace)
        for case in cases:
            try:
                output = coordinator.process(case)
            except Exception as exc:  # already traced as case_failed
                failures.append((case.case_id, exc))
                continue
            write_output(output_dir, output)
            outputs.append(output)
    return outputs, failures


def write_metadata(path: Path, case_count: int, runtime: str) -> None:
    payload: Dict[str, Any] = {
        "model": MODEL_NAME,
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
                        help="run with fixture agents instead of the real ones")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--trace", type=Path, default=TRACE_PATH)
    args = parser.parse_args(argv)

    cases = load_cases(args.input_dir)
    agents = build_agents(args.stubs)
    outputs, failures = run(agents, cases, args.output_dir, args.trace)

    write_metadata(METADATA_PATH, len(outputs),
                   f"python {sys.version_info.major}.{sys.version_info.minor}")

    print(f"cases={len(cases)} written={len(outputs)} failed={len(failures)}")
    for case_id, exc in failures:
        print(f"  {case_id}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
