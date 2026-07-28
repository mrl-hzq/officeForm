import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    DB_HOST = os.environ.get("DB_SERVER") or os.environ.get("DB_HOST", "127.0.0.1")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))
    DB_NAME = os.environ.get("DB_SCHEMA") or os.environ.get("DB_NAME", "officeform")
    DB_USER = os.environ.get("DB_USER", "officeform")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-secret-change-in-production")
    JWT_EXPIRY_HOURS = 8
    AUTH_SHARED_PASSWORD = os.environ.get("AUTH_SHARED_PASSWORD", "abcd1234")
    GOOGLE_SHEETS_ENABLED = os.environ.get("GOOGLE_SHEETS_ENABLED", "0") == "1"
    GOOGLE_CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")
    GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
    GOOGLE_SHEET_TAB = os.environ.get("GOOGLE_SHEET_TAB", "2026")
