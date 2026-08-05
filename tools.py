# file: tools.py

def extract_order_product_info(order_id: str, items_raw: list) -> dict:
    """
    Tool trích xuất thông tin thực thể và sản phẩm.
    Được LLM gọi thông qua Function Calling.
    """
    item_ids = []
    seller_ids = set()
    product_ids = set()
    category_names = set()

    for item in items_raw:
        item_ids.append(f"{order_id}:{item['item_id']}")
        seller_ids.add(item['seller_id'])
        product_ids.add(item['product_id'])
        
        if item.get('category'):
            category_names.add(str(item['category']))

    # Tuân thủ chặt chẽ rule từ hệ thống (trả về trực tiếp cho LLM)
    return {
        "affected_entities": {
            "item_ids": item_ids,
            "seller_ids": list(seller_ids)[:3]  # Max 3
        },
        "product_context": {
            "product_ids": list(product_ids)[:5], # Max 5
            "category_names": list(category_names)[:5] # Max 5
        }
    }