"""Load and validate the specialized Markdown prompt for each LLM agent."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict

from .schemas import ContractError


REQUIRED_SECTIONS = (
    "# Role",
    "# Objective",
    "# Ownership",
    "# Available tools",
    "# Required workflow",
    "# Input contract",
    "# Output contract",
    "# Constraints and guardrails",
    "# Missing data and errors",
    "# Handoff protocol",
    "# Completion criteria",
)

PROMPT_FILES: Dict[str, str] = {
    "coordinator_agent": "coordinator.md",
    "customer": "customer.md",
    "order_product": "order_product.md",
    "payment": "payment.md",
    "delivery": "delivery.md",
    "policy": "policy.md",
    "verifier": "verifier.md",
    "output_writer": "output_writer.md",
}


class PromptLoader:
    """Fail closed when an agent prompt is missing or structurally incomplete."""

    def __init__(self, prompt_dir: Path | None = None) -> None:
        self.prompt_dir = prompt_dir or Path(__file__).resolve().parent / "prompts"

    @lru_cache(maxsize=None)
    def load(self, agent_name: str) -> str:
        filename = PROMPT_FILES.get(agent_name)
        if filename is None:
            raise ContractError(f"no prompt registered for agent: {agent_name}")
        path = self.prompt_dir / filename
        if not path.is_file():
            raise ContractError(f"missing prompt file for {agent_name}: {path}")
        prompt = path.read_text(encoding="utf-8").strip()
        missing = [section for section in REQUIRED_SECTIONS if section not in prompt]
        if missing:
            raise ContractError(
                f"prompt {filename} missing required sections: {', '.join(missing)}"
            )
        return prompt

