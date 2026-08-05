# Member Role Report — Day 9: Multi Agent A2A

> Mỗi thành viên trong nhóm tự hoàn thành mẫu này để báo cáo đúng vai trò, phần việc và mức hiểu của mình. Không sao chép nguyên báo cáo chung hoặc báo cáo của thành viên khác. Thay nội dung trong dấu `[ ]` và xóa các dòng hướng dẫn không cần thiết trước khi nộp.

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

| Module/deliverable                | File/hàm phụ trách                         | Input nhận vào                              | Output bàn giao                                              | Trạng thái  |
| --------------------------------- | ------------------------------------------ | ------------------------------------------- | ------------------------------------------------------------ | ---------- |
| Agent orchestration + tool schema | [src/agents/llm_agents.py](C:/Users/toant/Desktop/K4-Day9-Multi-Agent-A2A/src/agents/llm_agents.py) + [src/order_product_agent.py](C:/Users/toant/Desktop/K4-Day9-Multi-Agent-A2A/src/order_product_agent.py) | CaseInput (includes case_id, investigation_scope) | LLMOrderProductAgent.invoke -> OlistOrderProductAgent.investigate(case) trả về OrderProductResult (item_ids, seller_ids, product_ids, category_names, item_total_brl, freight_total_brl) | Hoàn thành |
| Deterministic order/product logic | [src/order_product_agent.py](C:/Users/toant/Desktop/K4-Day9-Multi-Agent-A2A/src/order_product_agent.py)   | CaseInput (case + claimed_order_id)      | OlistOrderProductAgent.investigate trả về OrderProductResult (see schemas) — deduped lists, item/product/category lists, and BRL totals rounded to 2 decimals | Hoàn thành |

Chỉ nhận ownership cho phần trực tiếp triển khai: định nghĩa schema tool (JSON Schema), thực thi tool ở Python, và orchestration hội thoại LLM → tool → LLM.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động                 | Thành viên/module được hỗ trợ | Kết quả                 |
| ------------------------- | ----------------------------- | ----------------------- |
| Tích hợp & test local     | Toàn bộ pipeline LLM–Tool   | Đã cung cấp snippet kiểm thử (xem phần 4)      |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện                                | File/hàm/artifact liên quan                                                                 | Kết quả bàn giao                                                                                 | Cách xác minh                                                                 |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| Định nghĩa Tool schema và orchestration cuộc hội thoại | [agents.py](C:/Users/toant/Desktop/K4-Day9-Multi-Agent-A2A/agents.py)                       | OrderProductAgent.run(order_id, items_raw) trả về final_json và trace                        | Chạy script kiểm thử Python (ví dụ bên dưới) và kiểm tra cấu trúc JSON trả về  |
| Triển khai hàm trích xuất entities                   | [tools.py](C:/Users/toant/Desktop/K4-Day9-Multi-Agent-A2A/tools.py)                         | extract_order_product_info trả về dict với giới hạn seller_ids (max 3) và product_ids (max 5) | Chạy trực tiếp hàm với dữ liệu mẫu và so sánh output với mong đợi              |

Nêu một output cụ thể mà phần việc của bạn tạo ra hoặc giúp xác minh:

- Artifact: JSON object theo định dạng cuối cùng (final_json) do agent trả về. Ví dụ mẫu:

{
  "order_id": "ord123",
  "order_status": "delivered",
  "affected_entities": {
    "item_ids": ["ord123:1", "ord123:2"],
    "seller_ids": ["sellerA", "sellerB"]
  },
  "product_context": {
    "product_ids": ["prod1", "prod2"],
    "category_names": ["electronics"]
  },
  "item_total_brl": 123.45,
  "freight_total_brl": 10.0
}

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

- Xây dựng một agent orchestration pattern: cho phép LLM quyết định gọi một Python tool (Function Calling-style), thực thi tool ở runtime, nạp kết quả trở lại ngữ cảnh và để LLM trả về một JSON tiêu chuẩn cuối cùng. Mục tiêu: tách rõ phần logic xử lý dữ liệu (deterministic Python) và reasoning (LLM).

### Cách triển khai

- agents.py (OrderProductAgent):
  - Định nghĩa một tool descriptor theo chuẩn JSON Schema để LLM biết cách tạo tool call.
  - Gửi tin nhắn system + user tới model, yêu cầu model phải gọi tool extract_order_product_info (tắt lựa chọn bỏ qua bằng tool_choice).
  - Khi nhận tool_call từ LLM, parse arguments (JSON), gọi hàm Python thực tế (tools.extract_order_product_info), rồi nạp role="tool" message chứa kết quả vào lịch sử cuộc hội thoại.
  - Gọi model lần tiếp theo để nhận final_json (được yêu cầu trả về dạng JSON object bằng response_format).
  - Trả về final_json và một trace object để tiện debug/kiểm tra.

- src/order_product_agent.py (OlistOrderProductAgent):
  - Lấy order, items và (tuỳ chọn) product context từ repository theo case.customer_request.claimed_order_id.
  - Tạo item_ids theo format "{order_id}:{order_item_id}".
  - Dedupe seller_ids, product_ids và category_names bằng _stable_unique (preserve order).
  - Nếu investigation_scope.include_product_context=True, gọi repository.get_product(product_id) để thu category names; nếu False, product_ids được trả về rỗng.
  - Tính item_total và freight_total bằng Decimal và convert về float BRL với làm tròn 2 chữ số bằng _brl().
  - Trả về OrderProductResult (typed dataclass). Lưu ý: giới hạn số phần tử (truncate) được áp dụng khi assemble final CaseOutput trong coordinator, không ở bước agent.

### Input, output và contract

| Thành phần              | Mô tả                                                                 |
| ----------------------- | --------------------------------------------------------------------- |
| Input                   | CaseInput (see src/schemas.py): case_id, customer_request.claimed_order_id, investigation_scope.include_product_context, policy_version |
| Output                  | OrderProductResult (src/schemas.py): order_id, order_status, item_ids, seller_ids, product_ids, category_names, item_total_brl, freight_total_brl |
| Module phụ thuộc        | OrderProductRepository protocol + src/order_product_agent.py (deterministic lookup/aggregation) |
| Module sử dụng output   | src/coordinator.py assembles CaseOutput from agent results and enforces final size limits (item_ids[:5], seller_ids[:3], product_ids[:5], category_names[:5]) |
| Điều kiện lỗi cần xử lý | - Không tìm thấy order -> raise ContractError (handled in investigate)
|                         | - Không có items -> agent trả OrderProductResult với chỉ order_id/order_status (no item rows)
|                         | - CaseInput invalid -> schemas.validate() raises ContractError

### Cách xác minh

Kiểm thử / xác minh (quick):

- Unit tests: chạy test suite có sẵn để kiểm tra toàn bộ pipeline (LLM tool-calling + deterministic tools):

```bash
# chạy tất cả tests trong thư mục tests
python -m unittest discover -s tests -p "test_*.py"
```

- Kiểm thử nhanh hàm deterministic (direct):

```python
from src.order_product_agent import OlistOrderProductAgent

# Thay repository bằng stub/fixture phù hợp (repo phải implement get_order, get_items_by_order, get_product)
# Sử dụng test stubs ở tests/stubs.py để dễ chạy trong local test suite.

# Example (conceptual):
# repo = YourStubRepository()
# agent = OlistOrderProductAgent(repo)
# case = CaseInput.from_dict({...})
# result = agent.investigate(case)
# assert "ord123:1" in result.item_ids
```

- Để kiểm tra end-to-end, chạy test AgenticPipelineTests trong tests/test_llm_agents.py (mocks fake-llm are used there).

## 5. Một quyết định kỹ thuật quan trọng

- Bối cảnh: Làm sao đảm bảo LLM thực thi tool deterministic (Python) thay vì 'bịa' kết quả nội suy?
- Các phương án đã cân nhắc:
  1) Tin tưởng model và parse trực tiếp output do model tạo (không gọi tool thực sự).  
  2) Bắt buộc model gọi một tool descriptor và thực thi hàm Python để có kết quả chính xác, sau đó nạp lại vào ngữ cảnh.
- Phương án đã chọn: Phương án 2 — thiết kế Function-Calling-like descriptor và ép model gọi tool bằng tool_choice, sau đó thực thi Python tool.
- Lý do: Độ tin cậy và reproducibility cao hơn — phần trích xuất, dedupe và giới hạn kích thước được thực hiện bằng code có thể kiểm tra, test và debug; tránh model hallucination về các entity.
- Bằng chứng: trace chứa tool_execution_result, dễ kiểm tra và so sánh với final_json; unit test cho tools.extract_order_product_info có thể xác nhận các ranh giới (max 3/5).

## 6. Một lỗi hoặc blocker đã xử lý

- Triệu chứng/lỗi nguyên văn: "Pipeline gián đoạn: LLM không kích hoạt Tool Call." (raised Exception trong code nếu message_1.tool_calls rỗng)
- Lệnh hoặc bước tái hiện: Gọi agent.run(order_id, items_raw) mà model trả lời dạng text mà không tạo tool_call.
- Nguyên nhân gốc: Model có thể không chọn gọi function/tool nếu prompt không bắt buộc hoặc nếu temperature cao dẫn tới quyết định khác. Ngoài ra, nếu tools_schema không đúng format, model sẽ không produce tool_call.
- Cách xử lý:
  - Thêm `tool_choice` trong request để ép LLM phải gọi function cụ thể.
  - Giữ temperature=0.0 để có hành vi quyết định determinisitc từ model.
  - Bắt lỗi rõ ràng và raise Exception nếu tool_call không xuất hiện để không silent-fail pipeline.
- Cách xác minh sau khi sửa: Chạy lại agent.run với dữ liệu mẫu và kiểm tra rằng response_1.choices[0].message.tool_calls tồn tại; trace.tool_called == True.
- Điều học được: Khi phối hợp LLM và code, cần có cơ chế bắt buộc hoặc fallback rõ ràng để tránh mất mạch pipeline do model behaviour.

Nếu chưa xử lý xong: (n/a — đã áp dụng tool_choice và exception handling)

## 7. Hiểu biết về luồng end-to-end

1. Dữ liệu đi từ Crossref đến vector index như thế nào?
   - Trong bài lab chung: raw documents (ví dụ Crossref metadata) được thu thập, tiền xử lý (normalize, extract fields), rồi chuyển sang bước embedding (vectorization). Sau đó vectors được lưu vào một vector index (ví dụ FAISS, Milvus, Pinecone). Ở repo hiện tại, extract_order_product_info là bước tiền xử lý/normalized entity trước khi tạo context metadata cho embedding.

2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?
   - Evaluation set chứa các truy vấn đã biết và map tới ground-truth document IDs (tài liệu đúng). Khi chạy retrieval, so sánh top-K results với ground-truth IDs để tính metrics như recall@K, precision@K, MRR.

3. Quality checks khác freshness monitoring ở điểm nào trong bài lab?
   - Freshness monitoring kiểm tra xem index được cập nhật/refresh với dữ liệu mới gần đây hay không (thời gian). Quality checks còn bao gồm deduplication, completeness, schema validation, và đếm anomalies (missing fields, malformed records) — những thứ ảnh hưởng trực tiếp tới chất lượng embedding và retrieval.

4. Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?
   - Để đảm bảo so sánh công bằng: dùng cùng queries và same ground-truth đánh giá liệu repair có thực sự cải thiện metrics so với baseline và corrupted. Nếu test set khác nhau, thay đổi metric có thể do khác biệt dữ liệu chứ không phải do phương pháp.

5. Repair được xem là thành công dựa trên artifact và metric nào?
   - Artifact: repaired documents / repaired metadata / corrected entity lists và updated index snapshots.
   - Metric: tăng Recall@K, MRR, hoặc giảm error rate trong downstream QA. Thành công khi metrics trên test set cho thấy cải thiện có ý nghĩa so với corrupted baseline, đồng thời không làm giảm quá nhiều các metric khác.

**Câu trả lời:**

Phần code mình viết đảm nhận bước tiền xử lý entity (extract_order_product_info) và orchestration LLM→tool→LLM. Dữ liệu order/items được chuẩn hóa thành entity lists (item_ids, seller_ids, product_ids) và được giới hạn kích thước để không quá tải ngữ cảnh model hoặc downstream pipeline.

## 8. Cam kết của thành viên

Đánh dấu sau khi tự kiểm tra:

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Tôi không ghi “đã chạy thành công” cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Tran Van Toan
**Ngày xác nhận:** 2026-08-05
