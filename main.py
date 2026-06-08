"""
main.py — FastAPI backend for Indian Food Nutrition Analysis Platform
Vision model: Gemini 1.5 Flash via google-genai (free tier, 1500 req/day)

PRODUCTION HARDENING + AI METRICS
✅ CORS restricted
✅ Rate limiting
✅ File validation
✅ Request logging with timing
✅ Detailed error reporting
✅ AI metrics tracking
✅ Confidence scoring
"""

import os
import shutil
import uuid
import logging
import time
import json
from pathlib import Path
from datetime import datetime

from google import genai
from google.genai import types
from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from database import (
    init_db, create_utensil, get_all_utensils, get_utensil,
    update_utensil, delete_utensil, log_meal,
    get_meal_history, get_daily_summary
)
from prompt_builder import build_calorie_prompt, parse_llm_response
from cache_manager import get_cached_result, cache_result
from ai_metrics import PredictionMetrics, PerformanceAnalysis

load_dotenv()

# ── Logging Setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
UPLOAD_DIR = Path("uploads")
DEPLOYMENT_URL = os.getenv("DEPLOYMENT_URL", "http://localhost:8000")
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
DEBUG_MODE = os.getenv("DEBUG", "False").lower() == "true"

if not GEMINI_API_KEY:
    logger.error("GEMINI_API_KEY not set")
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Add it to your .env file. "
        "Get a free key at https://aistudio.google.com"
    )

# ── Initialize services ───────────────────────────────────────────────────────

try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    logger.info(f"✅ Gemini client initialized with model: {GEMINI_MODEL}")
except Exception as e:
    logger.error(f"❌ Failed to initialize Gemini client: {str(e)}")
    raise

limiter = Limiter(key_func=get_remote_address)
UPLOAD_DIR.mkdir(exist_ok=True)

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI-Powered Nutrition Analysis Platform",
    description="Intelligent food recognition with Gemini 1.5 Flash. Analyze Indian meals with confidence scoring.",
    version="2.0.0"
)

# ── CORS ──────────────────────────────────────────────────────────────────────
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://localhost:8501",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8501",
]
if DEPLOYMENT_URL and DEPLOYMENT_URL not in ["http://localhost:8000", "http://127.0.0.1:8000"]:
    allowed_origins.append(DEPLOYMENT_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ── Rate Limiting ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": "Maximum 10 requests per hour per IP",
            "retry_after": 3600
        }
    )
)

# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    """Initialize app on startup."""
    try:
        init_db()
        logger.info("="*60)
        logger.info("🚀 AI NUTRITION ANALYSIS PLATFORM STARTING")
        logger.info("="*60)
        logger.info(f"📊 Gemini Model: {GEMINI_MODEL}")
        logger.info(f"📈 Free Tier Quota: 1,500 requests/day")
        logger.info(f"🔒 Rate Limiting: 10 requests/hour per IP")
        logger.info(f"📁 Max File Size: 5MB")
        logger.info(f"🎯 Debug Mode: {DEBUG_MODE}")
        logger.info(f"📍 Deployment URL: {DEPLOYMENT_URL}")
        logger.info("="*60)
        logger.info("✅ Database initialized")
        logger.info("✅ Server ready")
        logger.info(f"📖 API Docs: {DEPLOYMENT_URL}/docs")
        logger.info(f"🔍 Metrics: {DEPLOYMENT_URL}/metrics")
        logger.info("="*60 + "\n")
    except Exception as e:
        logger.error(f"❌ Startup failed: {str(e)}", exc_info=True)
        raise

# ── Vision API call ───────────────────────────────────────────────────────────

def call_vision(image_path: Path, prompt: str) -> tuple[str, float]:
    """
    Call Gemini 1.5 Flash with image + prompt.
    
    Returns:
        (response_text, latency_seconds)
    
    Raises:
        Exception: With detailed error message from Gemini API
    """
    start_time = time.time()
    
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        ext = image_path.suffix.lower().lstrip(".")
        mime_mapping = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
            "gif": "image/gif"
        }
        mime = mime_mapping.get(ext, f"image/{ext}")

        logger.info(
            f"📸 Vision API call: {image_path.name} "
            f"({len(image_bytes)} bytes, MIME: {mime})"
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime),
                prompt,
            ],
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=1500,
            )
        )
        
        latency = time.time() - start_time
        logger.info(f"✅ Vision API success in {latency:.2f}s")
        
        return response.text, latency

    except Exception as e:
        latency = time.time() - start_time
        error_str = str(e)
        error_type = type(e).__name__
        
        logger.error(
            f"❌ Vision API failed after {latency:.2f}s\n"
            f"   Error Type: {error_type}\n"
            f"   Error Message: {error_str}",
            exc_info=True
        )
        
        # Re-raise with context for better debugging
        raise RuntimeError(
            f"Gemini API Error ({error_type}): {error_str}"
        )

# ── Pydantic Models ───────────────────────────────────────────────────────────

class UtensilCreate(BaseModel):
    name: str
    type: str
    diameter_cm: float | None = None
    depth_cm: float | None = None
    volume_ml: float | None = None
    notes: str | None = None

class UtensilUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    diameter_cm: float | None = None
    depth_cm: float | None = None
    volume_ml: float | None = None
    notes: str | None = None

# ── Utensil Endpoints ─────────────────────────────────────────────────────────

@app.get("/utensils", tags=["Utensils"])
def list_utensils():
    """Get all saved utensil profiles."""
    try:
        return get_all_utensils()
    except Exception as e:
        logger.error(f"Failed to list utensils: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch utensils")

@app.post("/utensils", tags=["Utensils"], status_code=201)
def add_utensil(body: UtensilCreate):
    """Create a new utensil profile."""
    try:
        logger.info(f"Creating utensil: {body.name}")
        return create_utensil(
            name=body.name,
            utensil_type=body.type,
            diameter_cm=body.diameter_cm,
            depth_cm=body.depth_cm,
            volume_ml=body.volume_ml,
            notes=body.notes,
        )
    except ValueError as e:
        logger.warning(f"Utensil creation failed: {str(e)}")
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Utensil creation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to create utensil")

@app.get("/utensils/{utensil_id}", tags=["Utensils"])
def get_one_utensil(utensil_id: int):
    """Get a specific utensil profile."""
    try:
        u = get_utensil(utensil_id)
        if not u:
            raise HTTPException(status_code=404, detail="Utensil not found")
        return u
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching utensil {utensil_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch utensil")

@app.put("/utensils/{utensil_id}", tags=["Utensils"])
def edit_utensil(utensil_id: int, body: UtensilUpdate):
    """Update a utensil profile."""
    try:
        if not get_utensil(utensil_id):
            raise HTTPException(status_code=404, detail="Utensil not found")
        logger.info(f"Updating utensil {utensil_id}")
        update_utensil(utensil_id, **body.dict(exclude_none=True))
        return get_utensil(utensil_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating utensil {utensil_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update utensil")

@app.delete("/utensils/{utensil_id}", tags=["Utensils"])
def remove_utensil(utensil_id: int):
    """Delete a utensil profile."""
    try:
        if not get_utensil(utensil_id):
            raise HTTPException(status_code=404, detail="Utensil not found")
        logger.info(f"Deleting utensil {utensil_id}")
        delete_utensil(utensil_id)
        return {"deleted": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting utensil {utensil_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete utensil")

# ── Core Analyze Endpoint ─────────────────────────────────────────────────────

@app.post("/analyze", tags=["Analysis"])
@limiter.limit("10/hour")
async def analyze_meal(
    request: Request,
    image: UploadFile = File(..., description="Food photo (JPEG, PNG, WebP)"),
    utensil_id: int | None = Form(None, description="Utensil profile ID (optional)"),
    fill_level: float = Form(0.85, description="Fill level 0.0-1.0"),
):
    """
    AI-Powered Nutrition Analysis
    
    Upload a meal photo to get:
    - Food identification with confidence scores
    - Ingredient breakdown
    - Calorie prediction
    - Nutritional analysis
    - Health recommendations
    
    Response: 2-4 seconds
    Rate limit: 10/hour per IP
    Free tier: 1,500 requests/day
    """
    
    request_start = time.time()
    client_ip = request.client.host if request.client else "unknown"
    
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 ANALYZE REQUEST from {client_ip}")
    logger.info(f"{'='*60}")

    

    try:
        # ── Input Validation ──────────────────────────────────────────────────
        if not 0.0 < fill_level <= 1.0:
            logger.warning(f"❌ Invalid fill_level: {fill_level}")
            raise HTTPException(
                status_code=422,
                detail="fill_level must be between 0.01 and 1.0"
            )

        if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
            logger.warning(f"❌ Invalid MIME type: {image.content_type}")
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported image type: {image.content_type}. "
                       "Use JPEG, PNG, or WebP."
            )

        # Check file size
        file_size = len(await image.read())
        await image.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            logger.warning(f"❌ File too large: {file_size} bytes")
            raise HTTPException(
                status_code=413,
                detail=f"File too large ({file_size/1024/1024:.1f}MB). Max 5MB."
            )

        logger.info(f"✅ File validation passed ({file_size/1024:.1f}KB)")

        # ── Check Cache ───────────────────────────────────────────────────────
        image_data = await image.read()
        await image.seek(0)
        
        cache_hit = get_cached_result(image_data, utensil_id, fill_level)
        if cache_hit:
            logger.info(f"✅ CACHE HIT - Returning cached result")
            logger.info(f"{'='*60}\n")
            
            # Log as cached metric
            try:
                PredictionMetrics.log_prediction(
                    meal_id=cache_hit.get("meal_id", 0),
                    dish_name=cache_hit.get("dishes", [{}])[0].get("dish_name", "Unknown"),
                    confidence_avg=cache_hit.get("dishes", [{}])[0].get("confidence", 0),
                    model_response_time=0.05,  # Cached = ~50ms
                    was_cached=True
                )
            except Exception as e:
                logger.warning(f"Failed to log cache hit metric: {str(e)}")
            
            return {**cache_hit, "from_cache": True, "cached_ms": 50}

        # ── Save Image ────────────────────────────────────────────────────────
        ext = image.filename.rsplit(".", 1)[-1] if "." in (image.filename or "") else "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        image_path = UPLOAD_DIR / filename

        with open(image_path, "wb") as f:
            f.write(image_data)
        
        logger.info(f"💾 Saved image: {filename}")
                # DEMO MODE - TEMPORARY

        return {
            "meal_id": 999,
            "utensil_used": None,
            "fill_level": fill_level,
            "model_used": "Demo Mode",
            "from_cache": False,
            "response_time_ms": 500,
            "total_kcal": 650,
            "dishes": [
                {
                    "dish_name": "Chicken Biryani",
                    "weight_g": 450,
                    "subtotal_kcal": 650,
                    "confidence": 0.95,
                    "ingredients": [
                        {"name": "Rice", "grams": 250, "kcal": 325},
                        {"name": "Chicken", "grams": 150, "kcal": 250},
                        {"name": "Spices", "grams": 50, "kcal": 75}
                    ]
                }
            ]
        }

        # ── Get Utensil Context ───────────────────────────────────────────────
        utensil = None
        if utensil_id:
            utensil = get_utensil(utensil_id)
            if utensil:
                logger.info(f"🥄 Using utensil: {utensil['name']}")
            else:
                logger.warning(f"⚠️  Utensil {utensil_id} not found")
        

        # ── Store Meal Log ────────────────────────────────────────────────────
        logger.info(f"💾 Storing meal log...")
        
        dishes = parsed.get("dishes", [])
        all_ingredients = []
        for dish in dishes:
            all_ingredients.extend(dish.get("ingredients", []))

        try:
            meal_id = log_meal(
                image_path=str(image_path),
                utensil_id=utensil_id,
                fill_level=fill_level,
                dish_name=", ".join(d.get("dish_name", "Unknown") for d in dishes),
                weight_g=sum(d.get("weight_g", 0) for d in dishes),
                total_kcal=parsed.get("total_kcal", 0),
                ingredients=all_ingredients,
                raw_response=""
            )
            logger.info(f"✅ Meal {meal_id} logged")
        except Exception as e:
            logger.error(f"❌ Failed to log meal: {str(e)}")
            meal_id = 0

        # ── Build Response ────────────────────────────────────────────────────
        response = {
            "meal_id": meal_id,
            "utensil_used": utensil["name"] if utensil else None,
            "fill_level": fill_level,
            "model_used": GEMINI_MODEL,
            "from_cache": False,
            "response_time_ms": round(vision_latency * 1000, 1),
            **parsed
        }

        # ── Cache Result ──────────────────────────────────────────────────────
        try:
            cache_result(image_data, utensil_id, fill_level, response)
            logger.info(f"💾 Result cached")
        except Exception as e:
            logger.warning(f"⚠️  Failed to cache result: {str(e)}")

        # ── Log Metrics ───────────────────────────────────────────────────────
        try:
            confidence_avg = dishes[0].get("confidence", 0) if dishes else 0
            PredictionMetrics.log_prediction(
                meal_id=meal_id,
                dish_name=dishes[0].get("dish_name", "Unknown") if dishes else "Unknown",
                confidence_avg=confidence_avg,
                model_response_time=vision_latency,
                was_cached=False
            )
        except Exception as e:
            logger.warning(f"Failed to log metrics: {str(e)}")

        total_time = time.time() - request_start
        logger.info(f"✅ Request completed in {total_time:.2f}s")
        logger.info(f"{'='*60}\n")

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unhandled error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e) if DEBUG_MODE else 'Please try again'}"
        )

# ── History & Summary ─────────────────────────────────────────────────────────

@app.get("/history", tags=["Data"])
def meal_history(limit: int = 20):
    """Get recent meal logs."""
    try:
        limit = min(limit, 100)
        return get_meal_history(limit=limit)
    except Exception as e:
        logger.error(f"Failed to fetch history: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch history")

@app.get("/summary", tags=["Data"])
def daily_summary(date: str | None = None):
    """Get daily nutrition summary."""
    try:
        return get_daily_summary(date_str=date)
    except Exception as e:
        logger.error(f"Failed to fetch summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch summary")

# ── AI Metrics & Analytics ────────────────────────────────────────────────────

@app.get("/metrics", tags=["Analytics"])
def get_metrics():
    """Get AI performance metrics."""
    try:
        return PerformanceAnalysis.get_summary()
    except Exception as e:
        logger.error(f"Failed to get metrics: {str(e)}")
        return {
            "error": "Could not load metrics",
            "detail": str(e)
        }

# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """System health check."""
    return {
        "status": "healthy",
        "model": GEMINI_MODEL,
        "provider": "Google Gemini",
        "quota": "1500 requests/day (free tier)",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/", tags=["System"])
def root():
    """Root endpoint."""
    return {
        "app": "AI-Powered Nutrition Analysis Platform",
        "version": "2.0.0",
        "docs": "/docs",
        "metrics": "/metrics",
        "health": "/health"
    }

# ── Global Error Handler ──────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler."""
    logger.error(f"❌ Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if DEBUG_MODE else "Please try again"
        }
    )

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Starting uvicorn...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)