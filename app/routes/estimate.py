from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Any
from ..services.ingredient_extractor import extract_ingredients_from_dish, extract_ingredients_from_image
from ..utils.carbon import estimate_carbon
from ..services.content_classifier import classify_text_as_food, classify_image_as_food
from ..services.food_recognizer import predict_food
import io

router = APIRouter()

class DishRequest(BaseModel):
    dish: str

@router.post("/", response_model=Any)
async def estimate_from_dish(payload: DishRequest):
    dish = payload.dish.strip()
    if not dish:
        raise HTTPException(status_code=400, detail="dish is required")

    # CLASSIFY text first
    classification = await classify_text_as_food(dish)
    if classification["action"] == "reject":
        # instructive 400 response pointing user to upload/write dish only
        raise HTTPException(status_code=400, detail=classification["message"])
    if classification["action"] == "ask_clarify":
        raise HTTPException(status_code=400, detail="Please provide a clear dish name (e.g., 'Chicken Biryani').")

    try:
        # proceed using classifier's dish suggestion if available
        dish_hint = classification["dish"] or dish
        ingredients = await extract_ingredients_from_dish(dish_hint)
        ing_with_carbon, total = estimate_carbon(ingredients)
        return JSONResponse({
            "dish": dish_hint,
            "estimated_carbon_kg": total,
            "ingredients": ing_with_carbon
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/image", response_model=Any)
async def estimate_from_image(image: UploadFile = File(...), hint: Optional[str] = Form(None)):
    contents = await image.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty image upload")

    try:
        # Prefer hint if given
        dish_name = predict_food(contents)  # returns None if not confident
        if not dish_name:
            dish_name = hint

        if not dish_name:
            raise HTTPException(
                status_code=400,
                detail="Image does not appear to be food. Please upload a dish photo or provide a hint."
            )

        ingredients = await extract_ingredients_from_dish(dish_name)
        ing_with_carbon, total = estimate_carbon(ingredients)

        return JSONResponse({
            "dish": dish_name,
            "estimated_carbon_kg": total,
            "ingredients": ing_with_carbon
        })

    except HTTPException as e:
        # Let our custom messages pass through
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

