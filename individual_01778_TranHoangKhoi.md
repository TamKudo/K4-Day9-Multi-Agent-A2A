# Member Role Report — Day 9: Multi Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Trần Hoàng Khôi |
| MSSV | 2A202601778 |
| Khóa/Lớp | K4 |
| Vai trò chính | Data Repository + Customer Agent |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Data Repository | `src/data_repository.py`; `DataRepository` | 9 CSV trong `data/` | Index truy vấn read-only cho order, customer, item, payment, product, seller, review, geolocation và category translation | Hoàn thành |
| Customer Agent | `src/customer_agent.py`; `CustomerAgent.investigate` | `CaseInput` và `DataRepository` | `CustomerResult(customer_unique_id, related_order_ids)` | Hoàn thành |
| Kiểm thử module | `tests/test_data_repository.py`, `tests/test_customer_agent.py` | Dữ liệu Olist và case mẫu | 8 unit/integration tests cho hai module | Hoàn thành |

Data Repository là dependency dùng chung cho Customer, Order & Product, Payment và Delivery Agent. Customer Agent bàn giao `CustomerResult` cho Coordinator và Policy Agent; nó không tự quyết định policy hoặc refund.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Thống nhất data contract | Coordinator và các domain agent | Chuẩn hóa cách giữ thứ tự nguồn, biểu diễn null, ID trung gian và giới hạn `related_order_ids` để các agent tích hợp nhất quán. |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Nạp và index dữ liệu Olist | `src/data_repository.py` | Nạp đủ 9 dataset; index theo `order_id`, `customer_id`, `customer_unique_id`, `product_id`, `seller_id` và ZIP prefix | `tests/test_data_repository.py` |
| Chuẩn hóa dữ liệu phục vụ tính toán | `DataRepository._read` | Ô rỗng thành `None`; tiền là `Decimal`; timestamp/ID giữ nguyên chuỗi CSV | Test kiểu dữ liệu payment/item và null contract |
| Xây Customer Agent | `CustomerAgent.investigate` | Tìm customer identity và history tối đa 5 order, loại order đang điều tra | `tests/test_customer_agent.py` |
| Kiểm tra lỗi dữ liệu | `ContractError` trong Customer Agent | Báo lỗi khi không tìm thấy order/customer hoặc thiếu `customer_unique_id` | Test missing order/customer |
Một artifact cụ thể của phần việc là `CustomerResult`. Với một case, agent trả về `customer_unique_id` của người mua và `related_order_ids` của các order khác cùng khách. Các ID này là facts lấy trực tiếp từ CSV, không do agent suy đoán.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Nhiều agent phải dùng cùng dữ liệu Olist. Nếu mỗi agent tự mở CSV và tự join, cách xử lý null, kiểu tiền, thứ tự mảng và khóa join có thể khác nhau, dẫn đến output không nhất quán. Ngoài ra, một `customer_id` của Olist chỉ đại diện cho một order, nên không thể dùng trực tiếp để xác định lịch sử mua hàng.

### Cách triển khai

`DataRepository` nạp CSV một lần và tạo các index in-memory. Truy vấn một-nhiều, ví dụ item/payment theo order hoặc orders theo `customer_unique_id`, trả kết quả theo đúng thứ tự CSV. Mỗi truy vấn trả defensive copy để agent không thể sửa dữ liệu gốc trong repository.

Repository chuẩn hóa ô rỗng thành `None`, dùng `Decimal` cho `price`, `freight_value`, `payment_value`, và dùng `int` cho các trường số cần thiết. Timestamp vẫn là chuỗi theo CSV để có thể vừa tính ở agent chuyên trách vừa ghi lại đúng format trong output.

Customer Agent thực hiện chuỗi join: `claimed_order_id -> order.customer_id -> customer.customer_unique_id -> related orders`. Agent loại order đang điều tra, chỉ lấy history khi `include_customer_history=true`, giữ thứ tự nguồn và giới hạn kết quả còn 5 ID. Agent chỉ trả customer facts; việc gắn secondary issue `repeat_customer` thuộc Policy Agent.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `DataRepository(data_dir)` nhận thư mục `data/`; `CustomerAgent.investigate` nhận `CaseInput` có `claimed_order_id` và `investigation_scope` |
| Output | Repository trả `dict`/`list[dict]` read-only theo nghĩa defensive copy; Customer Agent trả `CustomerResult` |
| Module phụ thuộc | `src/schemas.py` cho `CaseInput`, `CustomerResult`, `ContractError`; 9 CSV Olist trong `data/` |
| Module sử dụng output | Coordinator, Policy Agent và các domain agent cần truy vấn dữ liệu |
| Điều kiện lỗi cần xử lý | Thiếu file CSV, duplicate unique key, order/customer không tồn tại, thiếu `customer_unique_id`, order không có related history |

### Cách xác minh

```bash
python -m unittest tests.test_data_repository tests.test_customer_agent -v
```

- **Kết quả mong đợi:** Repository nạp được toàn bộ data, Customer Agent trả identity/history chính xác, giữ scope và giới hạn schema.
- **Kết quả thực tế:** 8 tests của Data Repository và Customer Agent pass; toàn bộ suite hiện có 12 tests pass.
- **Artifact/log:** `tests/test_data_repository.py`, `tests/test_customer_agent.py`; không chứa API key hoặc secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Cần đối soát tiền và tạo output có thứ tự ổn định giữa nhiều agent.
- **Các phương án đã cân nhắc:** (1) mỗi agent tự đọc CSV và dùng `float`; (2) tạo một repository dùng chung, index dữ liệu một lần, dùng `Decimal` cho tiền.
- **Phương án đã chọn:** Data Repository dùng chung, in-memory index, `Decimal` cho giá/phí/payment và defensive copy cho kết quả truy vấn.
- **Lý do:** Phương án này tránh sai số `float`, tránh lặp code join và đảm bảo các agent nhận cùng facts theo thứ tự nguồn. Nó cũng làm test và tái lập kết quả dễ hơn.
- **Bằng chứng quyết định phù hợp:** Test xác nhận `payment_value`, `price`, `freight_value` là `Decimal`; test defensive copy xác nhận thay đổi bản trả về không làm thay đổi dữ liệu repository.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** `KeyError: 'product_category_name'` khi index `product_category_name_translation.csv`.
- **Lệnh hoặc bước tái hiện:** Khởi tạo `DataRepository("data")` trước khi xử lý encoding BOM của file translation.
- **Nguyên nhân gốc:** Header đầu tiên của file translation có UTF-8 BOM, khiến tên cột thực tế không khớp chính xác với `product_category_name`.
- **Cách xử lý:** Đọc CSV bằng encoding `utf-8-sig`, tự động loại BOM nhưng vẫn tương thích với các CSV UTF-8 còn lại.
- **Cách xác minh sau khi sửa:** Chạy `python -m unittest tests.test_data_repository -v`; repository nạp được 71 category translations và các test pass.
- **Điều học được:** Khi dùng CSV từ nhiều nguồn, cần xác minh encoding/header như một phần của data contract, không chỉ kiểm tra schema logic.

## 7. Hiểu biết về luồng end-to-end

1. Input case cung cấp `claimed_order_id`. Coordinator gửi cùng `CaseInput` cho các domain agent. Các agent dùng Data Repository để lấy facts liên quan thay vì tự đọc CSV.
2. Customer Agent trả identity và lịch sử; Order & Product Agent trả item/seller/product/category; Payment Agent đối soát tiền; Delivery Agent tính chênh lệch giao hàng và handoff của seller.
3. Policy Agent nhận các typed results để áp dụng `EC_POLICY_V2`, xác định primary/secondary issues, nguyên nhân, bên chịu trách nhiệm, refund và actions. Coordinator ghép thành `CaseOutput`.
4. Verifier kiểm tra schema, null handling, giới hạn mảng, ID evidence và số tiền trước khi ghi JSON. Các output hợp lệ được ghi vào `output/`; trace và metadata phục vụ audit lần chạy.
5. Data quality check khác với policy: Data Repository/Verifier kiểm tra facts, format và contract; Policy Agent chỉ ra quyết định nghiệp vụ dựa trên các facts đã được kiểm tra. Việc tách hai lớp giúp không dùng policy để che lỗi dữ liệu.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Hoàng Khôi
**Ngày xác nhận:** 2026-08-05