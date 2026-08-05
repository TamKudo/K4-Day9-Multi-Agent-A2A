# Agent contracts

`src/schemas.py` là nguồn chuẩn duy nhất cho dữ liệu trao đổi giữa các agent.

| Agent | Input | Output |
| --- | --- | --- |
| Customer | `CaseInput` | `CustomerResult` |
| Order & Product | `CaseInput` | `OrderProductResult` |
| Payment | `CaseInput`, `OrderProductResult` | `PaymentResult` |
| Delivery | `CaseInput`, `OrderProductResult` | `DeliveryResult` |
| Policy | toàn bộ kết quả trên | `PolicyResult` |
| Verifier | `CaseInput`, `CaseOutput` | không trả dữ liệu; raise lỗi nếu sai |

Production implementation bọc mỗi deterministic domain operation bằng LLM agent
trong `src/agents/llm_agents.py`. Mỗi agent bắt buộc gọi tool đúng domain, nhận
kết quả tool rồi mới handoff typed result cho Coordinator.

Prompt chuyên biệt được load từ `src/prompts/<agent>.md`. Prompt chỉ mô tả vai
trò và contract; Python schema/tool/verifier vẫn là authority cuối cùng.

Quy ước:

- ID trung gian bỏ prefix evidence: `item_id` là `<order_id>:<order_item_id>`.
- Coordinator là nơi duy nhất thêm `order:`, `item:`, `payment:`, `seller:` và `policy:`.
- Tiền và số giờ được agent sở hữu phép tính làm tròn hai chữ số.
- Mảng giữ thứ tự nguồn; không dùng `set` nếu làm thay đổi thứ tự.
- Order không có item: các tổng đối soát phụ thuộc item là `None` (`null` khi ghi JSON).
- Agent domain không tự ghi output và không tự áp dụng policy.
- Không được dùng LLM để tự cộng tiền, tính giờ hoặc tạo ID; LLM gọi Python tool
  và bàn giao kết quả đã type hóa.
