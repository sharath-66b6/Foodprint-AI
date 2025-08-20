from fastapi import FastAPI
from .routes.estimate import router as estimate_router
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Foodprint AI - Carbon Estimator (FastAPI)")

app.include_router(estimate_router, prefix="/estimate")

@app.get("/")
def root():
    return {"status": "ok", "message": "Foodprint AI backend running"}
  