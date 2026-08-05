import json
import tempfile
import unittest
from pathlib import Path

from run import AgentBundle, run, write_metadata
from src.agents.policy import PolicyEngine
from src.agents.verifier import OutputVerifier
from src.io import load_cases
from src.schemas import CaseInput, CustomerRequest, InvestigationScope
from src.trace import JsonlTrace, MemoryTrace
from tests.stubs import (
    CustomerStub, DeliveryStub, EmptyDeliveryStub, EmptyOrderStub,
    EmptyPaymentStub, OrderStub, PaymentStub,
)

INPUT_DIR = Path(__file__).resolve().parent.parent / "input"


def case(case_id="EC_001", order_id="order-1"):
    return CaseInput(
        case_id=case_id,
        customer_request=CustomerRequest("vi", "test", order_id),
        investigation_scope=InvestigationScope(True, True),
        policy_version="EC_POLICY_V2",
    )


def bundle(order=None, payment=None, delivery=None):
    return AgentBundle(
        CustomerStub(), order or OrderStub(), payment or PaymentStub(),
        delivery or DeliveryStub(), PolicyEngine(), OutputVerifier(),
    )


class TraceTests(unittest.TestCase):
    def test_writes_one_json_object_per_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            with JsonlTrace(path) as trace:
                trace.record("EC_001", "coordinator", "case_started")
                trace.record("EC_001", "coordinator", "handoff", to="customer")

            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(2, len(lines))
        first, second = (json.loads(line) for line in lines)
        self.assertEqual("case_started", first["event"])
        self.assertNotIn("details", first)
        self.assertEqual({"to": "customer"}, second["details"])
        self.assertIn("ts", first)

    def test_truncates_previous_run_instead_of_appending(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trace.jsonl"
            with JsonlTrace(path) as trace:
                trace.record("EC_001", "coordinator", "case_started")
            with JsonlTrace(path) as trace:
                trace.record("EC_002", "coordinator", "case_started")

            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(1, len(lines))
        self.assertEqual("EC_002", json.loads(lines[0])["case_id"])

    def test_rejects_recording_outside_the_context_manager(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = JsonlTrace(Path(tmp) / "trace.jsonl")

            with self.assertRaises(RuntimeError):
                trace.record("EC_001", "coordinator", "case_started")

    def test_memory_trace_captures_details(self):
        trace = MemoryTrace()

        trace.record("EC_001", "coordinator", "handoff", to="policy")

        self.assertEqual({"to": "policy"}, trace.events[0]["details"])


class RunnerTests(unittest.TestCase):
    def test_writes_one_output_per_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outputs, failures = run(bundle(), [case("EC_001"), case("EC_002")],
                                    tmp_path / "out", tmp_path / "trace.jsonl")

            written = sorted(path.name for path in (tmp_path / "out").glob("*.json"))

        self.assertEqual([], failures)
        self.assertEqual(2, len(outputs))
        self.assertEqual(["EC_001.json", "EC_002.json"], written)

    def test_a_failing_case_does_not_abort_the_batch(self):
        class Boom(OrderStub):
            def investigate(self, case_input):
                if case_input.case_id == "EC_002":
                    raise RuntimeError("simulated crash")
                return super().investigate(case_input)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cases = [case("EC_001"), case("EC_002"), case("EC_003")]
            outputs, failures = run(bundle(order=Boom()), cases,
                                    tmp_path / "out", tmp_path / "trace.jsonl")
            trace_text = (tmp_path / "trace.jsonl").read_text(encoding="utf-8")

        self.assertEqual(2, len(outputs))
        self.assertEqual(["EC_002"], [case_id for case_id, _ in failures])
        self.assertIn("case_failed", trace_text)

    def test_failing_case_writes_no_output_file(self):
        class Boom(OrderStub):
            def investigate(self, case_input):
                raise RuntimeError("simulated crash")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            run(bundle(order=Boom()), [case("EC_001")],
                tmp_path / "out", tmp_path / "trace.jsonl")

            written = list((tmp_path / "out").glob("*.json")) if (tmp_path / "out").exists() else []

        self.assertEqual([], written)

    def test_ambiguous_order_without_items_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outputs, failures = run(
                bundle(order=EmptyOrderStub(), payment=EmptyPaymentStub(),
                       delivery=EmptyDeliveryStub()),
                [case("EC_001")], tmp_path / "out", tmp_path / "trace.jsonl",
            )

        self.assertEqual([], outputs)
        self.assertEqual(1, len(failures))
        self.assertIn("does not match any EC_POLICY_V2 primary issue",
                      str(failures[0][1]))

    def test_every_supplied_case_passes_the_verifier(self):
        """Integration smoke test over the real 50 inputs, with stub agents."""
        cases = load_cases(INPUT_DIR)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outputs, failures = run(bundle(), cases,
                                    tmp_path / "out", tmp_path / "trace.jsonl")

        self.assertEqual([], [f"{case_id}: {exc}" for case_id, exc in failures])
        self.assertEqual(len(cases), len(outputs))


class MetadataTests(unittest.TestCase):
    def test_declares_model_and_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"

            write_metadata(path, 50, "python 3.11")
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual({"model", "parameter_size", "framework", "runtime", "cases"},
                         set(payload))
        self.assertEqual(50, payload["cases"])

    def test_fake_runtime_is_labeled_as_a_test_double(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            write_metadata(path, 50, "test", "fake-tool-calling-llm")
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual("test-double", payload["parameter_size"])


if __name__ == "__main__":
    unittest.main()
