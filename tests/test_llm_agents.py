import tempfile
import unittest
from pathlib import Path

from run import AgentBundle
from src.agents.llm_agents import LLMOutputWriterAgent
from src.agents.policy import PolicyEngine
from src.agents.verifier import OutputVerifier
from src.io import write_output
from src.llm_runtime import (
    FakeToolCallingLLM, OpenAIChatCompletionsLLM, OpenAIResponsesLLM,
)
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
        prompts = {call["agent"]: call["instructions"] for call in llm.calls}
        self.assertIn("chuyên đối soát", prompts["payment"])
        self.assertIn("sai số 0.10 BRL", prompts["payment"])
        self.assertIn("<runtime_guardrails", prompts["payment"])
        self.assertNotEqual(prompts["customer"], prompts["delivery"])

    def test_output_writer_calls_llm_and_tool(self):
        llm = FakeToolCallingLLM()
        trace = MemoryTrace()
        output = AgentBundle(
            CustomerStub(), OrderStub(), PaymentStub(), DeliveryStub(),
            PolicyEngine(), OutputVerifier(), llm,
        ).into(trace).process(CASE)

        with tempfile.TemporaryDirectory() as tmp:
            destination = LLMOutputWriterAgent(llm, write_output, trace).write(
                Path(tmp), output,
            )

        self.assertEqual("EC_001.json", destination.name)
        self.assertEqual("output_writer", llm.calls[-1]["agent"])
        self.assertEqual("write_case_output", llm.calls[-1]["tool"])


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


class ChatCompletionsAdapterTests(unittest.TestCase):
    def test_auto_tool_call_and_tool_result_round_trip(self):
        class Usage:
            def model_dump(self):
                return {"prompt_tokens": 10, "completion_tokens": 2}

        class Function:
            name = "lookup_order"
            arguments = '{"order_id":"order-1"}'

        class ToolCall:
            id = "call-1"
            function = Function()

        class Message:
            def __init__(self, with_tool):
                self.tool_calls = [ToolCall()] if with_tool else None
                self.content = None if with_tool else "handoff complete"

            def model_dump(self, exclude_none=True):
                if self.tool_calls:
                    return {
                        "role": "assistant", "tool_calls": [{
                            "id": "call-1", "type": "function",
                            "function": {
                                "name": "lookup_order",
                                "arguments": '{"order_id":"order-1"}',
                            },
                        }],
                    }
                return {"role": "assistant", "content": self.content}

        class Response:
            def __init__(self, number):
                self.id = f"chat-{number}"
                self.model = "qwen-test"
                self.usage = Usage()
                self.choices = [type("Choice", (), {"message": Message(number == 1)})()]

        class Completions:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return Response(len(self.calls))

        completions = Completions()
        client = type("Client", (), {
            "chat": type("Chat", (), {"completions": completions})(),
        })()
        llm = OpenAIChatCompletionsLLM(client, "qwen-test")
        schema = {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
            "additionalProperties": False,
        }

        decision = llm.request_tool(
            agent_name="order", instructions="call tool",
            user_input='{"order_id":"order-1"}', tool_name="lookup_order",
            tool_description="lookup", parameters=schema,
        )
        completion = llm.submit_tool_result(
            agent_name="order", decision=decision, result={"status": "delivered"},
        )

        first, second = completions.calls
        self.assertEqual("auto", first["tool_choice"])
        self.assertEqual("lookup_order", first["tools"][0]["function"]["name"])
        self.assertEqual("tool", second["messages"][-1]["role"])
        self.assertEqual("handoff complete", completion.text)


if __name__ == "__main__":
    unittest.main()
