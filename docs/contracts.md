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

Quy ước:

- ID trung gian bỏ prefix evidence: `item_id` là `<order_id>:<order_item_id>`.
- Coordinator là nơi duy nhất thêm `order:`, `item:`, `payment:`, `seller:` và `policy:`.
- Tiền và số giờ được agent sở hữu phép tính làm tròn hai chữ số.
- Mảng giữ thứ tự nguồn; không dùng `set` nếu làm thay đổi thứ tự.
- Order không có item: các tổng đối soát phụ thuộc item là `None` (`null` khi ghi JSON).
- Agent domain không tự ghi output và không tự áp dụng policy.

