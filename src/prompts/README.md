# Agent prompt system

Mỗi production agent có đúng một prompt Markdown chuyên biệt. `PromptLoader`
kiểm tra đủ các phần role, objective, ownership, tools, workflow, contracts,
guardrails, errors, handoff và completion criteria trước khi cho phép gọi LLM.

Business rules trong prompt giúp model hiểu domain nhưng không thay thế hard
guardrails và deterministic Python tools.

