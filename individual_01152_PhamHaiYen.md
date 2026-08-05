# Member Role Report — Day 9: Multi Agent A2A

> Mỗi thành viên trong nhóm tự hoàn thành mẫu này để báo cáo đúng vai trò, phần việc và mức hiểu của mình.

## 1. Thông tin cá nhân

| Thông tin       | Nội dung |
| --------------- | -------- |
| Họ và tên       | Phạm Hải Yến |
| MSSV            | 2A202601152 |
| Khóa/Lớp        | K4 |
| Vai trò chính   | Phát triển Payment Agent và Delivery Agent |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| ------------------ | ------------------ | -------------- | ----------------- | ---------- |
| Payment Agent | `src/payment_agent.py` — `OlistPaymentAgent.investigate` | `CaseInput`, `OrderProductResult`, payment rows | `PaymentResult` | Hoàn thành |
| Delivery Agent | `src/delivery_agent.py` — `OlistDeliveryAgent.investigate` | `CaseInput`, `OrderProductResult`, order row và item rows | `DeliveryResult` | Hoàn thành |
| Unit test | `tests/test_payment_agent.py`, `tests/test_delivery_agent.py` | Fake repository và dữ liệu biên | 6 unit test | Hoàn thành |

Phần việc được đối chiếu với commit `f9eeda2` của Git author `phyen1311`. Hai agent chỉ cung cấp kết quả phân tích domain cho Coordinator và Policy Agent, không tự quyết định hoàn tiền hoặc ghi file output.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --------- | ----------------------------- | ------- |
| Kiểm tra tích hợp contract | `src/schemas.py`, `src/coordinator.py` | Kết quả từ hai agent khớp dataclass dùng chung; toàn bộ 10 test hiện có đều đạt |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --------------------- | --------------------------- | ---------------- | ------------- |
| Đối soát thanh toán | `src/payment_agent.py` | Payment IDs/types, payment total, expected total, difference và `reconciled` | 3 test Payment Agent |
| Phân tích giao hàng | `src/delivery_agent.py` | Delivery variance, seller handoff analysis và late-handoff seller IDs | 3 test Delivery Agent |
| Kiểm thử | Hai file trong `tests/` | Cases split payment, lệch ngưỡng, không có item và timestamp/deadline thiếu | `python -m unittest discover -v` |

Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:

Với đơn có item total `194.00 BRL`, freight `18.27 BRL` và hai payment `100.00 + 112.27 BRL`, Payment Agent trả về `expected_total_brl = 212.27`, `difference_brl = 0.0` và `reconciled = true`. Delivery Agent tính được `delivery_variance_hours = 87.39` trong test mẫu và nhận diện seller bàn giao muộn khi carrier nhận hàng sau deadline.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Payment Agent cung cấp bằng chứng thanh toán có khớp giá trị item và phí vận chuyển hay không. Delivery Agent cung cấp bằng chứng đơn giao trễ và seller có bàn giao trễ không. Policy Agent sử dụng hai kết quả này để quyết định trách nhiệm, hoàn tiền và hành động xử lý.

### Cách triển khai

Payment Agent lấy toàn bộ payment row theo `order_id`, giữ thứ tự nguồn để tạo ID dạng `<order_id>:<payment_sequential>`. Agent dùng `Decimal` và `ROUND_HALF_UP` để cộng/trừ tiền BRL đến hai chữ số. Khi có item và freight total, agent tính expected total, chênh lệch và đánh dấu `reconciled` khi chênh lệch tuyệt đối không quá `0.10 BRL`. Đơn không có item trả về `null` cho các trường phụ thuộc item theo contract.

Delivery Agent đọc timestamp giao cho khách, giao dự kiến và bàn giao carrier. Agent tính chênh lệch giờ giao; với mỗi seller, chọn `shipping_limit_date` hợp lệ sớm nhất rồi so sánh với thời điểm carrier nhận hàng. Timestamp thiếu được giữ là `null`; agent không tự gán trách nhiệm.

### Input, output và contract

| Thành phần | Mô tả |
| ---------- | ----- |
| Input | `CaseInput`, `OrderProductResult`; payment rows hoặc order/item rows từ repository |
| Output | `PaymentResult` hoặc `DeliveryResult` trong `src/schemas.py` |
| Module phụ thuộc | `src/schemas.py` và Protocol repository nội bộ của agent |
| Module sử dụng output | `Coordinator.process`, `PolicyAgent.evaluate`, `assemble_output` |
| Điều kiện lỗi cần xử lý | Timestamp thiếu trả về `null`; không tìm thấy order raise `ValueError`; đơn không có item có reconciliation `null` |

### Cách xác minh

```bash
python -m unittest discover -v
```

- **Kết quả mong đợi:** Hai agent tính đúng số tiền, timestamp và xử lý dữ liệu thiếu theo contract.
- **Kết quả thực tế:** 10/10 test đạt: 3 Payment, 3 Delivery, 1 Coordinator và 3 input contract.
- **Artifact/log:** `tests/test_payment_agent.py` và `tests/test_delivery_agent.py`; không chứa secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Tính toán BRL và ngưỡng reconciliation `0.10` dễ sai khi dùng `float` trực tiếp.
- **Các phương án đã cân nhắc:** Dùng `float` xuyên suốt; hoặc dùng `Decimal` nội bộ rồi chuyển sang `float` khi trả output.
- **Phương án đã chọn:** Dùng `Decimal(str(value))` và `ROUND_HALF_UP`; chỉ chuyển sang `float` khi tạo `PaymentResult`.
- **Lý do:** Đúng yêu cầu làm tròn, tránh sai số số thực và không thay đổi schema hiện có.
- **Bằng chứng quyết định phù hợp:** Test chênh lệch `0.11` trả về `reconciled = false`; test split payment trả về difference `0.0` và `reconciled = true`.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Item đầu của một seller thiếu `shipping_limit_date`, nhưng item sau lại có deadline hợp lệ; nếu chỉ giữ giá trị đầu tiên thì seller không được phân tích đúng.
- **Lệnh hoặc bước tái hiện:** Chạy `python -m unittest tests.test_delivery_agent.DeliveryAgentTests.test_uses_later_valid_limit_when_an_earlier_item_limit_is_missing -v`.
- **Nguyên nhân gốc:** Giá trị thiếu ở bản ghi đầu che mất deadline hợp lệ ở bản ghi liên quan sau đó.
- **Cách xử lý:** Thay deadline `None` bằng deadline hợp lệ nếu có; nếu có nhiều deadline hợp lệ thì chọn mốc sớm nhất.
- **Cách xác minh sau khi sửa:** Test đạt; `shipping_limit_at = 2018-03-15 20:31:15` và `late_handoff = true`.
- **Điều học được:** Phải bảo toàn dữ liệu thiếu nhưng vẫn tận dụng dữ liệu hợp lệ xuất hiện ở bản ghi liên quan.

## 7. Hiểu biết về luồng end-to-end

Giải thích ngắn gọn bằng lời của bạn:

1. Câu hỏi Crossref/vector index trong form không áp dụng trực tiếp cho bài này. Luồng tương ứng là JSON case trong `input/` được `load_cases` validate thành `CaseInput`; Coordinator gọi các agent domain và chuyển kết quả cho Policy Agent.
2. Repository không có evaluation set hay ground-truth document IDs. Chất lượng được kiểm tra bằng unit test contract và agent, với cả dữ liệu bình thường lẫn dữ liệu biên.
3. Quality check kiểm tra input/output, giới hạn dữ liệu, số tiền, timestamp và unit test. Freshness monitoring chưa được triển khai; nếu có, nó theo dõi độ mới CSV Olist thay vì đúng/sai của từng case.
4. Cùng test set phải dùng cho baseline, corrupted và repaired để kết quả chỉ khác do thay đổi hệ thống. Trong repository, cùng test suite được chạy sau mỗi thay đổi agent.
5. Repair thành công khi test tái hiện lỗi chuyển sang pass, không tạo regression và output vẫn đúng contract. Test deadline thiếu đã pass cùng toàn bộ suite 10/10.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Phạm Hải Yến
**Ngày xác nhận:** 2026-08-05
