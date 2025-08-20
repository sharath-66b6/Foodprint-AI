# Foodprint AI — Backend

A backend prototype implementing two endpoints:

* **POST `/estimate`** — Accepts a dish name (JSON) and returns estimated carbon footprint plus ingredient breakdown.
* **POST `/estimate/image`** — Accepts an image upload **and requires a hint (dish name / context)**, returning the same carbon footprint estimation.

This is a pragmatic prototype: the LLM/Groq API is used to extract ingredient lists, and mocked carbon values are used to estimate emissions. Intended for a take-home assignment, **not production**.

---

## 🚀 Tech stack

* Python 3.11
* FastAPI
* Groq API (LLM & Vision)
* Pydantic
* Uvicorn

---

## ⚙️ Setup (local)

1. Clone:

```bash
git clone <your-repo>
cd Foodprint-AI
```

2. Create `.env` from example and set your GROQ\_API\_KEY:

```bash
cp .env.example .env
# edit .env -> set GROQ_API_KEY
```

3. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

4. Run server:

```bash
uvicorn app.main:app --reload --port 8000
```

API runs at: [http://localhost:8000](http://localhost:8000)

---

## 📌 Example requests

### 1) Dish name

**Request:**

```http
POST /estimate
Content-Type: application/json

{"dish": "Chicken Biryani"}
```

**Response:**

```json
{
  "dish": "Chicken Biryani",
  "estimated_carbon_kg": 4.2,
  "ingredients": [
    {"name": "Rice", "carbon_kg": 1.1},
    {"name": "Chicken", "carbon_kg": 2.5},
    {"name": "Spices", "carbon_kg": 0.2},
    {"name": "Oil", "carbon_kg": 0.4}
  ]
}
```

---

### 2) Image upload (⚠️ requires hint)

```bash
curl -X POST "http://localhost:8000/estimate/image" \
  -F "image=@/path/to/plate.jpg" \
  -F "hint=Chicken Biryani"
```

**Response:**

```json
{
  "dish": "Chicken Biryani",
  "estimated_carbon_kg": 4.2,
  "ingredients": [
    {"name": "Rice", "carbon_kg": 1.1},
    {"name": "Chicken", "carbon_kg": 2.5},
    {"name": "Spices", "carbon_kg": 0.2},
    {"name": "Oil", "carbon_kg": 0.4}
  ]
}
```

❌ If you try funky inputs like `bus`, `phone`, `man`, or upload non-food images without a food `hint`, you’ll get:

```json
{
  "detail": "Please provide a valid dish name or food image with hint"
}
```

---

## ⚖️ Assumptions & Limitations

* Ingredient extraction is LLM-driven; results may vary.
* Carbon values are **mocked** using a lookup table; in production this should be replaced with authoritative LCA datasets.
* The `/estimate/image` endpoint requires a **hint** to avoid non-food inputs.
* This project does **not** include authentication or rate limiting (prototype only).

---

## 🧑‍💻 Design decisions & reasoning

* **FastAPI** chosen for typing, async support, and auto Swagger docs.
* **LLM + Groq API** chosen for ingredient extraction → flexible with messy dish names.
* **Validation** step for funky inputs — ensures non-food inputs like “bus” or “man” do not produce meaningless carbon estimates.
* **Hint required in image endpoint** → avoids vision misclassifications and guides the model.
