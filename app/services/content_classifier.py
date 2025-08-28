import asyncio
import json
import re
from typing import Dict, Optional
from .groq_client import client   # your Groq sync client
import base64

# Model to use on Groq (change if needed)
GROQ_CHAT_MODEL = "llama3-8b-8192"

# A lightweight list of obvious non-food keywords (common nouns). This catches many quick cases.
_NON_FOOD_KEYWORDS = {
    "bus","car","phone","man","woman","person","people","dog","cat","animal","tree","mountain",
    "river","building","house","laptop","keyboard","monitor","shoe","shoes","cupboard","bottle",
    "bicycle","train","plane","chair","table","lamp","camera","watch","clock","phone","truck",
    "truck","fish","bird","horse","cow","sheep","goat","backpack","wallet","bag","purse"
}

def _quick_text_heuristic_is_nonfood(text: str) -> bool:
    """
    Quick heuristic: short single-token common non-food nouns => non-food.
    """
    if not text:
        return True
    t = text.strip().lower()
    # if the user wrote exactly a short token, check keyword list
    if len(t.split()) == 1 and t in _NON_FOOD_KEYWORDS:
        return True
    # if it is very short (<3 chars) and not likely a dish
    if len(t) < 3 and not any(c.isdigit() for c in t):
        return True
    return False

def _call_groq_sync_for_classify(prompt: str, max_tokens: int = 256, temperature: float = 0.0) -> str:
    """
    Synchronous call to Groq chat completions. Run inside asyncio.to_thread from async functions.
    """
    resp = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a strict classifier. Output ONLY JSON with the exact keys requested."},
            {"role": "user", "content": prompt}
        ],
        model=GROQ_CHAT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # robust extraction
    try:
        choice = resp.choices[0]
        msg = getattr(choice, "message", None)
        if msg:
            return getattr(msg, "content", "") or str(resp)
        return str(resp)
    except Exception:
        return str(resp)

async def _call_groq_for_classify(prompt: str) -> str:
    return await asyncio.to_thread(_call_groq_sync_for_classify, prompt)

def _extract_json_object_loose(text: str) -> Dict:
    if not isinstance(text, str):
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    m = re.search(r"(\{.*\})", text, re.S)
    if m:
        try:
            parsed = json.loads(m.group(1))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}

async def classify_text_as_food(text_input: str) -> Dict:
    """
    Returns a dict:
    {
      "action": "accept"|"reject"|"ask_clarify",
      "is_food": bool,
      "dish": str|None,
      "confidence": float,
      "message": str  # user-friendly instruction if rejecting
    }
    """
    # quick heuristic catch
    if _quick_text_heuristic_is_nonfood(text_input):
        return {
            "action": "reject",
            "is_food": False,
            "dish": None,
            "confidence": 0.95,
            "message": "Please enter a dish name (e.g. 'Chicken Biryani') — not a person, object, or place."
        }

    # LLM classifier prompt: explicitly ask to check a wide range of non-food categories
    prompt = f"""
You are a classifier that MUST return ONLY a JSON object with these keys:
- action: one of ["accept", "reject", "ask_clarify"].
- is_food: true/false
- dish: a short dish name (string) if is_food true, otherwise null
- confidence: a number between 0.0 and 1.0
- message: a single short user-facing sentence (if action == "reject" instruct the user to upload or type only a dish name)

Behave conservatively: if input is ambiguous or seems like a person, animal, vehicle, electronic device, building, landscape, or non-food word, return action "reject".
Do NOT hallucinate ingredients here — only classification.

User input: "{text_input}"
Respond only with the JSON object, nothing else.
"""
    raw = await _call_groq_for_classify(prompt)
    parsed = _extract_json_object_loose(raw)
    if not parsed:
        # fallback conservative
        return {
            "action": "reject",
            "is_food": False,
            "dish": None,
            "confidence": 0.0,
            "message": "Input not recognized as a food dish. Please enter a dish name or upload a photo of a dish."
        }
    # normalize
    action = parsed.get("action", "").lower()
    if action not in ("accept", "reject", "ask_clarify"):
        action = "reject" if not parsed.get("is_food") else "accept"
    return {
        "action": action,
        "is_food": bool(parsed.get("is_food") is True or str(parsed.get("is_food")).lower() == "true"),
        "dish": parsed.get("dish"),
        "confidence": float(parsed.get("confidence") or 0.0),
        "message": parsed.get("message") or ("Please upload or enter a dish name.")
    }

async def classify_image_as_food(image_bytes: bytes, hint: Optional[str] = None) -> Dict:
    """
    Similar structured output for images. LLM is asked to detect non-food categories (objects, humans, animals).
    Returns same keys as classify_text_as_food, plus contains_human (bool) and contains_object_examples (list).
    """
    snippet = base64.b64encode(image_bytes)[:1200].decode("utf-8")
    prompt = f"""
        You are a visual classifier. Return ONLY a JSON object with these keys:
        - action: one of ["accept","reject","ask_clarify"]
        - is_food: true/false
        - dish: string|null (a short dish name if is_food true)
        - contains_human: true/false
        - contains_objects: array of short labels describing prominent non-food objects if any (e.g. ["bus","phone","car"])
        - confidence: 0.0-1.0
        - message: short user-facing instruction (if rejecting ask user to upload a food dish)

        Be conservative. If image likely contains a person, animal, vehicle, electronic device, building, or landscape (not a close-up of food), return action "reject". If it's ambiguous, return "ask_clarify". Do not try to invent ingredients here.

        Base64-snippet (truncated): "{snippet}"
        Hint: "{hint or ''}"
        Respond only with the JSON object.
        """
    raw = await _call_groq_for_classify(prompt)
    parsed = _extract_json_object_loose(raw)
    if not parsed:
        return {
            "action": "reject",
            "is_food": False,
            "dish": None,
            "contains_human": False,
            "contains_objects": [],
            "confidence": 0.0,
            "message": "Image could not be classified as a dish. Please upload a clear photo of a dish."
        }
    action = parsed.get("action", "reject").lower()
    if action not in ("accept", "reject", "ask_clarify"):
        action = "reject"
    return {
        "action": action,
        "is_food": bool(parsed.get("is_food") is True or str(parsed.get("is_food")).lower() == "true"),
        "dish": parsed.get("dish"),
        "contains_human": bool(parsed.get("contains_human") is True or str(parsed.get("contains_human")).lower() == "true"),
        "contains_objects": parsed.get("contains_objects") or [],
        "confidence": float(parsed.get("confidence") or 0.0),
        "message": parsed.get("message") or "Please upload a photo of a dish."
    }
