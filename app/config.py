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
    # ONLYOFFICE Document Server integration for in-browser Office file viewing.
    # PUBLIC_URL is how the user's browser reaches the document server.
    # INTERNAL_URL is how the document server container reaches this Flask app
    # to download files (e.g. http://web:3000 in Compose,
    # http://host.docker.internal:3000 when Flask runs natively).
    ONLYOFFICE_ENABLED = os.environ.get("ONLYOFFICE_ENABLED", "0") == "1"
    ONLYOFFICE_PUBLIC_URL = os.environ.get("ONLYOFFICE_PUBLIC_URL", "").rstrip("/")
    ONLYOFFICE_INTERNAL_URL = os.environ.get("ONLYOFFICE_INTERNAL_URL", "").rstrip("/")
    ONLYOFFICE_JWT_SECRET = os.environ.get("ONLYOFFICE_JWT_SECRET", "")
    MCP_SERVICE_LOGIN_KEY = os.environ.get("MCP_SERVICE_LOGIN_KEY", "")

    # Office Printer configuration
    PRINTER_ENABLED = os.environ.get("PRINTER_ENABLED", "1") == "1"
    PRINTER_HOST = os.environ.get("PRINTER_HOST", "192.168.5.115")
    PRINTER_PORT = int(os.environ.get("PRINTER_PORT", 9100))
    PRINTER_NAME = os.environ.get("PRINTER_NAME", "RICOH MP C2004ex PCL 6")
    PRINTER_METHOD = os.environ.get("PRINTER_METHOD", "auto")  # socket, command, auto
    PRINTER_TIMEOUT = int(os.environ.get("PRINTER_TIMEOUT", 10))

