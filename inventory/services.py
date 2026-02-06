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
    for a lost-and-found item based on uploaded images.
    Analyzes ALL provided images to get a comprehensive understanding of the item.
    """
    # Use Google Gemini API key
    api_key = getattr(settings, "GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning("GOOGLE_API_KEY is not set; skipping vision analysis.")
        return {}

    files = list(files or [])
    if not files:
        return {}

    # Process ALL images, not just the first one
    image_parts = []
    for image_file in files:
        try:
            # Read file bytes
            image_file.seek(0)
            image_bytes = image_file.read()
            image_file.seek(0)
        except Exception:
            logger.exception("Failed to read image file for vision analysis")
            continue

        # Encode as base64 for Gemini API
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        content_type = getattr(image_file, "content_type", "image/jpeg") or "image/jpeg"
        
        image_parts.append({
            "inline_data": {
                "mime_type": content_type,
                "data": image_b64,
            }
        })
    
    if not image_parts:
        logger.warning("No valid images to analyze")
        return {}

    # Gemini API endpoint - using gemini-2.5-flash (available model from your API)
    model_name = "gemini-2.5-flash"
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    # Update prompt to mention multiple images
    image_count_text = f"{len(image_parts)} image" if len(image_parts) == 1 else f"{len(image_parts)} images"
    prompt = (
        f"You are helping catalog lost-and-found items for a reception desk. "
        f"Given {image_count_text} of the same item from different angles/views, analyze ALL images comprehensively "
        f"to provide the most accurate identification. Consider all visible details across all images. "
        f"Respond with JSON only, with this exact shape:\n"
        '{ "title": "short, specific title", '
        '"description": "detailed description (format varies by category - see rules below)", '
        '"category": "one of: Electronics, Bags and Carry, Sports and clothing, '
        'Bottles and containers, Documents and Id\\"s, Notebooks/books, Other/Misc" }.\n\n'
        "IMPORTANT: Analyze ALL images together. If different images show different aspects (e.g., one shows a case, another shows the device screen), "
        "use the most identifying features from ALL images to determine what the item actually is. "
        "Do not be biased toward the first image - consider all images equally.\n\n"
        "DESCRIPTION FORMATTING RULES BY CATEGORY:\n\n"
        "1. NOTEBOOKS/BOOKS: "
        "If it's a TISB notebook (identified by 'the international school bangalore' on cover), "
        "description should ONLY include: color of the book, name written on it, class and section, and subject name. "
        "No other details. "
        "For other books/notebooks: emphasize any labels first, then describe patterns and design.\n\n"
        "2. ELECTRONICS: "
        "Identify the device type, then brand name. If brand is not visible, describe key features. "
        "Title should be: [Brand] [Device Type] [Color] [Model if visible]. "
        "Description should emphasize brand name and model if found, then describe design, patterns, and physical features.\n\n"
        "3. BAGS AND CARRY: "
        "Title should be: [Color] [Brand if visible] [Type of bag]. "
        "Description should mention features like keychains, tears, zippers, pockets, and other distinguishing characteristics.\n\n"
        "4. BOTTLES AND CONTAINERS: "
        "Title should be: [Brand if visible] [Bottle or Box] [Color]. "
        "Description should focus on physical features like dents, scratches, stickers, and other visible characteristics.\n\n"
        "5. OTHER/MISC: "
        "Describe as usual with relevant details.\n\n"
        "6. ALL OTHER CATEGORIES: "
        "Describe as usual but avoid unnecessary trivial details (e.g., don't mention specific button colors unless relevant). "
        "Focus on useful identifying information.\n\n"
        "Do not include any explanation or text outside the JSON. Return only valid JSON."
    )

    # Build parts array with prompt followed by all images
    parts = [{"text": prompt}] + image_parts

    body = {
        "contents": [
            {
                "parts": parts
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
        if "cloth" in v or "shirt" in v or "pants" in v or "jacket" in v or "shoe" in v or "wearable" in v or "sport" in v:
            return "SPORTS_AND_CLOTHING"
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



