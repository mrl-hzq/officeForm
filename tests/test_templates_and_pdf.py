from __future__ import annotations

import os
import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORM_ORI_DIR = os.path.join(BASE_DIR, "formOri")


class TestTemplatesAndPDF:
    def test_excel_templates_exist(self):
        """Verify all essential Excel templates exist in formOri/ directory."""
        required_templates = [
            "Leave Application Form.xls",
            "MC FORM .xls",
            "Borang Penilaian Prestasi (Non Leader).xlsx",
            "expenses claim form baru.xlsx",
        ]

        for template_name in required_templates:
            template_path = os.path.join(FORM_ORI_DIR, template_name)
            assert os.path.exists(template_path), f"Missing template file: {template_name}"
            assert os.path.getsize(template_path) > 0, f"Template file is empty: {template_name}"

    def test_libreoffice_script_exists(self):
        """Verify LibreOffice export helper script exists."""
        script_path = os.path.join(BASE_DIR, "scripts", "libreoffice_export.py")
        assert os.path.exists(script_path), "Missing scripts/libreoffice_export.py"
