# Running the pipeline

## Cài dependency

```bash
python3 -m pip install -r requirements.txt
```

## Kiểm thử không gọi mạng

```bash
python3 -m unittest discover -v
python3 run.py --fake-llm
```

`--fake-llm` vẫn chạy đủ LLM-agent wrapper, tool và handoff bằng test double,
nhưng không được xem là trace LLM thật để nộp.

## Chạy production

Không commit API key hoặc `.env`:

```bash
export GROQ_API_KEY="gsk_..."
python3 run.py
python3 scripts/qa_release.py
```

Hoặc đặt `GROQ_API_KEY` trong file `.env` ở root. Production mặc định dùng
Groq `llama-3.1-8b-instant` (8B, có native tool calling). Nếu không có
`GROQ_API_KEY`, runtime giữ đường dự phòng Hugging Face bằng
`OPENAI_API_KEY` + `OPENAI_BASE_URL` và model `Qwen/Qwen3-8B`.

Lượt production ghi lại đúng 50 JSON trong `output/`, thay nội dung
`logging/trace.jsonl` bằng lượt mới nhất và cập nhật `logging/metadata.json`.
Script QA tạo `submission_output.zip` chứa đúng 50 JSON dưới prefix `output/`
theo contract của trang chấm (`output/EC_001.json` đến
`output/EC_050.json`).
