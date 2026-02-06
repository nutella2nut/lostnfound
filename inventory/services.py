import base64
import json
import logging
from typing import Iterable, Mapping

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def analyze_item_images(files: Iterable) -> Mapping[str, str]:
    """
    Call Google Gemini Vision API to suggest a title and description
    for a lost-and-found item based on one uploaded image.
    """
    # Use Google Gemini API key
    api_key = getattr(settings, "GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning("GOOGLE_API_KEY is not set; skipping vision analysis.")
        return {}

    files = list(files or [])
    if not files:
        return {}

    # Use only the first image for now
    image_file = files[0]

    try:
        # Read file bytes
        image_file.seek(0)
        image_bytes = image_file.read()
        image_file.seek(0)
    except Exception:
        logger.exception("Failed to read image file for vision analysis")
        return {}

    # Encode as base64 for Gemini API
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    content_type = getattr(image_file, "content_type", "image/jpeg") or "image/jpeg"

    # Gemini API endpoint - using gemini-2.5-flash (available model from your API)
    model_name = "gemini-2.5-flash"
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    prompt = (
        "You are helping catalog lost-and-found items for a reception desk. "
        "Given an image of an item, respond with JSON only, with this exact shape:\n"
        '{ "title": "short, specific title", '
        '"description": "detailed description with brand, color, size, model, visible markings", '
        '"category": "one of: Electronics, Bags and Carry, Clothing and wearables, '
        'bottles and containers, Documents and Id\\\"s, Notebooks/books, Other/Misc" }.\n'
        "Do not include any explanation or text outside the JSON. Return only valid JSON."
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": content_type,
                            "data": image_b64,
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "response_mime_type": "application/json",
        },
    }

    try:
        resp = requests.post(endpoint, json=body, timeout=30)
        if resp.status_code != 200:
            # If model not found, try to list available models for debugging
            if resp.status_code == 404:
                try:
                    list_models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                    models_resp = requests.get(list_models_url, timeout=10)
                    if models_resp.status_code == 200:
                        models_data = models_resp.json()
                        available_models = [m.get("name", "") for m in models_data.get("models", [])]
                        logger.warning(
                            "Model %s not found. Available models: %s",
                            model_name,
                            ", ".join(available_models[:10]),  # Show first 10
                        )
                except Exception:
                    pass  # Ignore errors when listing models
            
            logger.error(
                "Gemini Vision API HTTP error %s: %s",
                resp.status_code,
                resp.text[:500],
            )
            return {}

        data = resp.json()
        # Gemini returns content in candidates[0].content.parts[0].text
        content_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(content_text)
    except Exception:
        logger.exception("Gemini Vision API call failed or returned invalid JSON")
        return {}

    title = (parsed.get("title") or "").strip()
    description = (parsed.get("description") or "").strip()
    category_raw = (parsed.get("category") or "").strip()

    def normalize_category(value: str) -> str:
        v = value.lower()
        if "electronic" in v or "laptop" in v or "phone" in v or "tablet" in v or "charger" in v:
            return "ELECTRONICS"
        if "bag" in v or "backpack" in v or "carry" in v or "luggage" in v:
            return "BAGS_AND_CARRY"
        if "cloth" in v or "shirt" in v or "pants" in v or "jacket" in v or "shoe" in v or "wearable" in v:
            return "CLOTHING_AND_WEARABLES"
        if "bottle" in v or "flask" in v or "container" in v or "tupperware" in v:
            return "BOTTLES_AND_CONTAINERS"
        if "document" in v or "id" in v or "passport" in v or "license" in v or "card" in v:
            return "DOCUMENTS_AND_IDS"
        if "notebook" in v or "book" in v or "diary" in v:
            return "NOTEBOOKS_AND_BOOKS"
        return "OTHER_MISC"

    category = normalize_category(category_raw)

    if not title and not description:
        logger.warning("Gemini Vision API returned empty title/description/category: %s", parsed)

    return {
        "title": title,
        "description": description,
        "category": category,
    }


# ============================================================================
# OPENAI IMPLEMENTATION (COMMENTED OUT - FOR REFERENCE)
# ============================================================================
# def analyze_item_images_openai(files: Iterable) -> Mapping[str, str]:
#     """
#     Call OpenAI's vision-capable chat model to suggest a title and description
#     for a lost-and-found item based on one uploaded image.
#     """
#     api_key = getattr(settings, "OPENAI_API_KEY", "")
#     if not api_key:
#         logger.warning("OPENAI_API_KEY is not set; skipping vision analysis.")
#         return {}
#
#     files = list(files or [])
#     if not files:
#         return {}
#
#     # Use only the first image for now
#     image_file = files[0]
#
#     try:
#         # Read file bytes
#         image_file.seek(0)
#         image_bytes = image_file.read()
#         image_file.seek(0)
#     except Exception:
#         logger.exception("Failed to read image file for vision analysis")
#         return {}
#
#     # Encode as base64 for data URL
#     image_b64 = base64.b64encode(image_bytes).decode("utf-8")
#     content_type = getattr(image_file, "content_type", "image/jpeg") or "image/jpeg"
#     data_url = f"data:{content_type};base64,{image_b64}"
#
#     endpoint = "https://api.openai.com/v1/chat/completions"
#     headers = {
#         "Authorization": f"Bearer {api_key}",
#         "Content-Type": "application/json",
#     }
#
#     system_prompt = (
#         "You are helping catalog lost-and-found items for a reception desk. "
#         "Given an image of an item, respond with JSON only, with this shape:\n"
#         '{ "title": "short, specific title", '
#         '"description": "detailed description with brand, color, size, model, visible markings" }.\n'
#         "Do not include anything outside the JSON."
#     )
#
#     body = {
#         "model": "gpt-4.1-mini",  # vision-capable model
#         "messages": [
#             {"role": "system", "content": system_prompt},
#             {
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": "Analyze this lost-and-found item."},
#                     {
#                         "type": "image_url",
#                         "image_url": {"url": data_url},
#                     },
#                 ],
#             },
#         ],
#         # Force the model to return a JSON object
#         "response_format": {"type": "json_object"},
#         "temperature": 0.4,
#     }
#
#     try:
#         resp = requests.post(endpoint, headers=headers, json=body, timeout=30)
#         if resp.status_code != 200:
#             logger.error(
#                 "Vision API HTTP error %s: %s",
#                 resp.status_code,
#                 resp.text[:500],
#             )
#             return {}
#
#         data = resp.json()
#         content_text = data["choices"][0]["message"]["content"]
#         parsed = json.loads(content_text)
#     except Exception:
#         logger.exception("Vision API call failed or returned invalid JSON")
#         return {}
#
#     title = (parsed.get("title") or "").strip()
#     description = (parsed.get("description") or "").strip()
#
#     if not title and not description:
#         logger.warning("Vision API returned empty title/description: %s", parsed)
#
#     return {
#         "title": title,
#         "description": description,
#     }



