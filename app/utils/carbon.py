# app/utils/carbon.py
from typing import List, Dict, Tuple
import os

EMISSIONS_PER_KG = {
    "beef": 27.0,
    "lamb": 39.2,
    "pork": 12.1,
    "chicken": 6.9,
    "rice": 4.0,
    "potato": 0.3,
    "tofu": 2.0,
    "vegetable": 0.5,
    "vegetables": 0.5,
    "oil": 6.0,
    "spices": 1.5,
    "cheese": 13.5,
    "milk": 3.2,
    "default": 2.5
}

DEFAULT_DISH_WEIGHT_KG = float(os.getenv("DEFAULT_DISH_WEIGHT_KG", 0.6))
# note: increasing default weight slightly can raise totals; tweak if you want higher/lower footprints.

def _find_emission_key(name: str) -> str:
    key = name.lower()
    if key in EMISSIONS_PER_KG:
        return key
    for k in EMISSIONS_PER_KG.keys():
        if k in key:
            return k
    return "default"

def estimate_carbon(ingredients: List[Dict]) -> Tuple[List[Dict], float]:
    """
    Input: list of {"name": str, "percentage": int/float (optional)}
    Output: (ingredients_with_carbon, total_carbon)
    ingredients_with_carbon: each is {"name": str, "carbon_kg": float}
    """
    n = len(ingredients)
    # Normalize percentages
    total_pct = 0
    normalized = []
    for ing in ingredients:
        p = ing.get("percentage")
        try:
            p = float(p) if p is not None else None
        except Exception:
            p = None
        normalized.append(p)
        if p:
            total_pct += p

    if total_pct == 0:
        normalized = [100.0 / n] * n
    else:
        # scale to 100 if not already
        factor = 100.0 / total_pct
        normalized = [ (p or 0) * factor for p in normalized ]

    result = []
    total_carbon = 0.0
    for ing, pct in zip(ingredients, normalized):
        name = ing.get("name", "unknown")
        key = _find_emission_key(name)
        emission_per_kg = EMISSIONS_PER_KG.get(key, EMISSIONS_PER_KG["default"])
        weight_kg = (pct / 100.0) * DEFAULT_DISH_WEIGHT_KG
        carbon = round(emission_per_kg * weight_kg, 3)
        total_carbon += carbon
        result.append({"name": name, "carbon_kg": carbon})
    total_carbon = round(total_carbon, 3)
    return result, total_carbon
