from __future__ import annotations

from unittest.mock import patch, Mock
import pytest


class TestSubmissionsAPI:
    def test_get_submissions_unauthorized(self, client):
        response = client.get("/api/submissions")
        assert response.status_code == 401
        assert response.get_json() == {"error": "Missing or invalid authorization header."}

    @patch("app.auth._get_user_role", return_value="worker")
    @patch("app.submissions.query")
    def test_get_submissions_worker_success(self, mock_query, _mock_role, client, worker_headers):
        mock_query.return_value = [
            {
                "id": 101,
                "worker_id": "C0036",
                "form_type": "annual",
                "form_data": '{"startDate":"2026-06-01","endDate":"2026-06-02"}',
                "status": "submitted",
                "pdf_filename": "AL_C0036_20260601.pdf",
                "created_at": None,
            }
        ]

        response = client.get("/api/submissions", headers=worker_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "submissions" in data
        submissions = data["submissions"]
        assert len(submissions) == 1
        assert submissions[0]["formType"] == "annual"
        assert submissions[0]["workerId"] == "C0036"

    @patch("app.auth._get_user_role", return_value="worker")
    @patch("app.submissions.query")
    def test_get_calendar_feed(self, mock_query, _mock_role, client, worker_headers):
        mock_query.return_value = [
            {
                "id": 201,
                "worker_id": "C0036",
                "worker_name": "Muhammad Amirul Haziq bin Kasamani",
                "calendar_name": "Haziq",
                "form_type": "annual",
                "leave_type": "annual",
                "start_date": None,
                "end_date": None,
                "duration_days": 1.0,
                "is_half_day": False,
                "half_day_period": None,
                "pdf_file_name": "AL_C0036_20260601.pdf",
            }
        ]

        response = client.get("/api/calendar", headers=worker_headers)
        assert response.status_code == 200
        data = response.get_json()
        assert "entries" in data
        entries = data["entries"]
        assert len(entries) == 1
        assert entries[0]["calendarName"] == "Haziq"
        assert entries[0]["formType"] == "annual"
        assert entries[0]["pdfUrl"] == "/generated/pdfs/AL_C0036_20260601.pdf"
