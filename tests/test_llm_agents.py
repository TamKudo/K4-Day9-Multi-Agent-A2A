import unittest

from run import AgentBundle
from src.agents.policy import PolicyEngine
from src.agents.verifier import OutputVerifier
from src.llm_runtime import FakeToolCallingLLM, OpenAIResponsesLLM
from src.schemas import (
    CaseInput, CustomerRequest, InvestigationScope,
)
from src.trace import MemoryTrace
from tests.stubs import CustomerStub, DeliveryStub, OrderStub, PaymentStub


CASE = CaseInput(
    "EC_001", CustomerRequest("vi", "test", "order-1"),
    InvestigationScope(True, True), "EC_POLICY_V2",
)


class AgenticPipelineTests(unittest.TestCase):
    def test_every_agent_calls_llm_and_a_tool(self):
        llm = FakeToolCallingLLM()
        trace = MemoryTrace()
        bundle = AgentBundle(
            CustomerStub(), OrderStub(), PaymentStub(), DeliveryStub(),
            PolicyEngine(), OutputVerifier(), llm,
        )

        output = bundle.into(trace).process(CASE)

        self.assertEqual("EC_001", output.case_id)
        expected = {
            "coordinator_agent", "customer", "order_product", "payment",
            "delivery", "policy", "verifier",
        }
        self.assertEqual(expected, {call["agent"] for call in llm.calls})
        events_by_agent = {}
        for event in trace.events:
            events_by_agent.setdefault(event["agent"], set()).add(event["event"])
        for agent in expected:
            self.assertIn("llm_request", events_by_agent[agent])
            self.assertIn("tool_call", events_by_agent[agent])
            self.assertIn("handoff", events_by_agent[agent])


class ResponsesAdapterTests(unittest.TestCase):
    def test_uses_responses_function_call_and_returns_tool_output(self):
        class Usage:
            def model_dump(self):
                return {"input_tokens": 10, "output_tokens": 2}

        class FunctionCall:
            type = "function_call"
            name = "lookup_order"
            arguments = '{"order_id":"order-1"}'
            call_id = "call-1"

        class Response:
            def __init__(self, number):
                self.id = f"response-{number}"
                self.model = "gpt-test"
                self.usage = Usage()
                self.output = [FunctionCall()] if number == 1 else []
                self.output_text = "handoff complete"

        class Responses:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return Response(len(self.calls))

        class Client:
            def __init__(self):
                self.responses = Responses()

        client = Client()
        llm = OpenAIResponsesLLM(client, "gpt-test")
        schema = {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        }

        decision = llm.request_tool(
            agent_name="order", instructions="call the tool",
            user_input='{"order_id":"order-1"}', tool_name="lookup_order",
            tool_description="lookup", parameters=schema,
        )
        completion = llm.submit_tool_result(
            agent_name="order", decision=decision, result={"status": "delivered"},
        )

        first, second = client.responses.calls
        self.assertEqual({"type": "function", "name": "lookup_order"}, first["tool_choice"])
        self.assertTrue(first["tools"][0]["strict"])
        self.assertEqual("response-1", second["previous_response_id"])
        self.assertEqual("function_call_output", second["input"][0]["type"])
        self.assertEqual("handoff complete", completion.text)


if __name__ == "__main__":
    unittest.main()
