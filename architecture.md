# Multi-Agent E-commerce Dispute Resolution

## Luồng điều phối

```text
CaseInput
   |
Coordinator
   |-- CustomerAgent -------------------- CustomerResult
   |-- OrderProductAgent ---------------- OrderProductResult
   |       |-- PaymentAgent ------------- PaymentResult
   |       `-- DeliveryAgent ------------ DeliveryResult
   |
   `-- PolicyAgent(all results) ---------- PolicyResult
             |
         assemble CaseOutput
             |
         VerifierAgent
             |
         JSON output + trace
```

Coordinator chỉ điều phối, handoff và ghép output; không chứa logic phân tích
domain hoặc quyết định policy. Các interface nằm tại `src/contracts.py`, kiểu dữ
liệu dùng chung tại `src/schemas.py`, và contract chi tiết tại
`docs/contracts.md`.

## Vai trò và quyền truy cập

| Thành phần | Đọc | Tạo/Trả về | Không sở hữu |
| --- | --- | --- | --- |
| Coordinator | input và kết quả agent | `CaseOutput`, trace, output JSON | phép tính domain, policy |
| CustomerAgent | order/customer index | `CustomerResult` | payment/delivery |
| OrderProductAgent | order/item/product/seller index | `OrderProductResult` | policy |
| PaymentAgent | payment rows, order result | `PaymentResult` | quyết định refund |
| DeliveryAgent | order và shipping limit | `DeliveryResult` | quyết định trách nhiệm |
| PolicyAgent | toàn bộ typed results | `PolicyResult` | ghi file output |
| VerifierAgent | input, output, repository | pass hoặc raise lỗi | sửa âm thầm output |

## Handoff và lỗi

Mỗi handoff dùng dataclass được type hóa. Coordinator ghi `case_started`, từng
`handoff`, `completed`, `validation_passed` và `case_completed`. Nếu một bước
raise exception, Coordinator ghi `case_failed` kèm loại lỗi rồi chuyển lỗi cho
runner xử lý; output chưa qua Verifier không được coi là hợp lệ.
