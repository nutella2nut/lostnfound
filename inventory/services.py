import base64
import json
import logging
from typing import Iterable, Mapping

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def analyze_item_images(files: Iterable) -> Mapping[str, str]:
    """
    Call OpenAI's vision-capable chat model to suggest a title and description
    for a lost-and-found item based on one uploaded image.

    We send the first image as a base64-encoded data URL and ask for strict JSON:

        {"title": "...", "description": "..."}
    """
    api_key = getattr(settings, "OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("OPENAI_API_KEY is not set; skipping vision analysis.")
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

    # Encode as base64 for data URL
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    content_type = getattr(image_file, "content_type", "image/jpeg") or "image/jpeg"
    data_url = f"data:{content_type};base64,{image_b64}"

    endpoint = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_prompt = (
        "You are helping catalog lost-and-found items for a reception desk. "
        "Given an image of an item, respond with STRICT JSON only, with this shape:\n"
        '{ "title": "short, specific title", '
        '"description": "detailed description with brand, color, size, model, visible markings" }.\n'
        "Do not include any explanation outside the JSON."
    )

    body = {
        # You can change this to another vision-capable model available to your account
        "model": "gpt-4.1-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Analyze this lost-and-found item."},
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            },
        ],
        "temperature": 0.4,
    }

    try:
        resp = requests.post(endpoint, headers=headers, json=body, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Extract the model's reply (expected to be JSON text)
        content = data["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content_text = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        else:
            content_text = content

        parsed = json.loads(content_text)
    except Exception:
        logger.exception("Vision API call failed or returned invalid JSON")
        return {}

    title = (parsed.get("title") or "").strip()
    description = (parsed.get("description") or "").strip()
    return {
        "title": title,
        "description": description,
    }



