import os


def _env(name, default):
    # Hosting dashboards make it easy to paste "NAME=value" into the value box; accept that too.
    return os.environ.get(name, default).strip().removeprefix(name + "=")


class Config:
    SECRET_KEY = _env("SECRET_KEY", "dev-secret-key-change-in-production")
    DATABASE_URL = _env("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/health_records")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB max upload
    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
