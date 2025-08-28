from transformers import pipeline
from PIL import Image
import io

classifier = pipeline("image-classification", model="nateraw/food")

def predict_food(image_bytes: bytes, threshold: float = 0.7):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    preds = classifier(image)
    best = max(preds, key=lambda x: x["score"])
    if best["score"] < threshold:
        return None  # Not confident → reject
    return best["label"]
