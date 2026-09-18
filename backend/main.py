"""
Step 3: FastAPI server exposing the trained model over HTTP.

Run with:
    uvicorn main:app --reload --port 8000

Then POST a .wav file to /analyze.
"""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from inference import ApneaAnalyzer

CHECKPOINT_PATH = Path(__file__).resolve().parent.parent / "prepared_dataset" / "best_model.pt"
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
ALLOWED_EXTENSIONS = {".wav", ".flac"}

app = FastAPI(title="Sleep Apnea Audio Analyzer")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this once the frontend's real origin is known
    allow_methods=["*"],
    allow_headers=["*"],
)

analyzer: ApneaAnalyzer | None = None


@app.on_event("startup")
def load_model():
    global analyzer
    analyzer = ApneaAnalyzer(CHECKPOINT_PATH)


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": analyzer is not None}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"รองรับเฉพาะไฟล์ {', '.join(ALLOWED_EXTENSIONS)} เท่านั้น")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        result = analyzer.analyze_file(tmp_path)
    except Exception:
        raise HTTPException(422, "ไม่สามารถประมวลผลไฟล์เสียงได้ ไฟล์อาจเสียหายหรือไม่ใช่ไฟล์เสียงที่ถูกต้อง")
    finally:
        os.unlink(tmp_path)

    return result


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
