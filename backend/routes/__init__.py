# Routes module
from .health import health_bp
from .upload import upload_bp
from .dashboard import dashboard_bp
from .applicants import applicants_bp
from .search import search_bp
from .demo import demo_bp

__all__ = [
    "health_bp",
    "upload_bp",
    "dashboard_bp",
    "applicants_bp",
    "search_bp",
    "demo_bp"
]
