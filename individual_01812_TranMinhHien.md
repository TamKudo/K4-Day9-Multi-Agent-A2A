# Báo cáo cá nhân — Day 9: Multi-Agent A2A

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Trần Minh Hiển |
| MSSV | 2A202601812 |
| Khóa/Lớp | K4 / D303 |
| Vai trò chính | Coordinator Agent và shared schema/contracts |
| Ngày hoàn thành | 2026-08-05 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Shared schema | `src/schemas.py` | JSON input và yêu cầu output của đề | Enum, dataclass và giới hạn dùng chung | Hoàn thành |
| Agent contracts | `src/contracts.py`, `docs/contracts.md` | Vai trò và handoff giữa các agent | Protocol typed cho từng specialist | Hoàn thành |
| Coordinator | `src/coordinator.py` | `CaseInput` và kết quả specialist | `CaseOutput` đúng schema | Hoàn thành |
| LLM Coordinator | `src/agents/coordinator.py`, `src/prompts/coordinator.md` | Một case và pipeline tool | Tool call được bảo vệ và handoff tới pipeline | Hoàn thành |
| Kiến trúc chung | `architecture.md`, `docs/prompt-design.md` | Thiết kế multi-agent của nhóm | Sơ đồ, ownership, quyền truy cập và guardrail | Hoàn thành |

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Tích hợp branch | Các specialist agent | Hợp nhất các module qua typed contract chung |
| Chuẩn hóa agentic flow | Toàn pipeline | Coordinator và mọi specialist đều gọi LLM rồi mới dùng domain tool |
| QA/release | Output Writer và pipeline | ZIP có đúng `output/EC_001.json` đến `output/EC_050.json` |
| Debug output và release | Policy, payment và release | Sửa payment type lặp, action guard và kiểm tra chính xác cấu trúc ZIP |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Xây dựng contract đầu vào/đầu ra | `src/schemas.py`, `src/contracts.py` | Một nguồn schema thống nhất cho toàn bộ agent | `python3 -m unittest tests.test_contracts` |
| Điều phối specialist và handoff | `src/coordinator.py` | Customer → Order/Product → Payment/Delivery → Policy → Verifier | `python3 -m unittest tests.test_coordinator` |
| Bắt buộc Coordinator gọi LLM | `src/agents/coordinator.py`, `src/llm_runtime.py` | LLM chọn đúng `run_investigation_pipeline` với protected arguments | `python3 -m unittest tests.test_llm_agents` |
| Đóng gói output | `scripts/qa_release.py`, `submission_output.zip` | Đúng 50 JSON dưới prefix `output/` | `python3 scripts/qa_release.py` |

Artifact cụ thể của phần việc là `CaseOutput` có cùng cấu trúc cho cả 50 case.
Coordinator chỉ assemble kết quả typed từ các specialist; nó không tự truy cập CSV
hoặc tự tính lại nghiệp vụ thuộc domain khác.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Nếu mỗi agent tự trả dictionary không có contract chung, các lỗi như sai enum,
thiếu field, vượt giới hạn array hoặc nhầm ownership chỉ được phát hiện khi ghi
file. Coordinator cũng dễ trở thành một "god agent" vừa truy cập dữ liệu, vừa
áp policy, vừa sửa kết quả specialist. Phần việc của tôi tạo ranh giới typed và
luồng handoff rõ ràng để mỗi agent chỉ sở hữu đúng domain.

### Cách triển khai

`CaseInput.from_dict` chuyển JSON đầu vào thành dataclass và kiểm tra policy
version, order ID cùng kiểu boolean của investigation scope. Mỗi specialist trả
một result type riêng: `CustomerResult`, `OrderProductResult`, `PaymentResult`,
`DeliveryResult` hoặc `PolicyResult`.

Coordinator gọi các specialist theo dependency thực tế. Payment và Delivery chỉ
chạy sau Order/Product vì cần order result. Policy nhận toàn bộ result typed,
sau đó `assemble_output` ánh xạ chúng sang wire schema duy nhất. Output được kiểm
tra giới hạn và qua Verifier trước khi Output Writer ghi JSON.

Ở production, Coordinator và từng specialist đều là LLM agent. Model bị ép gọi
đúng tool của vai trò; runtime so sánh chính xác `case_id`, `order_id` hoặc
`policy_version` trước khi cho phép Python tool chạy. Cách này đáp ứng mục tiêu
luyện tập agent/tool calling nhưng vẫn giữ phép join, tính tiền và tính thời gian
chính xác, tái lập được.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | `CaseInput`: case ID, customer request, investigation scope, policy version |
| Output | `CaseOutput`: assessment, entities, context, delivery, payment, cause/evidence và resolution |
| Module phụ thuộc | Các specialist agent, `PolicyAgent`, `VerifierAgent`, `TraceSink` |
| Module sử dụng output | `LLMOutputWriterAgent`, QA/release và hệ thống chấm ZIP |
| Điều kiện lỗi cần xử lý | Sai policy version, thiếu order, null item totals, tool call sai tên/argument, vượt giới hạn schema |

### Cách xác minh

```bash
python3 -m unittest tests.test_contracts tests.test_coordinator tests.test_llm_agents
python3 run.py
python3 scripts/qa_release.py
unzip -Z1 submission_output.zip
```

- **Kết quả mong đợi:** 50 case được ghi, không có failure; ZIP chứa đúng 50 JSON.
- **Kết quả đã xác minh:** production run đạt `cases=50 written=50 failed=0`,
  focused test đạt 46/46 và QA đạt `validated=50`.
- **Artifact/log:** `output/`, `logging/trace.jsonl`,
  `logging/metadata.json`, `submission_output.zip`.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Đề yêu cầu mọi bước, kể cả Coordinator, đều phải có agent gọi
  LLM; đồng thời output số liệu phải chính xác theo CSV.
- **Các phương án đã cân nhắc:** Cho một LLM duy nhất đọc toàn bộ dữ liệu và sinh
  JSON; hoặc để mỗi LLM agent chọn một tool hẹp, còn tool trả result typed.
- **Phương án đã chọn:** Một LLM tool-calling agent cho mỗi vai trò, protected
  arguments và deterministic domain tool phía sau.
- **Lý do:** Vẫn có quyết định/tool call của agent ở mọi bước nhưng giảm nguy cơ
  hallucination ID, sai số tiền và sai timestamp. Typed handoff cũng làm rõ phân
  vai và cho phép kiểm thử riêng từng domain.
- **Bằng chứng:** Trace ghi model, prompt, tool, arguments, usage và đích handoff
  cho từng agent; fake integration đã tạo 400 agent step cho 50 case và production
  dùng model 8B đúng giới hạn đề.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** Trang chấm báo ZIP không chứa đúng
  `output/EC_001.json` đến `output/EC_050.json`.
- **Bước tái hiện:** Liệt kê archive bằng `unzip -Z1 submission_output.zip`.
- **Nguyên nhân gốc:** ZIP ban đầu chứa JSON ở root archive thay vì giữ prefix
  thư mục `output/`.
- **Cách xử lý:** `scripts/qa_release.py` dùng arcname
  `output/EC_NNN.json`, đồng thời xác minh exact file set sau khi tạo ZIP.
- **Cách xác minh:** Script in `validated=50 zip=submission_output.zip`; hệ thống
  chấm nhận file và trả điểm hợp lệ.
- **Điều học được:** Contract của artifact triển khai cũng quan trọng như schema
  bên trong JSON; QA cần kiểm tra cả path trong archive.

## 7. Hiểu biết về luồng end-to-end

1. Coordinator nhận `CaseInput`, gọi Customer và Order/Product Agent. Sau khi có
   order result, nó gọi Payment và Delivery Agent, rồi handoff tất cả kết quả cho
   Policy Agent.
2. Các domain agent không tự quyết định refund. Chúng chỉ truy xuất hoặc tính các
   fact thuộc domain và trả result typed; Policy Agent mới áp dụng
   `EC_POLICY_V2` theo thứ tự ưu tiên.
3. `claimed_order_id` dùng để join order, customer, item, product, seller và
   payment. Lịch sử dùng `customer_unique_id`; related orders chỉ nằm trong
   customer context, không nằm trong affected entities.
4. Verifier kiểm tra schema, ID, null handling, tiền, array limit và tính nhất
   quán. Output chưa qua Verifier không được ghi file.
5. Output Writer ghi đúng một file cho mỗi case. QA kiểm tra exact 50 file và tạo
   ZIP giữ prefix `output/`; trace và metadata được commit trong repository nhưng
   không được đưa vào ZIP chấm điểm.

## 8. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trần Minh Hiển
**Ngày xác nhận:** 2026-08-05
