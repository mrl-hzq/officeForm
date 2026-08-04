from __future__ import annotations

from unittest.mock import patch, Mock
import pytest


class TestWorkersAPI:
    @patch("app.auth._get_user_role", return_value="worker")
    @patch("app.workers.query", return_value=[])
    @patch("app.workers.query_one")
    def test_get_worker_profile_success(self, mock_query_one, _mock_query, _mock_role, client, worker_headers):
        mock_query_one.return_value = {
            "worker_id": "C0036",
            "name": "Muhammad Amirul Haziq",
            "role": "worker",
            "profile_complete": 1,
            "employment_type": "permanent",
            "annual_leave_entitlement": 14.0,
        }

        response = client.get("/api/workers/C0036", headers=worker_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "worker" in data
        assert data["worker"]["workerId"] == "C0036"

    @patch("app.auth._get_user_role", return_value="worker")
    def test_get_worker_profile_forbidden(self, _mock_role, client, worker_headers):
        response = client.get("/api/workers/OTHER01", headers=worker_headers)
        assert response.status_code == 403

    @patch("app.auth._get_user_role", return_value="admin")
    def test_get_worker_profile_other_user_forbidden(self, _mock_role, client, admin_headers):
        response = client.get("/api/workers/OTHER01", headers=admin_headers)
        assert response.status_code == 403

    @patch("app.workers._rename_sheets_calendar_lines")
    @patch("app.auth._get_user_role", return_value="worker")
    @patch("app.workers.query", return_value=[])
    @patch("app.workers.query_one")
    @patch("app.workers.execute")
    def test_update_worker_profile_success(self, mock_execute, mock_query_one, _mock_query, _mock_role, _mock_rename, client, worker_headers):
        mock_query_one.return_value = {
            "worker_id": "C0036",
            "name": "Old Name",
            "role": "worker",
            "profile_complete": 0,
            "employment_type": "permanent",
            "annual_leave_entitlement": 14.0,
        }
        mock_execute.return_value = 1

        payload = {
            "name": "Muhammad Amirul Haziq bin Kasamani",
            "designation": "Software Engineer",
            "department": "IT",
            "employmentType": "permanent",
            "annualLeaveEntitlement": 14,
        }

        response = client.put("/api/workers/C0036", json=payload, headers=worker_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "worker" in data
        assert data["worker"]["workerId"] == "C0036"
