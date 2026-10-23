import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-before-deployment")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "uploads"))
    OUTPUT_FOLDER = os.getenv("OUTPUT_FOLDER", str(BASE_DIR / "generated_certificates"))
    TEMPLATE_FOLDER = os.getenv("TEMPLATE_FOLDER", str(BASE_DIR / "templates_certificates"))
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
    # Render and some providers expose postgres://; this project expects MySQL/TiDB or SQLite.
    # Set DATABASE_URL to mysql+pymysql://... for TiDB Cloud, or sqlite:///certificates.db locally.
