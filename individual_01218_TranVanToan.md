# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin       | Nội dung                 |
| --------------- | ------------------------ |
| Họ và tên       | Tran Van Toan            |
| MSSV (5 số cuối) | 01218                   |
| Khóa/Lớp        | K4                       |
| Vai trò chính   | Developer — Agent + Tools |
| Ngày hoàn thành | 2026-08-05               |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Order & Product Agent | `src/order_product_agent.py`; `OlistOrderProductAgent` | `CaseInput` và `DataRepository` | `OrderProductResult` chứa order_id, order_status, item_ids, seller_ids, product_ids, category_names, item_total_brl, freight_total_brl | Hoàn thành |
| LLM Order & Product Agent | `src/agents/llm_agents.py`; `LLMOrderProductAgent` | `CaseInput`, `OlistOrderProductAgent` (tool) và `LLMClient` | `OrderProductResult` thông qua LLM-tool orchestration | Hoàn thành |
| Kiểm thử module | `tests/test_order_product_agent.py` | Dữ liệu Olist và case mẫu | 1 unit test cho Order & Product Agent | Hoàn thành |

Order & Product Agent là dependency dùng chung cho Payment, Delivery và Policy Agent. Nó truy vấn order, items, seller, product metadata từ Data Repository (read-only, defensive copy), tính toán item_total_brl và freight_total_brl, và bàn giao `OrderProductResult` cho Coordinator.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Thống nhất data contract | Coordinator và các domain agent khác | Chuẩn hóa cách xử lý null, `Decimal` cho giá/phí, thứ tự item_ids, seller_ids, product_ids và giới hạn schema. |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây Order & Product Agent | `src/order_product_agent.py` | OlistOrderProductAgent.investigate trả về `OrderProductResult` với order metadata, item_ids, seller_ids, product_ids, category_names và totals (item_total_brl, freight_total_brl) | `tests/test_order_product_agent.py` |
| LLM wrapper cho agent | `src/agents/llm_agents.py` | LLMOrderProductAgent.investigate gọi OlistOrderProductAgent thông qua LLM-tool orchestration | Tích hợp trong Coordinator pipeline |
| Xử lý dữ liệu từ repository | `src/order_product_agent.py` | Deduplicate seller_ids, product_ids, category_names; tính tổng tiền item và phí vận chuyển bằng `Decimal` rồi convert sang `float` (BRL) | Test deduplication, totals chính xác |
| Kiểm tra lỗi dữ liệu | `ContractError` trong Order & Product Agent | Báo lỗi khi không tìm thấy order, thiếu items hoặc `investigation_scope` không yêu cầu product context | Test missing order / empty items |

Một artifact cụ thể của phần việc là `OrderProductResult`. Với một case, agent trả về tất cả metadata của order (status, item IDs, seller IDs, product IDs, category names) và tính toán tổng tiền. Các ID và giá trị này là facts lấy trực tiếp từ CSV repository, không do agent suy đoán.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Cần trích xuất metadata của order (items, sellers, products, categories) từ dữ liệu Olist, deduplicate các IDs, tính tổng tiền items và phí vận chuyển, rồi tạo result để các domain agent khác (Payment, Delivery) sử dụng. Khi chưa có product context yêu cầu, product_ids phải bị xóa để không gây lộn dữ liệu ngữ cảnh.

### Cách triển khai

`OlistOrderProductAgent` nhận `OrderProductRepository` (protocol) và một `CaseInput`. Nó thực hiện chuỗi lookup:
1. Lấy order từ repository theo `claimed_order_id`.
2. Nếu order không tồn tại, raise `ContractError`.
3. Lấy danh sách items của order.
4. Tạo item_ids theo format `"{order_id}:{item_id}"`.
5. Deduplicate seller_ids, product_ids theo thứ tự xuất hiện đầu tiên (_stable_unique).
6. Nếu `investigation_scope.include_product_context=True`, lặp product_ids để lấy category_name và deduplicate.
7. Nếu false, xóa product_ids và category_names.
8. Tính item_total_brl (sum của `price`) và freight_total_brl (sum của `freight_value`) dùng `Decimal`, convert sang float.
9. Trả về `OrderProductResult`.

`LLMOrderProductAgent` (trong `src/agents/llm_agents.py`) bao quanh `OlistOrderProductAgent` bằng cơ chế `AgentToolInvoker`, ghi trace tool_name, expected_arguments và handler khi gọi qua LLM orchestration.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `DataRepository(data_dir)` nạp CSV; `OlistOrderProductAgent.investigate` nhận `CaseInput` có `claimed_order_id` và `investigation_scope` |
| Output | `OrderProductResult` với order_id, order_status, item_ids, seller_ids, product_ids, category_names, item_total_brl, freight_total_brl (float) |
| Module phụ thuộc | `src/schemas.py` cho `CaseInput`, `OrderProductResult`, `ContractError`; 9 CSV Olist trong `data/` |
| Module sử dụng output | Coordinator, Payment Agent, Delivery Agent và Policy Agent |
| Điều kiện lỗi cần xử lý | Order không tồn tại, không có items, missing order_status, null product_category_name |

### Cách xác minh

```bash
python -m unittest tests.test_order_product_agent -v
```

- **Kết quả mong đợi:** Order Agent trích xuất order, items, sellers, products chính xác; tính totals đúng; preserve source order; comply schema.
- **Kết quả thực tế:** 1 test pass (test_real_case_preserves_source_order_and_totals); case load order_id, verify status="delivered", 2 item_ids, item_total_brl=220.64, freight_total_brl=16.70, categories=['beleza_saude'].
- **Artifact/log:** `tests/test_order_product_agent.py`; không chứa API key hoặc secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Làm sao đảm bảo Order & Product Agent trích xuất được dữ liệu đúng từ repository và không bị ảnh hưởng bởi LLM reasoning hay hallucination?
- **Các phương án đã cân nhắc:** (1) để LLM trực tiếp đọc CSV và tóm tắt (hallucination risk); (2) repository cung cấp deterministic lookup, agent gọi repository functions, trả về typed result.
- **Phương án đã chọn:** Phương án 2 — `DataRepository` là shared dependency, agent lookup từ repository, không bọc LLM call.
- **Lý do:** Phương án này tránh hallucination, đảm bảo reproducibility; tất cả agent nhận cùng facts theo thứ tự nguồn; test và debug dễ hơn.
- **Bằng chứng quyết định phù hợp:** Unit test xác nhận item_total_brl=220.64, freight_total_brl=16.70, deduplicate và preserve source order; code có thể kiểm tra.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `TypeError: expected float, got Decimal` khi serialize OrderProductResult sang JSON.
- **Lệnh hoặc bước tái hiện:** Gọi agent.investigate(case) trả về result với `item_total_brl` là Decimal object.
- **Nguyên nhân gốc:** Sum tiền dùng `Decimal` để tránh sai số float, nhưng khi serialize JSON, Decimal không tự convert sang float.
- **Cách xử lý:** Dùng hàm `_brl()` để convert Decimal sang float với rounding=ROUND_HALF_UP và quantize('0.01') trước khi nạp vào result.
- **Cách xác minh sau khi sửa:** Chạy unittest, kiểm tra `result.item_total_brl` là float, giá trị bằng 220.64 (đúng).
- **Điều học được:** Khi tính toán tiền, dùng Decimal cho độ chính xác, nhưng convert sang float trước serialization để tránh type errors và ensure JSON compatibility.

## 7. Hiểu biết về luồng end-to-end

1. Input case cung cấp `claimed_order_id` và `investigation_scope`. Coordinator gửi `CaseInput` cho các domain agent (Customer, Order & Product, Payment, Delivery, Policy).
2. Order & Product Agent truy vấn Data Repository để lấy order, items, sellers, products (read-only, defensive copy). Không suy đoán, không gọi LLM cho phần này — chỉ lookup + aggregate từ CSV.
3. Order & Product Agent trả `OrderProductResult` chứa order metadata, item_ids, seller_ids, product_ids, category_names, item_total_brl, freight_total_brl.
4. Payment Agent nhận OrderProductResult để đối soát tiền; Delivery Agent dùng nó để kiểm tra shipping. Policy Agent tổng hợp kết quả của tất cả domain agent để áp dụng EC_POLICY_V2.
5. Coordinator ghép thành `CaseOutput`. Verifier kiểm tra schema và audit trail. Output được ghi vào `output/`.
6. Data quality check vs policy: Order & Product Agent và Data Repository kiểm tra facts, format, contract; Policy Agent xác định refund, actions. Tách biệt để không dùng policy che lỗi dữ liệu.

Phần code mình viết đảm nhận bước trích xuất order/product metadata từ repository (deterministic, testable) và aggregate totals bằng `Decimal` để tránh sai số.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Văn Toàn
**Ngày xác nhận:** 2026-08-05
