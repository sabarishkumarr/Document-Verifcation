import os
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Base directories
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
STORAGE_DIR = PROJECT_ROOT / "storage"
UPLOAD_DIR = STORAGE_DIR / "uploads"
PROCESSED_DIR = STORAGE_DIR / "processed"

# Load environment variables from .env files if present
if (PROJECT_ROOT / ".env").exists():
    load_dotenv(PROJECT_ROOT / ".env")
elif (BACKEND_DIR / ".env").exists():
    load_dotenv(BACKEND_DIR / ".env")
else:
    load_dotenv()



class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-veridoc-secret-key-change-in-prod")
    
    # Storage settings
    STORAGE_DIR = STORAGE_DIR
    UPLOAD_FOLDER = UPLOAD_DIR
    PROCESSED_FOLDER = PROCESSED_DIR
    
    # 16 MB maximum file size limit
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))
    
    # Permitted file extensions for KYC intake
    ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
    
    # Database
    DATABASE_TYPE = os.getenv("DATABASE_TYPE", "sqlite").lower()
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(BACKEND_DIR / "database" / "veridoc.db"))
    DATABASE_URL = os.getenv("DATABASE_URL")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
    POSTGRES_DB = os.getenv("POSTGRES_DB", "veridoc_db")
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
    POSTGRES_SSLMODE = os.getenv("POSTGRES_SSLMODE", "prefer")
    
    # Allowed CORS origins for local React dev server
    CORS_ORIGINS = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ]

    # OCR and Text Extraction Settings
    TESSERACT_CMD = os.getenv("TESSERACT_CMD", None)
    PDF_OCR_FALLBACK_ENABLED = os.getenv("PDF_OCR_FALLBACK_ENABLED", "True").lower() in ("true", "1")
    PDF_MIN_TEXT_CHARS = int(os.getenv("PDF_MIN_TEXT_CHARS", 100))
    PDF_CHECK_IMAGE_FOR_SCAN = os.getenv("PDF_CHECK_IMAGE_FOR_SCAN", "True").lower() in ("true", "1")
    OCR_DPI = int(os.getenv("OCR_DPI", 300))

    # AI Document Intelligence Settings
    AI_EXTRACTION_ENABLED = os.getenv("AI_EXTRACTION_ENABLED", "True").lower() in ("true", "1")
    AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL") or os.getenv("AI_MODEL", "gemini-3.5-flash-lite")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    AI_MODEL = GEMINI_MODEL
    AI_TIMEOUT = int(os.getenv("AI_TIMEOUT", 30))

    # Gemini Token Pricing Settings (USD per million tokens)
    # Verified public pricing for Gemini 1.5/2.0 Flash tier: $0.075 / 1M prompt tokens, $0.300 / 1M output tokens
    _raw_price_input = os.getenv("GEMINI_PRICE_PER_M_INPUT_TOKENS")
    GEMINI_PRICE_PER_M_INPUT_TOKENS = float(_raw_price_input) if _raw_price_input not in (None, "") else 0.075

    _raw_price_output = os.getenv("GEMINI_PRICE_PER_M_OUTPUT_TOKENS")
    GEMINI_PRICE_PER_M_OUTPUT_TOKENS = float(_raw_price_output) if _raw_price_output not in (None, "") else 0.300


def calculate_gemini_cost(
    prompt_tokens: Optional[int],
    candidate_tokens: Optional[int],
    price_per_m_input: Optional[float] = None,
    price_per_m_output: Optional[float] = None
) -> Optional[float]:
    """
    Calculate estimated Gemini API cost in USD based on verified per-million-token pricing.
    Returns None if token metadata is missing or pricing is not configured.
    """
    if prompt_tokens is None or candidate_tokens is None:
        return None

    p_in = price_per_m_input if price_per_m_input is not None else Config.GEMINI_PRICE_PER_M_INPUT_TOKENS
    p_out = price_per_m_output if price_per_m_output is not None else Config.GEMINI_PRICE_PER_M_OUTPUT_TOKENS

    if p_in is None or p_out is None:
        return None

    cost = ((prompt_tokens * p_in) / 1_000_000.0) + ((candidate_tokens * p_out) / 1_000_000.0)
    return round(cost, 6)




class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Testing environment configuration."""
    DEBUG = False
    TESTING = True
    DATABASE_TYPE = "sqlite"
    # In-memory or isolated test database
    DATABASE_PATH = ":memory:"
    UPLOAD_FOLDER = STORAGE_DIR / "test_uploads"


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    TESTING = False


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig
}
