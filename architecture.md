# Multi-Agent E-commerce Dispute Resolution

## Luồng điều phối agentic

```text
CaseInput
   |
LLM Coordinator Agent
   `-- tool: run_investigation_pipeline
          |-- LLM Customer Agent
          |     `-- tool: investigate_customer -> CustomerResult
          |-- LLM OrderProduct Agent
          |     `-- tool: investigate_order_product -> OrderProductResult
          |-- LLM Payment Agent
          |     `-- tool: reconcile_payment -> PaymentResult
          |-- LLM Delivery Agent
          |     `-- tool: analyze_delivery -> DeliveryResult
          |-- LLM Policy Agent
          |     `-- tool: apply_ec_policy_v2 -> PolicyResult
          |-- deterministic schema assembler -> CaseOutput
          |-- LLM Verifier Agent
                `-- tool: verify_case_output -> pass/raise
          `-- LLM Output Writer Agent
                `-- tool: write_case_output -> EC_NNN.json
   |
JSON output + JSONL trace
```

Mỗi agent production thực hiện một lượt LLM để bắt buộc chọn đúng domain tool
bằng function calling; runtime chạy tool rồi handoff typed result trực tiếp.
Phép join, cộng tiền, tính giờ, policy và validation vẫn nằm trong Python tool để
kết quả chính xác và tái lập được. LLM không được tự sửa ID hoặc số liệu tool.

Coordinator cũng là LLM agent: model gọi `run_investigation_pipeline`, pipeline
handoff đến sáu specialist agent và trả `CaseOutput` cho Coordinator trước khi
ghi file. `src/llm_runtime.py` là runtime chung; typed contracts nằm tại
`src/schemas.py` và `docs/contracts.md`.

Mỗi agent có prompt chuyên biệt trong `src/prompts/`. `PromptLoader` bắt buộc đủ
role, ownership, workflow, input/output contract, guardrails, error handling,
handoff và completion criteria. Runtime nối thêm hard guardrails không thể bị
prompt hoặc case data ghi đè; thiết kế chi tiết nằm tại `docs/prompt-design.md`.

## Vai trò và quyền truy cập

| Thành phần | Đọc | Tạo/Trả về | Không sở hữu |
| --- | --- | --- | --- |
| Coordinator Agent | case và agent handoff tools | `CaseOutput`, trace | phép tính domain, policy |
| Customer Agent | customer tool | `CustomerResult` | payment/delivery |
| OrderProduct Agent | order/product tool | `OrderProductResult` | policy |
| Payment Agent | reconciliation tool | `PaymentResult` | quyết định refund |
| Delivery Agent | delivery tool | `DeliveryResult` | quyết định trách nhiệm |
| Policy Agent | deterministic policy tool | `PolicyResult` | ghi file output |
| Verifier Agent | validation tool | pass hoặc raise lỗi | sửa âm thầm output |
| Output Writer Agent | verified `CaseOutput` | file JSON tương ứng | sửa nội dung output |

## Handoff và lỗi

Mỗi agent gọi LLM đúng một lần để chọn domain tool; sau khi local tool chạy,
typed result được handoff trực tiếp, không tốn thêm một lượt LLM chỉ để xác nhận.
Trace thành công được gộp thành đúng một event `agent_step` cho mỗi agent/case,
chứa model, response ID, prompt file, tool, protected arguments, token usage và
đích handoff. Chỉ lỗi mới sinh thêm `agent_error`/`case_failed`. Output chưa qua Verifier
không được coi là hợp lệ. Trace không ghi API key và không đẩy toàn bộ CSV vào
log.

## Runtime

- Production ưu tiên Groq qua OpenAI-compatible Chat Completions, model cố định
  trong source là `llama-3.1-8b-instant` (8B) và ép đích danh domain tool của
  từng agent qua `tool_choice`.
  Runtime vẫn fail-closed nếu model không gọi đúng tool hoặc thay protected
  arguments. Hugging Face `Qwen/Qwen3-8B` còn là fallback bằng
  `OPENAI_API_KEY` + `OPENAI_BASE_URL`; riêng fallback này dùng
  `tool_choice=auto` và `/no_think`.
- Integration: `--fake-llm` dùng dữ liệu/tool thật và LLM test double, không gọi
  mạng; artifact này không thay thế trace chạy LLM thật khi nộp.
- Mọi production agent dùng cùng một `LLMClient`, model và trace sink.
