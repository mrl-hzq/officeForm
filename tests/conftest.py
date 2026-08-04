from __future__ import annotations

import jwt
from datetime import datetime, timedelta, timezone
import pytest
from app import create_app

JWT_SECRET = "test-jwt-secret-key-32-bytes-long-123456789"
SHARED_PASS = "test-shared-password"


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        AUTH_SHARED_PASSWORD=SHARED_PASS,
        JWT_SECRET_KEY=JWT_SECRET,
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def worker_token():
    payload = {
        "sub": "C0036",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def admin_token():
    payload = {
        "sub": "ADMIN01",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture
def worker_headers(worker_token):
    return {"Authorization": f"Bearer {worker_token}"}


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
