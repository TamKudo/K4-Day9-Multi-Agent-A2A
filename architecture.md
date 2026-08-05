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

Mỗi agent production đều thực hiện hai lượt LLM: lượt đầu bắt buộc chọn đúng
domain tool bằng function calling, lượt sau nhận tool result và hoàn tất handoff.
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

Mỗi handoff dùng dataclass được type hóa. Trace ghi `llm_request`, `llm_response`,
`tool_call`, `tool_result` và `handoff` cho từng agent. Coordinator còn ghi
`case_started`, `case_completed` hoặc `case_failed`. Output chưa qua Verifier
không được coi là hợp lệ. Trace không ghi API key và không đẩy toàn bộ CSV vào
log.

## Runtime

- Production: OpenAI-compatible Responses API, model cố định trong source là
  `Qwen/Qwen3-8B`, reasoning mặc định `low`. Có thể cấu hình endpoint bằng
  `OPENAI_BASE_URL`; không cấu hình model qua `.env`.
- Integration: `--fake-llm` dùng dữ liệu/tool thật và LLM test double, không gọi
  mạng; artifact này không thay thế trace chạy LLM thật khi nộp.
- Mọi production agent dùng cùng một `LLMClient`, model và trace sink.
