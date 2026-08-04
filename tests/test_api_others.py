from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, Mock
import pytest


class TestOthersAPI:
    def test_get_others_unauthorized(self, client):
        response = client.get("/api/others")
        assert response.status_code == 401

    @patch("app.auth._get_user_role", return_value="worker")
    def test_get_others_listing(self, _mock_role, client, worker_headers, tmp_path):
        (tmp_path / "guide.pdf").write_text("dummy pdf content")
        (tmp_path / "policy.docx").write_text("dummy docx content")

        with patch("app.other_forms._others_dir", return_value=tmp_path):
            response = client.get("/api/others", headers=worker_headers)
            assert response.status_code == 200
            data = response.get_json()
            assert "forms" in data
            forms = data["forms"]
            assert len(forms) == 2
            file_names = [item["fileName"] for item in forms]
            assert "guide.pdf" in file_names
            assert "policy.docx" in file_names

    @patch("app.auth._get_user_role", return_value="worker")
    def test_admin_upload_rejects_worker(self, _mock_role, client, worker_headers):
        response = client.post("/api/admin/others", headers=worker_headers)
        assert response.status_code == 403
        assert response.get_json() == {"error": "Admin access required."}

    @patch("app.auth._get_user_role", return_value="worker")
    def test_admin_delete_rejects_worker(self, _mock_role, client, worker_headers):
        response = client.delete("/api/admin/others/guide.pdf", headers=worker_headers)
        assert response.status_code == 403
        assert response.get_json() == {"error": "Admin access required."}
