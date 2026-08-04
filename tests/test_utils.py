from __future__ import annotations

from datetime import date, datetime
import pytest
from app.utils import (
    normalize_worker_id,
    sanitize_file_part,
    parse_iso_date,
    to_iso_date,
    parse_optional_date,
    parse_year_month,
    end_of_month,
    format_number,
    current_year_bounds,
    affects_annual_leave,
    count_al_taken_from_list,
    enrich_worker,
    parse_kpi_scores,
)


class TestUtils:
    def test_normalize_worker_id(self):
        assert normalize_worker_id("  c0036  ") == "C0036"
        assert normalize_worker_id(None) == ""
        assert normalize_worker_id("admin_01") == "ADMIN_01"

    def test_sanitize_file_part(self):
        assert sanitize_file_part("Leave Request #123!") == "Leave_Request_123"
        assert sanitize_file_part(None) == "file"
        assert sanitize_file_part("  ___  ") == "file"
        long_str = "a" * 100
        assert len(sanitize_file_part(long_str)) <= 80

    def test_parse_iso_date(self):
        dt = parse_iso_date("2026-06-15", "testField")
        assert dt == datetime(2026, 6, 15)

        with pytest.raises(ValueError, match="testField must use yyyy-mm-dd format."):
            parse_iso_date("invalid-date", "testField")

    def test_to_iso_date(self):
        dt = datetime(2026, 6, 15, 10, 30)
        assert to_iso_date(dt) == "2026-06-15"

    def test_parse_optional_date(self):
        assert parse_optional_date(None) is None
        assert parse_optional_date("") is None
        assert parse_optional_date("2026-06-15") == date(2026, 6, 15)

    def test_parse_year_month(self):
        d = parse_year_month("2026-06", "month")
        assert d == date(2026, 6, 1)

        with pytest.raises(ValueError, match="month must use yyyy-mm format."):
            parse_year_month("2026", "month")

    def test_end_of_month(self):
        assert end_of_month(date(2026, 2, 1)) == date(2026, 2, 28)
        assert end_of_month(date(2026, 6, 1)) == date(2026, 6, 30)

    def test_format_number(self):
        assert format_number(12.0) == 12
        assert format_number(12.5) == 12.5

    def test_current_year_bounds(self):
        s, e = current_year_bounds()
        assert s.month == 1 and s.day == 1
        assert e.month == 12 and e.day == 31

    def test_affects_annual_leave(self):
        assert affects_annual_leave({"leaveType": "annual"}) is True
        assert affects_annual_leave({"leaveType": "emergency"}) is True
        assert affects_annual_leave({"formType": "AL"}) is True
        assert affects_annual_leave({"formType": "EL"}) is True
        assert affects_annual_leave({"leaveType": "unpaid"}) is False
        assert affects_annual_leave({"formType": "KPI"}) is False

    def test_count_al_taken_from_list(self):
        submissions = [
            {
                "workerId": "C0036",
                "leaveType": "annual",
                "status": "submitted",
                "startDate": "2026-06-01",
                "endDate": "2026-06-03",
                "durationDays": 3.0,
            },
            {
                "workerId": "C0036",
                "leaveType": "emergency",
                "status": "submitted",
                "startDate": "2026-06-10",
                "endDate": "2026-06-10",
                "durationDays": 0.5,
            },
        ]
        taken = count_al_taken_from_list("C0036", date(2026, 1, 1), date(2026, 12, 31), submissions)
        assert taken == 3.5

    def test_enrich_worker(self):
        worker = {
            "worker_id": "C0036",
            "annualLeaveEntitlement": 14.0,
            "employmentType": "Permanent",
        }
        enriched = enrich_worker(worker, taken_to_date=3.5)
        assert enriched["annualLeaveTaken"] == 3.5
        assert enriched["annualLeaveBalance"] == 10.5

    def test_parse_kpi_scores(self):
        body = {
            "scores": {
                "knowledge": [4, 4, 4, 4, 4],
                "quality": [5, 5, 5, 5, 5],
                "problemSolving": [4, 4, 4, 4, 4],
                "communication": [4, 4, 4, 4, 4],
                "teamwork": [5, 5, 5, 5, 5],
                "initiative": [4, 4, 4, 4, 4],
                "continuousLearning": [5, 5, 5, 5, 5],
            }
        }
        scores = parse_kpi_scores(body)
        assert scores["knowledge"] == [4, 4, 4, 4, 4]
        assert len(scores) == 7
