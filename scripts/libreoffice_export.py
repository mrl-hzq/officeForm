from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run_calc_pdf_export(
    *,
    template_path: str | Path,
    working_workbook_path: str | Path,
    output_pdf_path: str | Path,
    actions: list[dict],
) -> None:
    template_path = Path(template_path).resolve()
    working_workbook_path = Path(working_workbook_path).resolve()
    output_pdf_path = Path(output_pdf_path).resolve()

    working_workbook_path.parent.mkdir(parents=True, exist_ok=True)
    if not working_workbook_path.exists():
        shutil.copyfile(template_path, working_workbook_path)

    bridge_python = os.environ.get("LIBREOFFICE_PYTHON", "/usr/bin/python3")
    if not Path(bridge_python).exists():
        bridge_python = sys.executable

    spec = {
        "workbookPath": str(working_workbook_path),
        "outputPdfPath": str(output_pdf_path),
        "actions": actions,
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
        json.dump(spec, handle)
        spec_path = Path(handle.name)

    try:
        result = subprocess.run(
            [bridge_python, str(ROOT / "scripts" / "libreoffice_uno_bridge.py"), str(spec_path)],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=int(os.environ.get("LIBREOFFICE_EXPORT_TIMEOUT_SECONDS", "180")),
        )
    finally:
        spec_path.unlink(missing_ok=True)

    if result.returncode != 0:
        details = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        raise RuntimeError(details or "LibreOffice PDF export failed.")

    if not output_pdf_path.exists():
        raise RuntimeError(f"LibreOffice did not create PDF: {output_pdf_path}")
