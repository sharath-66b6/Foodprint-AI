# app/services/ingredient_extractor.py
from typing import List, Dict, Tuple
import json, re, asyncio
from .groq_client import client   # our new groq client

# Choose a Groq model you have access to. Example: "llama3-8b-8192"
GROQ_CHAT_MODEL = "llama3-8b-8192"

def _call_llm_sync(prompt: str, max_tokens: int = 512, temperature: float = 0.2) -> str:
    """
    Synchronous Groq call. We'll run it in a thread from the async extractor
    to avoid blocking the FastAPI event loop.
    """
    # call the chat completions endpoint
    resp = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        model=GROQ_CHAT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # Extract text: documented response shape has .choices[0].message.content
    try:
        choice = resp.choices[0]
        # choice.message is a pydantic model-like object
        message = getattr(choice, "message", None)
        if message is not None:
            # message.content is the string
            return getattr(message, "content", "") or str(resp)
        # fallback to older field
        return getattr(choice, "text", str(resp))
    except Exception:
        # Last fallback: str(resp)
        return str(resp)

def _extract_json_array(text: str) -> List[Dict]:
    if not isinstance(text, str):
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
    except Exception:
        m = re.search(r"(\[.*\])", text, re.S)
        if m:
            try:
                parsed = json.loads(m.group(1))
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
    return []

async def _call_llm(prompt: str) -> str:
    # run the blocking Groq call in a thread to avoid blocking the event loop
    return await asyncio.to_thread(_call_llm_sync, prompt)

# Reuse the same robust extractor code from earlier (with retries)
async def extract_ingredients_from_dish(dish: str, max_retries: int = 2) -> List[Dict]:
    base_prompt = f"""
You are a helpful assistant. Given the dish name below, return ONLY a JSON array (no extra text).
Each array element must be an object with:
  - "name": the ingredient name (string)
  - "percentage": approximate percent of the dish by weight (integer)

Make realistic guesses for a typical preparation of the dish. Ensure percentages sum to about 100.

Example:
[
  {{ "name": "Rice", "percentage": 60 }},
  {{ "name": "Chicken", "percentage": 30 }},
  {{ "name": "Oil", "percentage": 7 }},
  {{ "name": "Spices", "percentage": 3 }}
]

Dish: "{dish}"
Return only the JSON array.
"""

    attempt = 0
    while attempt <= max_retries:
        text = await _call_llm(base_prompt)
        arr = _extract_json_array(text)

        if arr and isinstance(arr, list):
            cleaned = []
            for item in arr:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or item.get("ingredient") or "").strip()
                pct = item.get("percentage") or item.get("pct") or None
                if name:
                    cleaned.append({"name": name, "percentage": pct})
            if len(cleaned) > 1 and not all(c["name"].lower().strip() == dish.lower().strip() for c in cleaned):
                total_pct = sum([p or 0 for p in [c["percentage"] for c in cleaned]])
                if total_pct == 0:
                    eq = int(100 / len(cleaned))
                    for c in cleaned:
                        c["percentage"] = eq
                return cleaned

        attempt += 1
        if attempt <= max_retries:
            clarifying = f"""
Your previous response wasn't a useful ingredient breakdown. Please provide a typical ingredient breakdown for the dish "{dish}".
Return ONLY a JSON array of objects: {{ "name": "<ingredient>", "percentage": <int> }}.
List common ingredients (4-8 items) and ensure percentages sum to ~100.
Do not return the dish name as an ingredient.
"""
            await asyncio.sleep(0.4 * attempt)
            base_prompt = clarifying
            continue

        return [{"name": dish, "percentage": 100}]

def _extract_json_object(text: str) -> Dict:
    """
    Try parsing the LLM output as a JSON object. Be lenient:
    - If the LLM prints extra text, extract the first {...} block.
    """
    if not isinstance(text, str):
        return {}
    # direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # fallback: extract first {...} block (non-greedy)
    m = re.search(r"(\{.*\})", text, re.S)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}

async def extract_ingredients_from_image(image_bytes: bytes, hint: str = None) -> Tuple[List[Dict], str]:
    """
    New behavior:
      - Ask the model to return a JSON OBJECT:
        {
          "dish": "<inferred dish name>",
          "ingredients": [
            {"name": "Rice", "percentage": 60},
            {"name": "Chicken", "percentage": 30}
          ]
        }
      - Return (ingredients_list, dish_name)
    """
    import base64
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    snippet = b64[:1200]  # truncate for prompt safety

    prompt = f"""
You are a helpful visual assistant. The user provided an image (base64 snippet below) and an optional hint.
Return ONLY a JSON OBJECT with two keys:
  - "dish": the most likely dish name (string). If unsure, return a short description like "rice bowl" or "mixed salad".
  - "ingredients": an array of ingredient objects, each {{ "name": "<ingredient>", "percentage": <int> }}.
Aim for 4-8 ingredients and ensure percentages sum to about 100.

Example output:
{{
  "dish": "Chicken Biryani",
  "ingredients": [
    {{ "name": "Rice", "percentage": 60 }},
    {{ "name": "Chicken", "percentage": 30 }},
    {{ "name": "Oil", "percentage": 7 }},
    {{ "name": "Spices", "percentage": 3 }}
  ]
}}

Base64-snippet: "{snippet}"
Hint (if provided): "{hint or ''}"
Respond with only the JSON object, and nothing else.
"""
    # call your blocking LLM wrapper in a thread (keeps FastAPI's loop responsive)
    text = await asyncio.to_thread(_call_llm_sync, prompt)  # or await _call_llm(prompt) if you have async wrapper

    # Try parsing a JSON object
    parsed = _extract_json_object(text)

    # If parsed object is empty, attempt a softer fallback: try to extract an ingredients array and use hint/filename for dish
    if not parsed:
        # Try to find an ingredients array in the raw text (old fallback behaviour)
        arr = _extract_json_array(text)  # if you have this util in the file
        if arr:
            # set dish to hint if provided, else unknown
            dish_name = hint or "unknown dish"
            # ensure percentages exist
            cleaned = []
            total_pct = 0
            for item in arr:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name") or item.get("ingredient") or "").strip()
                pct = item.get("percentage") or item.get("pct") or None
                if name:
                    cleaned.append({"name": name, "percentage": pct})
                    total_pct += pct or 0
            if total_pct == 0 and len(cleaned) > 0:
                eq = int(100 / len(cleaned))
                for c in cleaned:
                    c["percentage"] = eq
            return cleaned, dish_name
        # ultimate fallback
        return [{"name": hint or "unknown", "percentage": 100}], (hint or "unknown")

    # parsed is a dict; extract dish and ingredients robustly
    dish_name = parsed.get("dish") or parsed.get("title") or parsed.get("name") or ""
    ingredients = parsed.get("ingredients") or parsed.get("ingredient_list") or []

    # Normalize the ingredient entries
    cleaned = []
    for item in ingredients:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or item.get("ingredient") or "").strip()
        pct = item.get("percentage") or item.get("pct") or None
        if name:
            cleaned.append({"name": name, "percentage": pct})

    # If model forgot percentages, fill evenly
    if cleaned:
        total_pct = sum([p or 0 for p in [c["percentage"] for c in cleaned]])
        if total_pct == 0:
            eq = int(100 / len(cleaned))
            for c in cleaned:
                c["percentage"] = eq

    # If dish name empty, fall back to hint or a short descriptor
    if not dish_name or not isinstance(dish_name, str) or dish_name.strip() == "":
        dish_name = hint or "inferred-dish"

    return cleaned, dish_name