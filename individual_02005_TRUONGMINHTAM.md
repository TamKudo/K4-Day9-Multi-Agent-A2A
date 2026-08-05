# Báo cáo cá nhân — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Trương Minh Tâm |
| MSSV | 2A202602005 |
| Khóa/Lớp | K4 / D303 |
| Vai trò chính | Policy Agent, Verifier Agent và QA/release |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Policy Agent | `src/agents/policy.py` | Toàn bộ result typed của 4 domain agent | `PolicyResult`: primary/secondary issue, responsibility, refund, actions | Hoàn thành |
| Verifier Agent | `src/agents/verifier.py` | `CaseInput` và `CaseOutput` đã assemble | Pass hoặc `VerificationError` kèm toàn bộ vi phạm | Hoàn thành |
| Trace sink | `src/trace.py` | Sự kiện từ Coordinator và các LLM agent | `logging/trace.jsonl` của lượt chạy mới nhất | Hoàn thành |
| Batch runner | `run.py` | 50 file `input/EC_*.json` | 50 file `output/`, trace và `logging/metadata.json` | Hoàn thành |
| Test cho phần sở hữu | `tests/test_policy.py`, `tests/test_verifier.py`, `tests/test_run.py` | Fixture không cần CSV | 49 test policy/verifier, 10 test runner | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Tách stub dùng chung | `tests/test_coordinator.py` của Hiển | `tests/stubs.py` sinh ID theo case thay vì hardcode `order-1`; tránh 50 case fail khi cắm vào runner |
| Phân tích bảng điểm 58.6025 | Toàn pipeline | Đối chiếu 50 output với CSV gốc, khoanh vùng lỗi evidence ở `src/coordinator.py` |
| Sửa evidence seller | `src/coordinator.py` của Hiển | 34/50 case thiếu `seller:` evidence → 0; số evidence seller từ 10 lên 59 |
| Tối ưu tốc độ chạy | `src/llm_runtime.py`, `run.py` | Một lượt 50 case từ ~73 phút xuống ~22 phút |
| Retry provider | `src/llm_runtime.py` | Thêm backoff cho 429/5xx; lượt chạy 50/50 không còn case rớt vì rate limit |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Cài đặt `EC_POLICY_V2` | `src/agents/policy.py` | Primary issue theo đúng thứ tự ưu tiên, secondary theo thứ tự đề, refund và action | `python -m unittest tests.test_policy` |
| Hard gate trước khi ghi file | `src/agents/verifier.py` | Chặn evidence sai, null handling sai, rounding sai, timestamp sai định dạng | `python -m unittest tests.test_verifier` |
| Chạy 50 case thật | `run.py`, `logging/trace.jsonl` | 50/50 case, 0 failure, trace 3450 dòng | `python run.py --workers 4` |
| Khai báo model cho chấm điểm | `logging/metadata.json` | `qwen/qwen3-8b`, `8B`, đúng ràng buộc ≤10B của đề | `cat logging/metadata.json` |
| Chẩn đoán mất điểm | `output/`, `data/*.csv` | Khoanh vùng đúng nguyên nhân bằng đối chiếu dữ liệu, không đoán | Script đối chiếu output với CSV |

Artifact cụ thể của phần việc: mọi file trong `output/` đều đi qua `OutputVerifier`
trước khi được ghi. Một case không qua verifier thì không có file output tương ứng,
nên không tồn tại file nào vi phạm schema mà vẫn lọt vào ZIP nộp bài.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Bốn domain agent trả về fact đúng nhưng không ai quyết định case. Policy Agent là
nơi duy nhất áp `EC_POLICY_V2`: chọn primary issue theo thứ tự ưu tiên, gán trách
nhiệm, tính refund và sinh action. Nếu logic này rải rác trong các agent khác thì
không thể kiểm thử riêng và không ai chịu trách nhiệm khi kết quả sai.

Vấn đề thứ hai là hard gate. Đề chấm 0 điểm cho case vi phạm schema, nên cần một
lớp kiểm tra output sau khi assemble nhưng trước khi ghi file. Lớp này phải chỉ
báo lỗi, tuyệt đối không tự sửa — vì sửa âm thầm sẽ che mất bug thật của agent
phía trên.

### Cách triển khai

`PolicyEngine.evaluate` đánh giá primary issue bằng cách thoát ở nhánh khớp đầu
tiên theo đúng thứ tự đề: canceled → unavailable → late_delivery_seller →
late_delivery_logistics → valid_split_payment → unsupported_late_claim. Phân biệt
seller hay logistics chỉ dựa vào `late_handoff_seller_ids` rỗng hay không, không
tự tính lại giờ giấc vì đó là việc của Delivery Agent.

Secondary issue được thêm theo thứ tự nghiệp vụ trong đề chứ không theo thứ tự
phát hiện. `multi_seller_order` và `multiple_categories` dùng `set` để đếm giá trị
khác nhau, nên đơn có 2 item cùng một seller không bị tính nhầm.

Về action: action chính đứng trước, sau đó là các action bổ sung theo thứ tự đề.
`verify_payment_allocation` bị chặn khi primary là `valid_split_payment` vì action
chính đã giải thích split payment.

`OutputVerifier` gom mọi vi phạm rồi mới raise một lần, thay vì dừng ở lỗi đầu
tiên — như vậy sửa một lượt thay vì chạy lại nhiều lần. Phần đắt nhất là evidence:
mỗi ID được dựng lại từ dữ liệu case rồi đối chiếu, không chỉ khớp regex. Ví dụ
`item:<order>:99` sẽ bị bắt nếu `order_item_id = 99` không tồn tại trong
`item_ids`, vì evidence sai bị tính là false positive.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `CaseInput` cùng `CustomerResult`, `OrderProductResult`, `PaymentResult`, `DeliveryResult` |
| Output | `PolicyResult`; Verifier không trả dữ liệu, chỉ raise `VerificationError` |
| Module phụ thuộc | Bốn domain agent; Verifier phụ thuộc `assemble_output` của Coordinator |
| Module sử dụng output | `Coordinator.assemble_output`, `LLMOutputWriterAgent`, QA/release |
| Điều kiện lỗi cần xử lý | Order không có item (`expected_total_brl`, `difference_brl`, `reconciled` phải là `null`), refund vượt trần action, seller chịu trách nhiệm không nằm trong `seller_ids`, timestamp sai định dạng, số tiền chưa làm tròn 2 chữ số |

### Cách xác minh

```bash
python -m unittest tests.test_policy tests.test_verifier
python run.py --workers 4
```

- **Kết quả mong đợi:** Toàn bộ test policy/verifier pass; 50 case được ghi, không case nào failure.
- **Kết quả đã xác minh:** 49 test policy/verifier pass. Lượt chạy thật cho
  `cases=50 written=50 failed=0`, trace 3450 dòng, `case_failed` bằng 0.
- **Artifact/log:** `output/`, `logging/trace.jsonl`, `logging/metadata.json`.
  Không có secret trong các artifact này; API key nằm trong `.env` đã gitignore.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Verifier cần chặn evidence không tồn tại trong CSV, nhưng
  protocol `verify(case, output)` chỉ nhận `CaseInput` và `CaseOutput`, không có
  repository.
- **Các phương án đã cân nhắc:** (1) Đổi contract để Verifier cầm repository và
  truy vấn thẳng CSV; (2) Dựng lại evidence từ `affected_entities` trong chính
  output rồi đối chiếu.
- **Phương án đã chọn:** Phương án 2, kèm cờ `strict_evidence` để nối repository
  sau mà không phá test hiện có.
- **Lý do:** Đổi contract là file của Hiển và ảnh hưởng mọi agent đang chạy, trong
  khi `affected_entities` vốn đã do Order/Payment Agent dựng từ CSV. Đối chiếu nội
  bộ bắt được toàn bộ lỗi evidence do tầng assemble sinh ra mà không cần chạm vào
  ranh giới chung.
- **Hạn chế đã biết:** Nếu Order hoặc Payment Agent trả ID sai ngay từ đầu thì
  Verifier không phát hiện được; nó chỉ đảm bảo output tự nhất quán. Đây là đánh
  đổi có ý thức, không phải thiếu sót bị bỏ qua.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Bảng điểm lần nộp đầu là 58.6025/100, và điều đáng chú ý là
  mọi hạng mục đều nằm trong khoảng 52–60. Sai lệch đều như vậy không giống lỗi
  rải rác ở vài case mà giống một lỗi hệ thống.
- **Bước tái hiện:** Viết script đối chiếu toàn bộ 50 file `output/` với
  `data/olist_*.csv`: entity ID, tổng tiền, timestamp, delivery variance, seller
  handoff, customer history.
- **Những gì đã loại trừ:** Toàn bộ phép tính đúng 0/50 sai lệch — `item_ids`,
  `seller_ids`, `payment_ids`, `item_total`, `freight_total`, `payment_total`,
  ba timestamp giao vận, `delivery_variance_hours`, `seller_handoff_analysis`,
  `customer_unique_id`, `related_order_ids` và `repeat_customer`. Nghĩa là phần
  dữ liệu của Khôi, Toàn và Yến không phải nguyên nhân.
- **Nguyên nhân gốc:** `_evidence_ids` trong `src/coordinator.py` chỉ thêm
  `seller:` cho seller nằm trong `responsible_parties`. Khi bên chịu trách nhiệm
  là `logistics_provider` hoặc `platform`, không seller nào lọt vào evidence dù
  đơn hàng vẫn có seller thật. Kết quả: 34/50 case không có `seller:` evidence,
  toàn repo chỉ có 10 evidence seller.
- **Cách xử lý:** Đưa mọi seller của đơn vào evidence, với seller chịu trách
  nhiệm xếp trước để không bị cắt khi chạm trần 3 seller.
- **Cách xác minh sau khi sửa:** Số `seller:` evidence tăng từ 10 lên 59; số case
  có seller nhưng thiếu seller evidence giảm từ 34 xuống 0. Thêm hai test khóa
  hành vi này: một cho verdict logistics vẫn phải có seller evidence, một cho thứ
  tự ưu tiên seller chịu trách nhiệm.
- **Điều học được:** Điểm số phân bố đều trên mọi hạng mục là dấu hiệu của một
  lỗi chung ở tầng assemble, không phải nhiều lỗi nhỏ độc lập. Đối chiếu output
  với dữ liệu gốc bằng script đáng giá hơn nhiều so với đọc lại code và đoán.

### Blocker chưa xử lý xong

- **Phạm vi bị ảnh hưởng:** Ba giả thuyết còn lại về phần mất điểm, chưa được
  kiểm chứng bằng lần nộp mới.
- **Chi tiết:** (1) `case_status` hiện suy ra từ `refund > 0`, nên đơn giao trễ mà
  freight bằng `null` sẽ ra `no_action`; (2) `confidence` là công thức tôi tự đặt
  vì đề không cho, hiện chỉ sinh hai giá trị 0.95 và 0.85; (3) `ranked_causes`
  luôn trả đúng một cause trong khi trần là 3.
- **Bước tiếp theo:** Nộp lại bản đã sửa evidence trước để đo mức tăng điểm, rồi
  mới sửa tiếp từng giả thuyết. Sửa cả ba cùng lúc sẽ không biết thay đổi nào có
  tác dụng.

## 7. Hiểu biết về luồng end-to-end

1. `run.py` nạp 50 `CaseInput` từ `input/`, kiểm tra tên file khớp `case_id` và
   không trùng lặp, rồi đưa từng case cho Coordinator.
2. Coordinator gọi Customer và Order/Product trước. Payment và Delivery chạy sau
   vì cần `OrderProductResult`. Bốn kết quả typed này được handoff cho Policy.
3. Policy Agent là nơi duy nhất áp `EC_POLICY_V2`. Các domain agent chỉ trả fact,
   không quyết định refund hay trách nhiệm; ngược lại Policy không đọc CSV và
   không tự tính lại số liệu domain.
4. `assemble_output` ánh xạ mọi result sang wire schema và dựng `evidence_ids`.
   Đây là nơi duy nhất thêm các prefix `order:`, `item:`, `payment:`, `seller:`
   và `policy:` — ID trung gian giữa các agent không mang prefix.
5. `validate_limits()` kiểm tra trần array, sau đó Verifier kiểm evidence, null
   handling, rounding, timestamp và tính nhất quán. Case không qua Verifier thì
   không có file output, nên `output/` không bao giờ chứa file vi phạm schema.
6. Mỗi bước ghi trace vào `logging/trace.jsonl`. File này bị truncate mỗi lượt
   chạy vì đề chỉ yêu cầu lượt chạy mới nhất. `metadata.json` khai model, số
   tham số, framework và runtime để chấm điểm kiểm tra ràng buộc ≤10B.
7. Khi nộp, chỉ nén `output/` thành ZIP; source, `.env` và các file audit không
   được đưa vào.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trương Minh Tâm
**Ngày xác nhận:** 2026-08-05
