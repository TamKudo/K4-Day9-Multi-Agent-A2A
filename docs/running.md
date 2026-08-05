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
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="<OpenAI-compatible endpoint serving Qwen/Qwen3-8B>"
python3 run.py
python3 scripts/qa_release.py
```

Lượt production ghi lại đúng 50 JSON trong `output/`, thay nội dung
`logging/trace.jsonl` bằng lượt mới nhất và cập nhật `logging/metadata.json`.
Script QA tạo `submission_output.zip` chứa đúng 50 JSON ở root của ZIP.
