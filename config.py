import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/health_records"
    )
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB max upload
    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
