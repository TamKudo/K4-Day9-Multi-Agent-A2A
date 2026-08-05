# Prompt design và mức độ phân vai

## Cấu trúc bắt buộc

Mỗi prompt trong `src/prompts/` phải có đủ 11 phần được kiểm tra bởi
`PromptLoader`: role, objective, ownership, available tools, workflow, input
contract, output contract, constraints/guardrails, missing-data/errors, handoff
và completion criteria. Thiếu file hoặc thiếu section làm agent fail trước khi
gọi model.

## Ma trận phân vai

| Agent | Ownership | Tool duy nhất | Handoff |
| --- | --- | --- | --- |
| Coordinator | orchestration, completeness | `run_investigation_pipeline` | verified output -> writer |
| Customer | identity, history | `investigate_customer` | `CustomerResult` -> coordinator |
| OrderProduct | order/items/products/totals | `investigate_order_product` | `OrderProductResult` -> coordinator |
| Payment | reconciliation | `reconcile_payment` | `PaymentResult` -> coordinator |
| Delivery | delivery/handoff variance | `analyze_delivery` | `DeliveryResult` -> coordinator |
| Policy | taxonomy/responsibility/refund/actions | `apply_ec_policy_v2` | `PolicyResult` -> coordinator |
| Verifier | final pass/fail gate | `verify_case_output` | validation -> coordinator |
| Output Writer | verified file persistence | `write_case_output` | path -> release layer |

## Prompt guardrail và hard guardrail

Prompt giải thích domain và hành vi mong muốn. Runtime luôn nối thêm một khối
`runtime_guardrails` có priority cao nhất: bắt buộc đúng một tool call, bảo vệ
ID, cấm thêm argument, cấm bypass tool, chống instruction injection từ user/tool
data và cấm tạo kết quả giả khi tool lỗi.

Python vẫn là nguồn thực thi cho join, Decimal, datetime, policy ordering,
schema limits và verification. LLM không có quyền sửa tool result. Trace chỉ ghi
tên file prompt và SHA-256 rút gọn để audit phiên bản, không ghi toàn prompt.

## Nguyên tắc thay đổi prompt

- Thay prompt không được thay đổi wire schema hoặc business rules trong tool.
- Một PR prompt phải chạy `tests/test_prompts.py` và integration test.
- Không copy cùng một prompt cho nhiều agent.
- Không đưa API key, endpoint secret hoặc dữ liệu case cụ thể vào prompt.
- Nếu cần thay ownership/tool/handoff, cập nhật cả kiến trúc và tests.

