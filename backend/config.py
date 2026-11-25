import os
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
    DATABASE_PATH = os.getenv("DATABASE_PATH", str(BACKEND_DIR / "database" / "veridoc.db"))
    
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




class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    TESTING = False


class TestingConfig(Config):
    """Testing environment configuration."""
    DEBUG = False
    TESTING = True
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
