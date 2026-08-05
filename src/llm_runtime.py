"""LLM tool-calling boundary shared by every agent.

The model chooses a forced, domain-scoped function. Python validates its
arguments and executes the deterministic tool. This keeps calculations
reproducible while ensuring every production agent performs an auditable LLM
invocation and tool call.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Mapping, Protocol, TypeVar

from .schemas import ContractError

T = TypeVar("T")


@dataclass(frozen=True)
class ToolDecision:
    tool_name: str
    arguments: Dict[str, Any]
    response_id: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass(frozen=True)
class AgentCompletion:
    response_id: str
    model: str
    text: str
    usage: Dict[str, Any] = field(default_factory=dict)


class LLMClient(Protocol):
    model: str

    def request_tool(
        self,
        *,
        agent_name: str,
        instructions: str,
        user_input: str,
        tool_name: str,
        tool_description: str,
        parameters: Dict[str, Any],
    ) -> ToolDecision: ...

    def submit_tool_result(
        self, *, agent_name: str, decision: ToolDecision, result: Any,
    ) -> AgentCompletion: ...


class OpenAIResponsesLLM:
    """OpenAI Responses API adapter using forced function calling."""

    def __init__(self, client: Any, model: str, reasoning_effort: str = "low") -> None:
        self._client = client
        self.model = model
        self.reasoning_effort = reasoning_effort

    @classmethod
    def from_env(cls) -> "OpenAIResponsesLLM":
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("Install dependencies with: pip install -r requirements.txt") from exc
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for a real agent run")
        model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
        effort = os.getenv("OPENAI_REASONING_EFFORT", "low")
        return cls(OpenAI(api_key=api_key), model, effort)

    def request_tool(
        self, *, agent_name: str, instructions: str, user_input: str,
        tool_name: str, tool_description: str, parameters: Dict[str, Any],
    ) -> ToolDecision:
        response = self._client.responses.create(
            model=self.model,
            instructions=instructions,
            input=user_input,
            tools=[{
                "type": "function", "name": tool_name,
                "description": tool_description,
                "parameters": parameters, "strict": True,
            }],
            tool_choice={"type": "function", "name": tool_name},
            reasoning={"effort": self.reasoning_effort},
            max_output_tokens=256,
            metadata={"agent": agent_name},
        )
        calls = [item for item in response.output if item.type == "function_call"]
        if len(calls) != 1 or calls[0].name != tool_name:
            raise ContractError(
                f"{agent_name}: expected one {tool_name} tool call, got {len(calls)}"
            )
        try:
            arguments = json.loads(calls[0].arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ContractError(f"{agent_name}: invalid tool arguments") from exc
        usage = response.usage.model_dump() if response.usage is not None else {}
        return ToolDecision(
            tool_name, arguments, response.id, response.model, usage, calls[0].call_id
        )

    def submit_tool_result(
        self, *, agent_name: str, decision: ToolDecision, result: Any,
    ) -> AgentCompletion:
        response = self._client.responses.create(
            model=self.model,
            previous_response_id=decision.response_id,
            input=[{
                "type": "function_call_output",
                "call_id": decision.call_id,
                "output": json.dumps(_jsonable(result), ensure_ascii=False),
            }],
            max_output_tokens=256,
            reasoning={"effort": self.reasoning_effort},
            metadata={"agent": agent_name, "phase": "tool_result_handoff"},
        )
        usage = response.usage.model_dump() if response.usage is not None else {}
        return AgentCompletion(response.id, response.model, response.output_text, usage)


class FakeToolCallingLLM:
    """Network-free test double that makes the same forced tool decision."""

    model = "fake-tool-calling-llm"

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def request_tool(
        self, *, agent_name: str, instructions: str, user_input: str,
        tool_name: str, tool_description: str, parameters: Dict[str, Any],
    ) -> ToolDecision:
        properties = parameters.get("properties", {})
        marker = json.loads(user_input)
        arguments = {name: marker[name] for name in properties}
        self.calls.append({"agent": agent_name, "tool": tool_name, "arguments": arguments})
        number = len(self.calls)
        return ToolDecision(
            tool_name, arguments, f"fake-{number}", self.model, {}, f"call-{number}"
        )

    def submit_tool_result(
        self, *, agent_name: str, decision: ToolDecision, result: Any,
    ) -> AgentCompletion:
        return AgentCompletion(
            f"{decision.response_id}-complete", self.model,
            f"{agent_name} completed {decision.tool_name}",
        )


class AgentToolInvoker:
    """Enforce LLM -> tool -> handoff and emit a complete audit trace."""

    def __init__(self, llm: LLMClient, trace: Any) -> None:
        self.llm = llm
        self.trace = trace

    def invoke(
        self,
        *,
        case_id: str,
        agent_name: str,
        recipient: str,
        tool_name: str,
        tool_description: str,
        expected_arguments: Mapping[str, str],
        handler: Callable[[], T],
    ) -> T:
        parameters = {
            "type": "object",
            "properties": {
                name: {"type": "string", "description": f"Exact {name} from the case"}
                for name in expected_arguments
            },
            "required": list(expected_arguments),
            "additionalProperties": False,
        }
        self.trace.record(case_id, agent_name, "llm_request", model=self.llm.model)
        decision = self.llm.request_tool(
            agent_name=agent_name,
            instructions=(
                f"You are the {agent_name} Agent. You must call {tool_name} exactly once "
                "with the identifiers supplied by the user. Do not invent or alter IDs."
            ),
            user_input=json.dumps(dict(expected_arguments), ensure_ascii=False),
            tool_name=tool_name,
            tool_description=tool_description,
            parameters=parameters,
        )
        self.trace.record(
            case_id, agent_name, "llm_response", response_id=decision.response_id,
            model=decision.model, usage=decision.usage,
        )
        if decision.arguments != dict(expected_arguments):
            raise ContractError(
                f"{agent_name}: LLM changed protected tool arguments: {decision.arguments}"
            )
        self.trace.record(
            case_id, agent_name, "tool_call", tool=tool_name,
            arguments=decision.arguments,
        )
        try:
            result = handler()
        except Exception as exc:
            self.trace.record(
                case_id, agent_name, "tool_error", tool=tool_name,
                error_type=type(exc).__name__, error=str(exc),
            )
            raise
        self.trace.record(
            case_id, agent_name, "tool_result", tool=tool_name,
            result_type=type(result).__name__,
        )
        self.trace.record(
            case_id, agent_name, "llm_request", model=self.llm.model,
            phase="tool_result_handoff",
        )
        completion = self.llm.submit_tool_result(
            agent_name=agent_name, decision=decision, result=result,
        )
        self.trace.record(
            case_id, agent_name, "llm_response",
            response_id=completion.response_id, model=completion.model,
            usage=completion.usage, phase="tool_result_handoff",
        )
        self.trace.record(case_id, agent_name, "handoff", to=recipient)
        return result


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
