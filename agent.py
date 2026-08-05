# file: agents.py
import os
import json
from openai import OpenAI
from tools import extract_order_product_info

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL_NAME = "gpt-4o-mini"

class OrderProductAgent:
    def __init__(self):
        self.name = "OrderProductAgent"
        
        # 1. Định nghĩa mô tả Tool theo chuẩn JSON Schema của OpenAI
        self.tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "extract_order_product_info",
                    "description": "Trích xuất và giới hạn số lượng các thực thể (item_ids, seller_ids, product_ids) từ dữ liệu thô.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {
                                "type": "string",
                                "description": "Mã ID của đơn hàng"
                            },
                            "items_raw": {
                                "type": "array",
                                "description": "Danh sách các sản phẩm",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "item_id": {"type": "integer"},
                                        "seller_id": {"type": "string"},
                                        "product_id": {"type": "string"},
                                        "category": {"type": "string"}
                                    }
                                }
                            }
                        },
                        "required": ["order_id", "items_raw"]
                    }
                }
            }
        ]

    def run(self, order_id: str, items_raw: list):
        system_prompt = """Bạn là OrderProduct Agent. 
        Quy trình của bạn:
        1. Gọi hàm `extract_order_product_info` để xử lý raw data.
        2. Dựa vào kết quả hàm trả về, hãy định dạng chính xác thành JSON sau:
        {
            "affected_entities": {
                "item_ids": ["<order_id>:<order_item_id>"],
                "seller_ids": ["<seller_id>"]
            },
            "product_context": {
                "product_ids": ["<product_id>"],
                "category_names": ["<category_name>"]
            }
        }"""

        # Khởi tạo tin nhắn
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Order ID: {order_id}\nRaw Data: {json.dumps(items_raw, ensure_ascii=False)}"}
        ]

        # BƯỚC 1: LLM PHÂN TÍCH VÀ RA QUYẾT ĐỊNH GỌI TOOL
        response_1 = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=self.tools_schema,
            # Ép LLM luôn phải dùng tool này, không được lười biếng bỏ qua
            tool_choice={"type": "function", "function": {"name": "extract_order_product_info"}}, 
            temperature=0.0
        )

        message_1 = response_1.choices[0].message
        messages.append(message_1) # Lưu vào lịch sử hội thoại

        # BƯỚC 2: PYTHON THỰC THI TOOL TỪ YÊU CẦU CỦA LLM
        if message_1.tool_calls:
            for tool_call in message_1.tool_calls:
                if tool_call.function.name == "extract_order_product_info":
                    # Parse tham số do LLM bóc tách được
                    args = json.loads(tool_call.function.arguments)
                    
                    # Ứng dụng chạy hàm Python
                    tool_result = extract_order_product_info(
                        order_id=args["order_id"],
                        items_raw=args["items_raw"]
                    )
                    
                    # BƯỚC 3: NẠP KẾT QUẢ TOOL VÀO LẠI NGỮ CẢNH
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": json.dumps(tool_result, ensure_ascii=False)
                    })

            # BƯỚC 4: LLM TRẢ LỜI LẦN CUỐI CÙNG (Dựa trên tool_result)
            response_2 = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0
            )
            
            final_json = json.loads(response_2.choices[0].message.content)
            
            trace = {
                "agent": self.name,
                "tool_called": True,
                "tool_arguments_generated": args,
                "tool_execution_result": tool_result
            }
            return final_json, trace
            
        else:
            raise Exception("Pipeline gián đoạn: LLM không kích hoạt Tool Call.")